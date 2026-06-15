"""Convert the raw OSM road data from JSON to OSM XML.

The OSM Overpass export (RoadData.json) is rewritten as network.osm, the XML
format OSMnx expects, so Prepare_network.py can load it into a graph.
"""
import json
import osmnx as ox
import networkx as nx
import osmium
import xml.etree.ElementTree as ET


def osm_json_to_xml(json_path, xml_path):
    """Read an OSM-JSON export and write the equivalent OSM XML file.

    Each node and way element, along with its tags, is translated into the
    corresponding OSM XML element.
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    root = ET.Element("osm", version="0.6")

    for element in data["elements"]:
        # Nodes carry coordinates and optional tags.
        if element["type"] == "node":
            node = ET.SubElement(root, "node", {
                "id": str(element["id"]),
                "lat": str(element["lat"]),
                "lon": str(element["lon"])
            })
            for k, v in element.get("tags", {}).items():
                ET.SubElement(node, "tag", k=k, v=v)

        # Ways reference an ordered list of node IDs plus optional tags.
        elif element["type"] == "way":
            way = ET.SubElement(root, "way", {"id": str(element["id"])})
            for nd in element.get("nodes", []):
                ET.SubElement(way, "nd", ref=str(nd))
            for k, v in element.get("tags", {}).items():
                ET.SubElement(way, "tag", k=k, v=v)

    ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=True)

osm_json_to_xml("INPUT_Data_Files/RoadData.json", "INPUT_Data_Files/network.osm")
