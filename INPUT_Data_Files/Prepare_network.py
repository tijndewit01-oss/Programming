import json
import os
import sys
import osmnx as ox
import networkx as nx
import osmium
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pickle
'''
Loads OSM file into NetworkX graph. 
Calculates the rho_max 
Determines the u_max
Saves graph as network.pkl
'''



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
    try:
        u_max = float(str(data.get('maxspeed', config.TRAFFIC_MODEL['speed_fallback'])).split()[0]) #if not specified default to 30 kph
    except:
        u_max = config.TRAFFIC_MODEL['speed_fallback'] # default to 30 kph if conversion fails
    u_max_ms = u_max / 3.6 #convert to m/s
    data['u_max_speed'] = u_max_ms
    if isinstance(lanes_raw, list):
        lanes = int(lanes_raw[0])
    else:
        lanes = int(lanes_raw)
    data['rho_max'] = (length / Car_Spacing) * lanes


# save
with open("INPUT_Data_Files/network.pkl", "wb") as f:
    pickle.dump(G, f)
