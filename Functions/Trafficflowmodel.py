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
        # Dynamic occupancy added by vehicles in the discrete-event simulation [vehicles on edge]
        self._density: Dict[EdgeKey, float] = {}
        # Jam occupancy: the maximum number of vehicle equivalents on this edge
        self._rho_max: Dict[EdgeKey, float] = {}
        # Free-flow speed: the speed vehicles travel when the road is completely empty [m/s]
        self._u_max_ms: Dict[EdgeKey, float] = {}
        # Physical length of the road segment [m]
        self._length: Dict[EdgeKey, float] = {}
        # Background occupancy from real-world traffic data [vehicles on edge]
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
        """Write the simulated vehicle occupancy for edge (u,v), clamped to the physical range [0, rho_max].

        Clamping prevents negative densities (e.g. from floating-point rounding when
        the last car leaves) and densities above the jam density.
        """
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._density[key] = max(0.0, min(rho, rho_max))

    def set_rho_background(self, u, v, rho_background):
        """Set the background traffic occupancy for edge (u,v).

        Background density represents real-world vehicles not tracked as individual agents
        in the simulation (e.g. regular commuter traffic derived from loop-detector counts).
        """
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._rho_background[key] = max(0.0, min(float(rho_background), rho_max))

    def get_density(self, u: int, v: int) -> float:
        """Return the total occupancy on edge (u,v): simulated vehicles + background traffic.

        Both contributions are combined here so that all downstream calculations
        (speed, travel time, routing) automatically account for real-world congestion.
        """
        return self._density.get((u, v), 0.0) + self._rho_background.get((u,v), 0.0)

    def get_simulated_density(self, u: int, v: int) -> float:
        """Return simulated vehicle occupancy on edge (u,v), excluding background traffic."""
        return self._density.get((u, v), 0.0)

    def get_background_density(self, u: int, v: int) -> float:
        """Return background traffic occupancy on edge (u,v)."""
        return self._rho_background.get((u, v), 0.0)

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
        """Add delta to the simulated occupancy on edge (u,v).

        Pass a positive delta when a vehicle enters the segment,
        a negative delta when it leaves. The result is clamped via set_density.
        """
        self.set_density(u, v, self._density.get((u, v), 0) + delta)


def greenshields_speed(rho: float, rho_max: float, u_max_ms: float) -> float:
    """Greenshields linear speed-occupancy model: u = u_max * (1 - rho / rho_max).

    Returns 0 when the segment is at jam density (rho >= rho_max).
    """
    if rho_max <= 0:
        return 0.0
    rho_clamped = min(max(rho, 0.0), rho_max)
    model_speed = u_max_ms * (1.0 - rho_clamped / rho_max)
    min_crawl_speed = config.TRAFFIC_MODEL['min_crawl_speed_ms']
    return max(model_speed, min_crawl_speed)


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


def edge_state(u: int, v: int, density_map: TrafficDensityMap) -> dict:
    """Return dashboard/log-friendly state for one edge at the current density."""
    occupancy = density_map.get_density(u, v)
    background_occupancy = density_map.get_background_density(u, v)
    rho_max = density_map.get_rho_max(u, v)
    length_m = density_map.get_length(u, v)
    max_speed_ms = density_map.get_u_max_ms(u, v)
    travel_time_s = edge_travel_time(u, v, density_map)
    if travel_time_s and travel_time_s != float('inf'):
        speed_ms = length_m / travel_time_s
    else:
        speed_ms = 0.0
    if rho_max and rho_max != float('inf'):
        congestion_ratio = occupancy / rho_max
    else:
        congestion_ratio = 0.0
    if max_speed_ms is None:
        max_speed_ms = 0.0
    return {
        'occupancy': occupancy,
        'background_occupancy': background_occupancy,
        'rho_max': rho_max,
        'congestion_ratio': congestion_ratio,
        'speed_ms': speed_ms,
        "max_speed_ms": max_speed_ms,
        'length_m': length_m,
    }


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
    linear interpolation. Each hour-boundary B has a ramp window
    [B - interpolate/2, B + interpolate/2] going hour-(B/3600 - 1) -> hour-(B/3600).
    Outside any window the value is flat at the surrounding plateau hour.

    This version is robust to a simulation start time that lands mid-ramp: the initial
    density is seeded at the correct interpolated value, and the loop finishes only the
    remainder of the window it starts inside.

    Two road types are treated differently:
      - N-roads (ref 'N35' or 'N348'): major state roads; use the flow density directly.
      - All other roads: local roads; flow density is scaled down by N_local, a config
        factor expressing what fraction of N-road traffic also loads the local network.
    """
    interpolate = config.ROAD_NETWORK['Interpolate']
    convert_N_local = config.ROAD_NETWORK['N_local']
    flow = pd.read_csv('INPUT_Data_Files/ROAD_DATA/flow_2_3_avg.csv')['Avg Saturday (all det)']
    t_start = config.SIMULATION['EventStartTime']
    t_end = config.SIMULATION['EventEndingTime']

    def edge_background_counts(data):
        """Convert hourly road flow [veh/h] into vehicles present on this edge."""
        u_max_ms = data.get('u_max_ms', config.TRAFFIC_MODEL['speed_fallback'] / 3.6)
        length_km = data.get('length', 0.0) / 1000.0
        if u_max_ms <= 0 or length_km <= 0:
            return flow * 0.0
        return (flow / (u_max_ms * 3.6)) * length_km

    def clamp_hour(h):
        """Keep an hour index inside the valid range of the flow array."""
        return max(0, min(h, len(flow) - 1))

    def interpolated_value(now, flow_count, ref):
        """Return the correct background vehicle count for one edge at absolute time `now`.

        Inside a ramp window centred on the nearest hour boundary: blend linearly from
        current_hour -> next_hour. On a plateau: hold the flat hour value.
        Applies N_local scaling for non-N-roads.
        """
        boundary = round(now / 3600) * 3600     # nearest hour boundary in seconds
        delta = now - boundary                  # signed offset from that boundary [s]

        if abs(delta) <= interpolate / 2:
            # inside a ramp window centred on this boundary
            next_hour = clamp_hour(int(boundary // 3600))
            current_hour = clamp_hour(int(boundary // 3600) - 1)
            t = interpolate / 2 + delta         # 0 at window start, interpolate at window end
            frac = t / interpolate
        else:
            # on a plateau: hold whichever hour we're sitting in
            plateau_hour = clamp_hour(int(boundary // 3600) if delta >= 0 else int(boundary // 3600) - 1)
            current_hour = next_hour = plateau_hour
            frac = 0.0

        value = flow_count[current_hour] + (flow_count[next_hour] - flow_count[current_hour]) * frac
        if ref not in ('N35', 'N348'):
            value *= convert_N_local
        return value

    # --- Initial density: correct even if t_start lands mid-ramp ---
    for u, v, data in G.edges(data=True):
        ref = data.get('ref', None)
        flow_count = edge_background_counts(data)
        density_map.set_rho_background(u, v, interpolated_value(t_start, flow_count, ref))

    while True:
        boundary = round(env.now / 3600) * 3600     # nearest hour boundary to current sim time
        delta = env.now - boundary

        # Decide which ramp window to process next.
        if abs(delta) < interpolate / 2:
            # Already inside this boundary's window: finish the remainder of THIS window.
            target_boundary = boundary
        else:
            # On a plateau: next window belongs to the upcoming boundary.
            target_boundary = boundary + 3600 if delta >= interpolate / 2 else boundary
            window_start = target_boundary - interpolate / 2
            if window_start > env.now:
                yield env.timeout(window_start - env.now)   # sleep until window start

        next_hour = int(target_boundary // 3600)
        current_hour = next_hour - 1

        # Stop if this window's start falls at or after simulation end.
        if (target_boundary - interpolate / 2) >= t_end:
            break
        # Stop once we'd index past the last hour the flow data covers.
        if next_hour >= len(flow):
            break

        current_hour = clamp_hour(current_hour)
        next_hour = clamp_hour(next_hour)

        # Step through the window every 60 s from wherever we currently are.
        window_end = target_boundary + interpolate / 2
        while env.now < window_end:
            t = interpolate / 2 + (env.now - target_boundary)  # elapsed in window [s]
            frac = t / interpolate
            for u, v, data in G.edges(data=True):
                ref = data.get('ref', None)
                flow_count = edge_background_counts(data)
                rho_background_value = (flow_count[current_hour] +
                                        (flow_count[next_hour] - flow_count[current_hour]) * frac)
                if ref not in ('N35', 'N348'):
                    rho_background_value *= convert_N_local
                density_map.set_rho_background(u, v, rho_background_value)

            step = min(60, window_end - env.now)    # don't overshoot the window end
            if step <= 0:
                break
            yield env.timeout(step)
    

# Module-level shared density map used across the simulation
traffic_density = TrafficDensityMap()
