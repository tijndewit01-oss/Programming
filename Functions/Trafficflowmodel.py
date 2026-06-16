"""Traffic-flow model: shared road density state and density-dependent routing.

This module holds the live state of every road segment and the maths that turns
that state into speeds, travel times and routes:

  - TrafficDensityMap stores per-edge occupancy (simulated + background) and the
    fixed properties (jam density, free-flow speed, length) needed to score it.
  - The Greenshields model converts occupancy into a speed, and hence into a
    travel time used as the edge weight for shortest-path routing.
  - background_density_update is a SimPy process that injects real-world traffic
    from measured hourly flow data, smoothed across hour boundaries.

All vehicles (cars and buses) share one TrafficDensityMap instance so they
mutually influence each other's travel times.
"""

import os
import sys
import pandas as pd
from typing import Dict, Tuple

import networkx as nx

# Make the project root importable so config.py loads regardless of launch dir
# (this file lives one directory below the root).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

EdgeKey = Tuple[int, int]  # Directed edge identifier: (upstream node, downstream node).



class TrafficDensityMap:
    """Mutable density state shared by every road segment in the simulation.

    Each edge is keyed by its (u, v) node-ID pair, matching the OSMnx graph.
    Alongside the live occupancy, every edge's fixed properties (jam density,
    free-flow speed, length) are stored here too, so a travel-time query needs
    nothing but this object.
    """

    def __init__(self) -> None:
        # Occupancy contributed by vehicles tracked in the simulation [vehicles].
        self._density: Dict[EdgeKey, float] = {}
        # Jam density: maximum vehicle-equivalents that fit on the edge.
        self._rho_max: Dict[EdgeKey, float] = {}
        # Free-flow speed: speed on a completely empty edge [m/s].
        self._u_max_ms: Dict[EdgeKey, float] = {}
        # Physical length of the edge [m].
        self._length: Dict[EdgeKey, float] = {}
        # Occupancy contributed by real-world background traffic [vehicles].
        self._rho_background: Dict[EdgeKey, float] = {}

    def init_edge(self, u: int, v: int, rho_max: float, u_max_ms: float, length: float) -> None:
        """Register an edge with its fixed properties; occupancy starts at 0."""
        key = (u, v)
        self._rho_max[key] = rho_max
        self._u_max_ms[key] = u_max_ms
        self._length[key] = length
        # setdefault only writes the value if the key is absent, so any density
        # already on this edge is preserved if the edge is re-initialised.
        self._density.setdefault(key, 0.0)  # Keep any density already recorded for this edge.
        self._rho_background[key] = 0.0

    def set_density(self, u: int, v: int, rho: float) -> None:
        """Set the simulated occupancy on edge (u,v), clamped to [0, rho_max].

        Clamping avoids negative occupancy from floating-point rounding when the
        last car leaves, and prevents occupancy from exceeding the jam density.
        """
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._density[key] = max(0.0, min(rho, rho_max))

    def set_rho_background(self, u, v, rho_background):
        """Set the background-traffic occupancy on edge (u,v), clamped to [0, rho_max].

        Background occupancy models real-world vehicles not simulated as agents
        (e.g. regular commuters inferred from loop-detector counts).
        """
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._rho_background[key] = max(0.0, min(float(rho_background), rho_max))

    def get_density(self, u: int, v: int) -> float:
        """Return total occupancy on edge (u,v): simulated plus background.

        Combining both here means every downstream calculation (speed, travel
        time, routing) automatically accounts for real-world congestion.
        """
        return self._density.get((u, v), 0.0) + self._rho_background.get((u,v), 0.0)

    def get_background_density(self, u: int, v: int) -> float:
        """Return only the background-traffic occupancy on edge (u,v)."""
        return self._rho_background.get((u, v), 0.0)

    def get_rho_max(self, u: int, v: int) -> float:
        """Return the jam density of edge (u,v) — the occupancy at which flow stops."""
        return self._rho_max.get((u, v))

    def get_u_max_ms(self, u: int, v: int) -> float:
        """Return the free-flow speed [m/s] of edge (u,v)."""
        return self._u_max_ms.get((u, v))

    def get_length(self, u: int, v: int) -> float:
        """Return the length [m] of edge (u,v)."""
        return self._length.get((u, v))

    def update_density(self, u: int, v: int, delta: float) -> None:
        """Add delta to the simulated occupancy on edge (u,v).

        Use a positive delta when a vehicle enters the edge and a negative delta
        when it leaves; the result is clamped by set_density.
        """
        self.set_density(u, v, self._density.get((u, v), 0) + delta)


def greenshields_speed(rho: float, rho_max: float, u_max_ms: float) -> float:
    """Return speed [m/s] from the Greenshields model: u = u_max * (1 - rho/rho_max).

    Speed falls linearly with occupancy and is floored at min_crawl_speed_ms so
    a jammed edge keeps moving very slowly instead of stopping permanently.
    """
    if rho_max <= 0:
        return 0.0
    rho_clamped = min(max(rho, 0.0), rho_max)
    model_speed = u_max_ms * (1.0 - rho_clamped / rho_max)
    min_crawl_speed = config.TRAFFIC_MODEL['min_crawl_speed_ms']
    return max(model_speed, min_crawl_speed)


def travel_time(length: float, rho: float, rho_max: float, u_max_ms: float) -> float:
    """Return travel time [s] across a segment of the given length and occupancy.

    Returns infinity when the modelled speed is zero (a fully gridlocked edge).
    """
    speed = greenshields_speed(rho, rho_max, u_max_ms)
    if speed <= 0.0:
        return float('inf')
    return length / speed


def edge_travel_time(u: int, v: int, density_map: TrafficDensityMap) -> float:
    """Return the current travel time [s] for edge (u,v), reading state from the map."""
    rho = density_map.get_density(u, v)
    rho_max = density_map.get_rho_max(u, v)
    u_max_ms = density_map.get_u_max_ms(u, v)
    length = density_map.get_length(u, v)
    return travel_time(length, rho, rho_max, u_max_ms)


def edge_state(u: int, v: int, density_map: TrafficDensityMap) -> dict:
    """Return a dict of edge (u,v)'s current state for logging and visualisation."""
    occupancy = density_map.get_density(u, v)
    background_occupancy = density_map.get_background_density(u, v)
    rho_max = density_map.get_rho_max(u, v)
    length_m = density_map.get_length(u, v)
    max_speed_ms = density_map.get_u_max_ms(u, v)
    travel_time_s = edge_travel_time(u, v, density_map)
    # Derive the realised speed from the travel time, guarding against gridlock.
    if travel_time_s and travel_time_s != float('inf'):
        speed_ms = length_m / travel_time_s
    else:
        speed_ms = 0.0
    # Congestion ratio is occupancy as a fraction of jam density (1.0 = jammed).
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


def init_from_graph(G: nx.MultiDiGraph, density_map: TrafficDensityMap) -> TrafficDensityMap:
    """Populate a TrafficDensityMap from an OSMnx graph and return it.

    Each edge is expected to carry 'rho_max' and 'u_max_ms' attributes (added by
    Prepare_network.py); 'u_max_ms' falls back to the configured speed and
    'length' falls back to 0.0 when missing.
    """
    for u, v, data in G.edges(data=True):
        rho_max = data.get('rho_max', float('inf'))
        u_max_ms = data.get('u_max_ms', config.TRAFFIC_MODEL['speed_fallback'] / 3.6) # Fallback speed in m/s.
        length = data.get('length', 0.0)
        density_map.init_edge(u, v, rho_max, u_max_ms, length)
    return density_map




def shortest_path(G: nx.MultiDiGraph, source: int, target: int, density_map: TrafficDensityMap) -> list[int]:
    """Return the fastest route from source to target as a list of node IDs.

    Dijkstra runs with edge weights equal to the current density-dependent
    travel time. Because weights are recomputed on every call, the route adapts
    to whatever congestion exists at that moment in the simulation.
    """
    def weight(u, v, data):
        # Edge weight is the live travel time across the edge.
        return edge_travel_time(u, v, density_map)
    return nx.shortest_path(G, source, target, weight=weight)


def background_density_update(env, G, density_map):
    """SimPy process that keeps background traffic density current on every edge.

    Background density represents real-world (non-simulated) traffic. It comes
    from hourly average vehicle counts (flow_2_3_avg.csv), converted to vehicles
    on an edge via the flow identity density = flow / speed * length.

    To avoid abrupt jumps at the top of each hour, the value ramps linearly over
    a window centred on each hour boundary B, spanning
    [B - interpolate/2, B + interpolate/2] and blending hour (B/3600 - 1) into
    hour (B/3600). Outside any window the value is held flat at the surrounding
    hour's plateau.

    The process is robust to a start time that lands mid-ramp: it seeds the
    initial density at the correct interpolated value, then only finishes the
    remainder of the window it begins inside.

    Two road classes are handled differently:
      - N-roads (ref 'N35'/'N348'): major roads; the flow density is used as-is.
      - Other roads: local roads; the flow density is scaled by N_local.
    """
    interpolate = config.ROAD_NETWORK['Interpolate']
    convert_N_local = config.ROAD_NETWORK['N_local']
    flow = pd.read_csv('INPUT_Data_Files/ROAD_DATA/flow_2_3_avg.csv')['Avg Saturday (all det)']
    t_start = config.SIMULATION['EventStartTime']
    t_end = config.SIMULATION['EventEndingTime']

    def edge_background_counts(data):
        """Convert the hourly flow series [veh/h] into vehicles present on this edge."""
        u_max_ms = data.get('u_max_ms', config.TRAFFIC_MODEL['speed_fallback'] / 3.6)
        length_km = data.get('length', 0.0) / 1000.0
        if u_max_ms <= 0 or length_km <= 0:
            return flow * 0.0
        # density [veh/km] = flow [veh/h] / speed [km/h]; multiply by length [km]
        # to get the vehicle count on the edge. The factor 3.6 converts u_max_ms
        # from m/s to km/h.
        return (flow / (u_max_ms * 3.6)) * length_km

    def clamp_hour(h):
        """Keep an hour index within the bounds of the flow array."""
        return max(0, min(h, len(flow) - 1))

    def interpolated_value(now, flow_count, ref):
        """Return one edge's background vehicle count at absolute time `now`.

        Inside a ramp window centred on the nearest hour boundary, blend linearly
        from the current hour to the next; on a plateau, hold the flat value.
        Non-N-roads are scaled by N_local.
        """
        boundary = round(now / 3600) * 3600     # Nearest hour boundary [s].
        delta = now - boundary                  # Signed offset from that boundary [s].

        if abs(delta) <= interpolate / 2:
            # Inside the ramp window centred on this boundary.
            next_hour = clamp_hour(int(boundary // 3600))
            current_hour = clamp_hour(int(boundary // 3600) - 1)
            t = interpolate / 2 + delta         # 0 at window start, interpolate at window end.
            frac = t / interpolate
        else:
            # On a plateau: hold whichever hour we are currently sitting in.
            plateau_hour = clamp_hour(int(boundary // 3600) if delta >= 0 else int(boundary // 3600) - 1)
            current_hour = next_hour = plateau_hour
            frac = 0.0

        value = flow_count[current_hour] + (flow_count[next_hour] - flow_count[current_hour]) * frac
        if ref not in ('N35', 'N348'):
            value *= convert_N_local
        return value

    # Seed the initial density correctly even if t_start lands mid-ramp.
    for u, v, data in G.edges(data=True):
        ref = data.get('ref', None)
        flow_count = edge_background_counts(data)
        density_map.set_rho_background(u, v, interpolated_value(t_start, flow_count, ref))

    while True:
        boundary = round(env.now / 3600) * 3600     # Nearest hour boundary to the current time.
        delta = env.now - boundary

        # Choose which ramp window to process next.
        if abs(delta) < interpolate / 2:
            # Already inside this boundary's window: finish the remainder of it.
            target_boundary = boundary
        else:
            # On a plateau: the next window belongs to the upcoming boundary.
            target_boundary = boundary + 3600 if delta >= interpolate / 2 else boundary
            window_start = target_boundary - interpolate / 2
            if window_start > env.now:
                yield env.timeout(window_start - env.now)   # Sleep until the window starts.

        next_hour = int(target_boundary // 3600)
        current_hour = next_hour - 1

        # Stop if this window would start at or after the simulation end.
        if (target_boundary - interpolate / 2) >= t_end:
            break
        # Stop once the next hour would index past the available flow data.
        if next_hour >= len(flow):
            break

        current_hour = clamp_hour(current_hour)
        next_hour = clamp_hour(next_hour)

        # Walk through the window in 60 s steps, updating every edge each step.
        window_end = target_boundary + interpolate / 2
        while env.now < window_end:
            # t goes from 0 at the start of the ramp window to `interpolate` at
            # the end, making frac = t / interpolate a 0->1 blend fraction.
            t = interpolate / 2 + (env.now - target_boundary)  # Elapsed time within the window [s].
            frac = t / interpolate
            for u, v, data in G.edges(data=True):
                ref = data.get('ref', None)
                flow_count = edge_background_counts(data)
                rho_background_value = (flow_count[current_hour] +
                                        (flow_count[next_hour] - flow_count[current_hour]) * frac)
                if ref not in ('N35', 'N348'):
                    rho_background_value *= convert_N_local
                density_map.set_rho_background(u, v, rho_background_value)

            step = min(60, window_end - env.now)    # Avoid overshooting the window end.
            if step <= 0:
                break
            yield env.timeout(step)
