# Importing libraries and data
import sympy as sm
import numpy as np
import matplotlib.pyplot as plt


import json

with open("C:\\Users\\tijnd\\OneDrive\\Documenten\\AA WB Delft\\Master\\System analysis\\Programming\\INPUT Data Files\\RoadData.json", "r") as f:
    data = json.load(f)

print(data.keys())
element_types = set(e["type"] for e in data["elements"])
print(element_types)