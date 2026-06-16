"""Entry point that wires up and runs one simulation.

This module is the single place where all the moving parts are connected:

  1. Create the SimPy environment (the discrete-event clock).
  2. Load the road network and build the shared traffic-density state.
  3. Create every shared queue and the parking lot, then inject them into the
     components, so the runtime infrastructure is defined in exactly one spot.
  4. Validate and clean the car entry-node data before the run starts.
  5. Start every component process and run the simulation to the end time.
  6. Write the logs and print a short summary.

Run with:  python main.py
"""

import os
import sys
import pickle

# Make the project root importable regardless of the launch directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import simpy
import networkx as nx

import config
from Functions.Trafficflowmodel import (
    TrafficDensityMap,
    init_from_graph,
    shortest_path,
    background_density_update,
    edge_state,
)
from Functions.TTicketScan import TTicketScan
from Functions.TShuttleBus import TShuttleBus
from Functions.TCarGenerator import TCarGenerator
from Functions.TVisitorGenerator import TVisitorGenerator
from Functions.SimulationLogger import SimulationLogger


# Prepared OSMnx road graph produced by INPUT_Data_Files/Prepare_network.py.
NETWORK_PKL = os.path.join('INPUT_Data_Files', 'network.pkl')

# Effectively-unlimited parking capacity until a real cap is modelled.
PARKING_CAPACITY = 1_000_000

# Whether to layer real-world background traffic on top of the simulated cars.
ENABLE_BACKGROUND_DENSITY = True


def load_graph():
    """Load and return the prepared OSMnx road graph from network.pkl."""
    with open(NETWORK_PKL, 'rb') as f:
        return pickle.load(f)


def prepare_start_nodes(G, density_map):
    """Validate and clean the car entry-node data before the run.

    Two known data issues are guarded against here:
      - Drop any start node that cannot reach the parking lot in the directed
        graph, since a car starting there would crash on shortest_path.
      - Renormalise the remaining entry probabilities so np.random.choice always
        receives a valid distribution that sums to 1.

    The cleaned values are written back into config.ROAD_NETWORK so the visitor
    and car generators pick them up, and the cleaned {name: node_id} dict is
    returned for convenience.
    """
    start_nodes = dict(config.ROAD_NETWORK['StartNodes'])
    probs = dict(config.ROAD_NETWORK['CarStartNodeProb'])
    parking = config.ROAD_NETWORK['Parkinglot']

    # Step 1: keep only the start nodes that can actually reach the parking lot.
    reachable = {}
    for name, nid in start_nodes.items():
        try:
            shortest_path(G, nid, parking, density_map)
            reachable[name] = nid
        except nx.NetworkXNoPath:
            print(f"  [WARN] start node {name} ({nid}) has no path to the parking "
                  f"lot - dropping it (data issue: fix node).")

    # Step 2: renormalise the probabilities over the surviving nodes.
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


def queue_snapshot_update(env, logger, busqueue, ticketqueue, carqueues, parking_entry, parking_lot):
    """SimPy process: periodically record the length of every queue.

    Snapshots are taken at a fixed interval so the dashboard and replay can
    reconstruct queue lengths over time, independent of the enqueue/dequeue
    events logged by the components themselves.
    """
    interval = config.LOGGING['QueueSampleInterval']
    while True:
        logger.log_queue(
            sim_time=env.now,
            queue_name='shuttle_bus_queue',
            location='bus_stop',
            length=len(busqueue.items),
            event_type='snapshot',
            actor_type='system',
            actor_id='',
        )
        logger.log_queue(
            sim_time=env.now,
            queue_name='ticket_scan_queue',
            location='ticket_scan',
            length=len(ticketqueue.items),
            event_type='snapshot',
            actor_type='system',
            actor_id='',
        )
        # One snapshot row per car pickup queue (there is one per entry node).
        for node_id, queue in carqueues.items():
            logger.log_queue(
                sim_time=env.now,
                queue_name=f"car_queue_{node_id}",
                location=node_id,
                length=len(queue.items),
                event_type='snapshot',
                actor_type='system',
                actor_id='',
            )
        logger.log_queue(
            sim_time=env.now,
            queue_name='parking_entry_queue',
            location='parking_lot',
            length=len(parking_entry.queue),
            event_type='snapshot',
            actor_type='system',
            actor_id='',
        )
        logger.log_queue(
            sim_time=env.now,
            queue_name='parking_lot_occupancy',
            location='parking_lot',
            length=parking_lot.count,
            event_type='snapshot',
            actor_type='system',
            actor_id='',
        )
        # The wait comes after the logging, so the first snapshot is captured
        # immediately at simulation start (t=EventStartTime) and then every
        # `interval` seconds thereafter.
        yield env.timeout(interval)


def segment_snapshot_update(env, G, density_map, logger):
    """SimPy process: periodically record the density state of every road edge.

    These snapshots drive the congestion colouring on the map replay and the
    hotspot chart on the dashboard.
    """
    interval = config.LOGGING['SegmentSampleInterval']
    while True:
        for u, v, _data in G.edges(data=True):
            logger.log_segment_density(
                sim_time=env.now,
                event_type='snapshot',
                actor_type='system',
                actor_id='',
                u=u,
                v=v,
                segment_id=f"{u}->{v}",
                **edge_state(u, v, density_map),
            )
        # The wait comes after the logging, so the first snapshot is captured
        # immediately at simulation start (t=EventStartTime) and then every
        # `interval` seconds thereafter.
        yield env.timeout(interval)


def main():
    # The clock starts at the event start time rather than 0.
    env = simpy.Environment(initial_time=config.SIMULATION['EventStartTime'])
    logger = SimulationLogger(
        config.LOGGING['OutputDir'],
        run_id=config.LOGGING.get('RunId'),
    )

    # --- road network + shared traffic-density state ---
    G = load_graph()
    density_map = init_from_graph(G, TrafficDensityMap())

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

    # Snapshot processes only run when their sampling interval is enabled.
    if config.LOGGING['QueueSampleInterval'] > 0:
        env.process(queue_snapshot_update(
            env,
            logger,
            busqueue,
            ticketqueue,
            carqueues,
            parking_entry,
            parking_lot,
        ))
    if config.LOGGING['SegmentSampleInterval'] > 0:
        env.process(segment_snapshot_update(env, G, density_map, logger))

    # --- components: each starts its own SimPy processes on construction ---
    ticket_scan = TTicketScan(env, ticketqueue, logger)
    shuttle_bus = TShuttleBus(env, G, density_map, busqueue, logger)
    car_generator = TCarGenerator(env, G, density_map, parking_lot, parking_entry, carqueues, logger)
    visitor_generator = TVisitorGenerator(env, busqueue, carqueues, ticketqueue, logger)

    # --- run the simulation until the event end time ---
    env.run(until=config.SIMULATION['EventEndingTime'])

    # --- assemble and log the scenario summary, then flush all logs ---
    waiting_for_car = sum(len(q.items) for q in carqueues.values())
    logger.set_final_time(env.now)
    scenario_summary = {
        'finished_at': env.now,
        'event_start_time': config.SIMULATION['EventStartTime'],
        'event_ending_time': config.SIMULATION['EventEndingTime'],
        'number_visitors_config': config.SIMULATION['NumberVisitors'],
        'visitors_generated': logger.visitor_count(),
        'visitors_completed': logger.completed_visitor_count(),
        'cars_parked': parking_lot.count,
        'waiting_for_car': waiting_for_car,
        'waiting_for_shuttle_bus': len(busqueue.items),
        'waiting_for_ticket_scan': len(ticketqueue.items),
        'mode_split': dict(config.VISITOR_GENERATOR['ModeSplit']),
        'n_buses': config.SHUTTLE_BUS['n_buses'],
        'ticket_scan_lanes': config.TICKET_SCAN['NumScanLanes'],
        'parking_entry_lanes': config.CAR['ParkingLotEntryLanes'],
    }
    # Merge in the computed KPIs (travel times, CO2, peak queues, etc.).
    scenario_summary.update(logger.summary_metrics(config.EMISSIONS))
    logger.log_scenario_summary(scenario_summary)
    logger.flush(final_time=env.now)

    # --- console summary of the finished run ---
    print(f"\nSimulation finished at t = {env.now} s")
    print(f"Run ID:                      {logger.run_id}")
    print(f"Logs written to:             {config.LOGGING['OutputDir']}")
    print(f"Cars parked:                 {parking_lot.count}")
    print(f"Cars waiting at parking lot  {len(parking_entry.queue)}")
    print(f"Visitors still waiting for:")
    print(f"  - a car:                   {waiting_for_car}")
    print(f"  - the shuttle bus:         {len(busqueue.items)}")
    print(f"  - the ticket scan:         {len(ticketqueue.items)}")


if __name__ == '__main__':
    main()
