import json
import os
import sys
import osmnx as ox
import networkx as nx
import osmium
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pickle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config







G = ox.graph_from_xml("INPUT_Data_Files/network.osm")
# print(type(G))
# print(G.number_of_nodes())
# print(G.number_of_edges())


# ox.plot_graph(G)
# plt.show()


Car_Spacing = config.TRAFFIC_MODEL['Car_Spacing']

for u, v, data in G.edges(data=True):
    length = data.get('length', 0.0)
    lanes_raw = data.get('lanes', 1)
    if isinstance(lanes_raw, list):
        lanes = int(lanes_raw[0])
    else:
        lanes = int(lanes_raw)
    data['rho_max'] = (length / Car_Spacing) * lanes


# save
with open("INPUT_Data_Files/network.pkl", "wb") as f:
    pickle.dump(G, f)
