import os
import sys
import pandas as pd
from typing import Dict, Tuple

import networkx as nx

# Add the project root to sys.path so that config.py can be imported no matter
# which directory Python is launched from (the file lives one level up from here)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

EdgeKey = Tuple[int, int]  # directed edge identifier: (upstream node ID, downstream node ID)



class TrafficDensityMap:
    """Shared mutable density state for all road segments.

    Keyed by (u, v) node-ID pairs matching the OSMnx graph edges.
    rho_max per edge is stored alongside density so travel-time queries
    are self-contained.
    """

    def __init__(self) -> None:
        # Dynamic density added exclusively by vehicles in the discrete-event simulation [veh/m]
        self._density: Dict[EdgeKey, float] = {}
        # Jam density: the maximum density at which the road becomes fully blocked [veh/m]
        self._rho_max: Dict[EdgeKey, float] = {}
        # Free-flow speed: the speed vehicles travel when the road is completely empty [m/s]
        self._u_max_ms: Dict[EdgeKey, float] = {}
        # Physical length of the road segment [m]
        self._length: Dict[EdgeKey, float] = {}
        # Background density from real-world traffic data (vehicles not explicitly modelled in the simulation) [veh/m]
        self._rho_background: Dict[EdgeKey, float] = {}

    def init_edge(self, u: int, v: int, rho_max: float, u_max_ms: float, length: float) -> None:
        """Register an edge with its capacity; initial density is 0."""
        key = (u, v)
        self._rho_max[key] = rho_max
        self._u_max_ms[key] = u_max_ms
        self._length[key] = length
        self._density.setdefault(key, 0.0)  # setdefault leaves any pre-existing density intact
        self._rho_background[key] = 0.0

    def set_density(self, u: int, v: int, rho: float) -> None:
        """Write the simulated vehicle density for edge (u,v), clamped to the physical range [0, rho_max].

        Clamping prevents negative densities (e.g. from floating-point rounding when
        the last car leaves) and densities above the jam density.
        """
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._density[key] = max(0.0, min(rho, rho_max))

    def set_rho_background(self, u, v, rho_background):
        """Set the background traffic density for edge (u,v).

        Background density represents real-world vehicles not tracked as individual agents
        in the simulation (e.g. regular commuter traffic derived from loop-detector counts).
        """
        self._rho_background[(u,v)] = rho_background

    def get_density(self, u: int, v: int) -> float:
        """Return the total density on edge (u,v) [veh/m]: simulated cars + background traffic.

        Both contributions are combined here so that all downstream calculations
        (speed, travel time, routing) automatically account for real-world congestion.
        """
        return self._density.get((u, v), 0.0) + self._rho_background.get((u,v), 0.0)

    def get_rho_max(self, u: int, v: int) -> float:
        """Return the jam density [veh/m] for edge (u,v) — the density at which flow stops."""
        return self._rho_max.get((u, v))

    def get_u_max_ms(self, u: int, v: int) -> float:
        """Return the free-flow speed [m/s] for edge (u,v) — speed when no other vehicles are present."""
        return self._u_max_ms.get((u, v))

    def get_length(self, u: int, v: int) -> float:
        """Return the length [m] of edge (u,v)."""
        return self._length.get((u, v))

    def update_density(self, u: int, v: int, delta: float) -> None:
        """Add delta to the simulated density on edge (u,v).

        Pass a positive delta when a vehicle enters the segment,
        a negative delta when it leaves. The result is clamped via set_density.
        """
        self.set_density(u, v, self._density.get((u, v), 0) + delta)


def greenshields_speed(rho: float, rho_max: float, u_max_ms: float) -> float:
    """Greenshields linear speed-density model: u = u_max * (1 - rho / rho_max).

    Returns 0 when the segment is at jam density (rho >= rho_max).
    """
    if rho_max <= 0:
        return 0.0
    rho_clamped = min(max(rho, 0.0), rho_max)
    if rho_clamped >= rho_max:
        rho_clamped = rho_max*0.9999 # avoid returning 0 speed to prevent infinite travel times; treat as near-jam
    return u_max_ms * (1.0 - rho_clamped / rho_max)#PLACEHOLDER fix the crawling speed later


def travel_time(length: float, rho: float, rho_max: float, u_max_ms: float) -> float:
    """Travel time (seconds) for a segment given its length and current density.

    Returns inf when the segment is gridlocked.
    """
    speed = greenshields_speed(rho, rho_max, u_max_ms)
    if speed <= 0.0:
        return float('inf')
    return length / speed


def edge_travel_time(u: int, v: int, density_map: TrafficDensityMap) -> float:
    """Convenience wrapper that pulls rho and rho_max from the shared density map."""
    rho = density_map.get_density(u, v)
    rho_max = density_map.get_rho_max(u, v)
    u_max_ms = density_map.get_u_max_ms(u, v)
    length = density_map.get_length(u, v)
    return travel_time(length, rho, rho_max, u_max_ms)


def init_from_graph(G: nx.MultiDiGraph, density_map: "TrafficDensityMap | None" = None) -> TrafficDensityMap:
    """Populate a TrafficDensityMap from an OSMnx graph.

    Each edge must have a 'rho_max' attribute (set by Prepare_network.py)
    and a 'u_max_ms' attribute.
    If density_map is None, the module-level traffic_density is used.
    """
    target = density_map if density_map is not None else traffic_density
    for u, v, data in G.edges(data=True):
        rho_max = data.get('rho_max', float('inf'))
        u_max_ms = data.get('u_max_ms', config.TRAFFIC_MODEL['speed_fallback'] / 3.6) # default to fallback speed in m/s
        length = data.get('length', 0.0)
        target.init_edge(u, v, rho_max, u_max_ms, length)
    return target




def shortest_path(G: nx.MultiDiGraph, source: int, target: int, density_map: TrafficDensityMap) -> list[int]:
    """Return the fastest path from source to target as an ordered list of OSMnx node IDs.

    Dijkstra's algorithm is run with edge weights equal to the density-dependent travel
    time at the moment of the call. Because weights are re-evaluated every call, the route
    adapts to current congestion levels throughout the simulation.
    """
    def weight(u, v, data):
        # Compute travel time on each edge from the current density state; used as Dijkstra weight
        return edge_travel_time(u, v, density_map)
    return nx.shortest_path(G, source, target, weight=weight)


#Background density updater
def background_density_update(env, G, density_map):
    """SimPy generator process that updates background traffic density on every edge throughout the simulation.

    Background density represents real-world non-simulated traffic. It is derived from
    hourly average vehicle counts (flow_2_3_avg.csv) using the fundamental traffic-flow
    identity: density = flow / speed. The flow data is indexed by hour of the day.

    To avoid abrupt jumps at the top of each hour, the transition is smoothed with
    linear interpolation. The process wakes up `interpolate/2` seconds before each hour
    boundary and then steps 60 seconds at a time across the full `interpolate`-second
    window, blending from the current-hour density to the next-hour density.

    Two road types are treated differently:
      - N-roads (ref 'N35' or 'N348'): major state roads; use the flow density directly.
      - All other roads: local roads; flow density is scaled down by N_local, a config
        factor expressing what fraction of N-road traffic also loads the local network.
    """
    interpolate = config.ROAD_NETWORK['interpolate']    # total width of the interpolation window around each hour boundary [s]
    convert_N_local = config.ROAD_NETWORK['N_local']    # scaling factor: converts N-road flow density to equivalent local-road background density
    flow = pd.read_csv('INPUT_Data_Files/ROAD_DATA/flow_2_3_avg.csv')['Avg Saturday (all det)']  # hourly vehicle counts [veh/h], index = integer hour of the day
    t_start = config.SIMULATION['EventStartTime']       # simulation start time [s since midnight]
    t_end = config.SIMULATION['EventEndingTime']         # simulation end time [s since midnight]

    #Initial set of density
    # Before any SimPy events run, set each edge's background density to the value
    # corresponding to the starting hour so the simulation begins with realistic congestion
    for u, v, data in G.edges(data=True):
        ref = data.get('ref', None)            # road reference string (e.g. 'N35'); identifies whether this is an N-road
        u_max_ms = data.get('u_max_ms', None)  # free-flow speed [m/s], used to convert flow [veh/h] to density

        # density = flow [veh/h] / speed [km/h]; u_max_ms * 3.6 converts m/s to km/h
        flow_dens_N = flow / (u_max_ms * 3.6)
        # local-road background density is N-road density scaled by the N_local factor
        flow_dens_local = convert_N_local* (flow / (u_max_ms * 3.6))

        # int(t_start / 3600) gives the integer hour index into the flow array
        if ref in ('N35', 'N348'):
            rho_background_value = (flow_dens_N[int(t_start / 3600)])
        else:
            rho_background_value = (flow_dens_local[int(t_start / 3600)])
        density_map.set_rho_background(u, v, rho_background_value)
    while True:
        current_hour = int(env.now // 3600)    # integer hour index of the hour currently in progress
        next_hour = current_hour + 1            # integer hour index of the next hour (interpolation target)
        seconds_to_next_hour = 3600 - (env.now % 3600) #3600 seconds in an hour minus the current time how many seconds are left of the hour
        # Stop the process if the start of the next interpolation window (interpolate/2 s before the
        # next hour boundary) would fall at or after the end of the simulation
        if (next_hour * 3600 - interpolate/2) >= t_end:
            break
        # Sleep until interpolate/2 seconds before the next full hour so the interpolation
        # window is centred symmetrically on the hour boundary
        yield env.timeout(seconds_to_next_hour - int(interpolate/2))

        for step in range(int(interpolate/60)):
            #Calculate flow

            # Elapsed time within the interpolation window [s]; increases by 60 s each step
            t = step * 60
            for u, v, data in G.edges(data=True):
                ref = data.get('ref', None)
                u_max_ms = data.get('u_max_ms', None)

                flow_dens_N = flow / (u_max_ms * 3.6)
                flow_dens_local = convert_N_local* (flow / (u_max_ms * 3.6))


                if ref in ('N35', 'N348'):
                    # Linear interpolation: at t=0 the value equals current_hour density;
                    # at t=interpolate it equals next_hour density
                    rho_background_value = (flow_dens_N[current_hour] +
                                                       (flow_dens_N[next_hour] - flow_dens_N[current_hour])
                                                       * (t/interpolate))
                else:
                    rho_background_value = (flow_dens_local[current_hour] +
                                                       (flow_dens_local[next_hour] - flow_dens_local[current_hour])
                                                       * (t/interpolate))
                density_map.set_rho_background(u, v, rho_background_value)

            yield env.timeout(60)  # advance the simulation clock by 60 s before computing the next interpolation step


# Module-level shared density map used across the simulation
traffic_density = TrafficDensityMap()
