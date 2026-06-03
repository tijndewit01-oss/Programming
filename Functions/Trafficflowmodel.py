import os
import sys
from typing import Dict, Tuple

import networkx as nx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

EdgeKey = Tuple[int, int]  # (u, v) node IDs

_u_max_default: float = config.TRAFFIC_MODEL['u_max']


class TrafficDensityMap:
    """Shared mutable density state for all road segments.

    Keyed by (u, v) node-ID pairs matching the OSMnx graph edges.
    rho_max per edge is stored alongside density so travel-time queries
    are self-contained.
    """

    def __init__(self) -> None:
        self._density: Dict[EdgeKey, float] = {}
        self._rho_max: Dict[EdgeKey, float] = {}
        self._u_max_ms: Dict[EdgeKey, float] = {}

    def init_edge(self, u: int, v: int, rho_max: float, u_max_ms: float) -> None:
        """Register an edge with its capacity; initial density is 0."""
        key = (u, v)
        self._rho_max[key] = rho_max
        self._u_max_ms[key] = u_max_ms
        self._density.setdefault(key, 0.0)

    def set_density(self, u: int, v: int, rho: float) -> None:
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._density[key] = max(0.0, min(rho, rho_max))

    def get_density(self, u: int, v: int) -> float:
        return self._density.get((u, v), 0.0)

    def get_rho_max(self, u: int, v: int) -> float:
        return self._rho_max.get((u, v), float('inf'))
    
    def get_u_max_ms(self, u: int, v: int) -> float:
        return self._u_max_ms.get((u, v), _u_max_default)

    def update_density(self, u: int, v: int, delta: float) -> None:
        self.set_density(u, v, self.get_density(u, v) + delta)


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


def travel_time(length: float, rho: float, rho_max: float, u_max_ms: float = _u_max_default) -> float:
    """Travel time (seconds) for a segment given its length and current density.

    Returns inf when the segment is gridlocked.
    """
    speed = greenshields_speed(rho, rho_max, u_max_ms)
    if speed <= 0.0:
        return float('inf')
    return length / speed


def edge_travel_time(u: int, v: int, length: float,
                     density_map: TrafficDensityMap) -> float:
    """Convenience wrapper that pulls rho and rho_max from the shared density map."""
    rho = density_map.get_density(u, v)
    rho_max = density_map.get_rho_max(u, v)
    u_max_ms = density_map.get_u_max_ms(u, v)
    return travel_time(length, rho, rho_max, u_max_ms)


def init_from_graph(G: nx.MultiDiGraph, density_map: "TrafficDensityMap | None" = None) -> TrafficDensityMap:
    """Populate a TrafficDensityMap from an OSMnx graph.

    Each edge must have a 'rho_max' attribute (set by Prepare_network.py).
    If density_map is None, the module-level traffic_density is used.
    """
    target = density_map if density_map is not None else traffic_density
    for u, v, data in G.edges(data=True):
        rho_max = data.get('rho_max', float('inf'))
        u_max_ms = data.get('u_max_ms', config.TRAFFIC_MODEL['speed_fallback'] / 3.6) # default to fallback speed in m/s
        target.init_edge(u, v, rho_max, u_max_ms)
    return target


def weight_func():
    


# Module-level shared density map used across the simulation
traffic_density = TrafficDensityMap()
