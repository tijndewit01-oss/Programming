"""Build the routable road graph used by the simulation.

Loads the OSM XML into a NetworkX graph, then annotates every edge with the two
attributes the traffic model needs:
  - u_max_ms: free-flow speed in m/s, taken from the maxspeed tag (falling back
    to the configured default when missing or unparseable).
  - rho_max:  jam density, derived from the edge length, car spacing and number
    of lanes.
The annotated graph is pickled to network.pkl for main.py to load.
"""
import json
import os
import sys
import osmnx as ox
import networkx as nx
import osmium
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pickle


# Make the project root importable so config.py loads regardless of launch dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
min_length = config.ROAD_NETWORK['Min_segment_length']


# Load the OSM network and show it once for a quick visual sanity check.
G = ox.graph_from_xml("INPUT_Data_Files/network.osm")
ox.plot_graph(G)
plt.show()


Car_Spacing = config.TRAFFIC_MODEL['Car_Spacing']

for u, v, data in G.edges(data=True):
    length = data.get('length', 0.0)
    # Two-way edges share their lane count between directions, so halve it.
    # Default True (one-way) when the OSM tag is absent: a deliberate
    # conservative assumption that avoids double-counting lane capacity on
    # untagged edges.
    if not data.get('oneway', True):
        lanes_raw = data.get('lanes', 2)/2
    else:
        lanes_raw = data.get('lanes', 1)
    try:
        # maxspeed may be e.g. "50" or "50 mph"; take the leading number.
        u_max = float(str(data.get('maxspeed', config.TRAFFIC_MODEL['speed_fallback'])).split()[0])
    except (ValueError, TypeError):
        # Catch parse failures on the maxspeed tag (e.g. non-numeric strings).
        u_max = config.TRAFFIC_MODEL['speed_fallback']  # Fall back to the default speed on any parse failure.
    u_max_ms = u_max / 3.6  # Convert kph to m/s.
    data['u_max_ms'] = u_max_ms
    # lanes may come through as a list (OSM allows multiple values); take the first.
    if isinstance(lanes_raw, list):
        lanes = int(lanes_raw[0])
    else:
        lanes = int(lanes_raw)
    # Jam density: how many cars fit bumper-to-bumper across all lanes, using a
    # floor on length so very short edges still hold a sensible number.
    data['rho_max'] = (max(length, min_length) / Car_Spacing) * lanes


# Save the annotated graph for the simulation to load.
with open("INPUT_Data_Files/network.pkl", "wb") as f:
    pickle.dump(G, f)
