"""Initialization — single wiring point for the simulation (PDL: Initialization).

Responsibilities:
  1. Create the SimPy environment.
  2. Load the road network and build the shared traffic-density state.
  3. Create ALL shared queues + the parking lot here, and inject them into the
     components (so runtime infrastructure lives in exactly one place).
  4. Validate/clean the entry-node data before the run.
  5. Start every component process and run the simulation.
  6. Print a short summary.

Run with:  python main.py
"""

import os
import sys
import pickle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import simpy
import networkx as nx

import config
from Functions.Trafficflowmodel import (
    init_from_graph,
    shortest_path,
    background_density_update,
)
from Functions.TTicketScan import TTicketScan
from Functions.TShuttleBus import TShuttleBus
from Functions.TCarGenerator import TCarGenerator
from Functions.TVisitorGenerator import TVisitorGenerator


NETWORK_PKL = os.path.join('INPUT_Data_Files', 'network.pkl')

# PLACEHOLDER: effectively-unlimited parking until Phase 7 adds a real capacity cap.
PARKING_CAPACITY = 1_000_000

# Toggle the real-world background traffic process (reads flow_2_3_avg.csv).
ENABLE_BACKGROUND_DENSITY = True


def load_graph():
    """Load the prepared OSMnx road graph (network.pkl)."""
    with open(NETWORK_PKL, 'rb') as f:
        return pickle.load(f)


def prepare_start_nodes(G, density_map):
    """Validate and clean the car entry-node data before the run.

    Init-time guards for known data issues (see TASKLIST: "Fix nodes"):
      - Drop any start node that cannot reach the parking lot in the directed
        graph (otherwise its cars crash on shortest_path).
      - Validate/normalise the remaining entry probabilities so np.random.choice
        always receives a valid distribution.

    Mutates config.ROAD_NETWORK in place so TVisitor / TCarGenerator pick up the
    cleaned values, and returns the cleaned {name: node_id} dict.
    """
    start_nodes = dict(config.ROAD_NETWORK['StartNodes'])
    probs = dict(config.ROAD_NETWORK['CarStartNodeProb'])
    parking = config.ROAD_NETWORK['Parkinglot']

    # 1. reachability filter
    reachable = {}
    for name, nid in start_nodes.items():
        try:
            shortest_path(G, nid, parking, density_map)
            reachable[name] = nid
        except nx.NetworkXNoPath:
            print(f"  [WARN] start node {name} ({nid}) has no path to the parking "
                  f"lot - dropping it (data issue: fix node).")

    # 2. normalise probabilities over the reachable nodes
    weights = {name: probs.get(name, 0.0) for name in reachable}
    total = sum(weights.values())
    if total <= 0:
        raise RuntimeError("No reachable car start node has a positive probability.")
    if abs(total - 1.0) > 1e-6:
        print(f"  [WARN] CarStartNodeProb summed to {total:.4f}, not 1.0 - "
              f"renormalising the reachable nodes to a valid distribution.")
    normalised = {name: w / total for name, w in weights.items()}

    config.ROAD_NETWORK['StartNodes'] = reachable
    config.ROAD_NETWORK['CarStartNodeProb'] = normalised
    return reachable


def main():
    env = simpy.Environment(initial_time=config.SIMULATION['EventStartTime'])

    # --- road network + shared traffic-density state ---
    G = load_graph()
    density_map = init_from_graph(G)

    # --- init-time validation of entry-node data ---
    start_nodes = prepare_start_nodes(G, density_map)

    # --- shared queues (all created here, injected into the components) ---
    busqueue = simpy.Store(env)
    ticketqueue = simpy.Store(env)
    carqueues = {node_id: simpy.Store(env) for node_id in start_nodes.values()}

    # --- parking lot: cars queue at the entrance, then hold a slot once parked ---
    parking_entry = simpy.Resource(env, capacity=config.CAR['ParkingLotEntryLanes'])
    parking_lot = simpy.Resource(env, capacity=PARKING_CAPACITY)

    # --- real-world background traffic density (optional) ---
    if ENABLE_BACKGROUND_DENSITY:
        env.process(background_density_update(env, G, density_map))

    # --- components (PDL Initialization order) ---
    ticket_scan = TTicketScan(env, ticketqueue)
    shuttle_bus = TShuttleBus(env, G, density_map, busqueue)
    car_generator = TCarGenerator(env, G, density_map, parking_lot, parking_entry, carqueues)
    visitor_generator = TVisitorGenerator(env, busqueue, carqueues, ticketqueue)

    # --- run ---
    env.run(until=config.SIMULATION['EventEndingTime'])

    # --- summary (per-visitor logging is Phase 5) ---
    waiting_for_car = sum(len(q.items) for q in carqueues.values())
    print(f"\nSimulation finished at t = {env.now} s")
    print(f"Cars parked:                 {parking_lot.count}")
    print(f"Visitors still waiting for:")
    print(f"  - a car:                   {waiting_for_car}")
    print(f"  - the shuttle bus:         {len(busqueue.items)}")
    print(f"  - the ticket scan:         {len(ticketqueue.items)}")


if __name__ == '__main__':
    main()
