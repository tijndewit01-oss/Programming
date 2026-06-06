import json
import os
import sys
import osmnx as ox
import networkx as nx
import osmium
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pickle

G = ox.graph_from_xml("INPUT_Data_Files/network.osm")


Node1 = ox.nearest_nodes(G, 6.258743, 52.363001)
Node2 = ox.nearest_nodes(G, 6.265216, 52.361613)
Node3 = ox.nearest_nodes(G, 6.257414, 52.408386)
Node4 = ox.nearest_nodes(G, 6.300448, 52.394650)
Node5 = ox.nearest_nodes(G, 6.309560, 52.381940)
Bus_start = ox.nearest_nodes(G, 6.276720, 52.391536)
Parkinglot = ox.nearest_nodes(G, 6.273370, 52.384528)

nodes_spec = {Node1, Node2, Node3, Node4, Node5, Bus_start, Parkinglot}

node_colors = ["red" if node in nodes_spec else "blue" for node in G.nodes()]

nodes_dict = {
    "Node1": ox.nearest_nodes(G, 6.258743, 52.363001),
    "Node2": ox.nearest_nodes(G, 6.265216, 52.361613),
    "Node3": ox.nearest_nodes(G, 6.257414, 52.408386),
    "Node4": ox.nearest_nodes(G, 6.300448, 52.394650),
    "Node5": ox.nearest_nodes(G, 6.309560, 52.381940),
    "Bus_start": ox.nearest_nodes(G, 6.276720, 52.391536),
    "Parkinglot": ox.nearest_nodes(G, 6.273370, 52.384528),
}
print(nodes_dict)
# ox.plot_graph(G, node_color=node_colors, node_size=30)