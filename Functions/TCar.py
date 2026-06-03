#The TCar class (PDL: TCar)
import simpy
import numpy as np


class TCar:
    """A car that carpools visitors from a spawn node to the parking lot.

    PLACEHOLDER: road-network travel (node-to-node routing, traffic density
    updates) is not yet implemented. Replace the fixed DRIVE_TIME with real
    routing once roadnetwork.py is ready.
    """

    DRIVE_TIME_PLACEHOLDER = 240  # seconds, fixed stand-in for real routing

    def __init__(self, env, config, capacity):
        self.env = env
        self.config = config
        self.CC = capacity        # car capacity in passengers
        self.passengers = []
        self.process = env.process(self.run())

    def run(self):
        pass  # PLACEHOLDER — to be implemented with road-network routing
