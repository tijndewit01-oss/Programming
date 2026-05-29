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

    def init_edge(self, u: int, v: int, rho_max: float) -> None:
        """Register an edge with its capacity; initial density is 0."""
        key = (u, v)
        self._rho_max[key] = rho_max
        self._density.setdefault(key, 0.0)

    def set_density(self, u: int, v: int, rho: float) -> None:
        key = (u, v)
        rho_max = self._rho_max.get(key, float('inf'))
        self._density[key] = max(0.0, min(rho, rho_max))

    def get_density(self, u: int, v: int) -> float:
        return self._density.get((u, v), 0.0)

    def get_rho_max(self, u: int, v: int) -> float:
        return self._rho_max.get((u, v), float('inf'))

    def update_density(self, u: int, v: int, delta: float) -> None:
        self.set_density(u, v, self.get_density(u, v) + delta)


def greenshields_speed(rho: float, rho_max: float, u_max: float = _u_max_default) -> float:
    """Greenshields linear speed-density model: u = u_max * (1 - rho / rho_max).

    Returns 0 when the segment is at jam density (rho >= rho_max).
    """
    if rho_max <= 0:
        return 0.0
    rho_clamped = min(max(rho, 0.0), rho_max)
    return u_max * (1.0 - rho_clamped / rho_max)


def travel_time(length: float, rho: float, rho_max: float, u_max: float = _u_max_default) -> float:
    """Travel time (seconds) for a segment given its length and current density.

    Returns inf when the segment is gridlocked.
    """
    speed = greenshields_speed(rho, rho_max, u_max)
    if speed <= 0.0:
        return float('inf')
    return length / speed


def edge_travel_time(u: int, v: int, length: float,
                     density_map: TrafficDensityMap,
                     u_max: float = _u_max_default) -> float:
    """Convenience wrapper that pulls rho and rho_max from the shared density map."""
    rho = density_map.get_density(u, v)
    rho_max = density_map.get_rho_max(u, v)
    return travel_time(length, rho, rho_max, u_max)


def init_from_graph(G: nx.MultiDiGraph, density_map: "TrafficDensityMap | None" = None) -> TrafficDensityMap:
    """Populate a TrafficDensityMap from an OSMnx graph.

    Each edge must have a 'rho_max' attribute (set by Prepare_network.py).
    If density_map is None, the module-level traffic_density is used.
    """
    target = density_map if density_map is not None else traffic_density
    for u, v, data in G.edges(data=True):
        rho_max = data.get('rho_max', float('inf'))
        target.init_edge(u, v, rho_max)
    return target


# Module-level shared density map used across the simulation
traffic_density = TrafficDensityMap()
