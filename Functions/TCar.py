#The TCar class
import simpy
import numpy as np
from Functions.Trafficflowmodel import shortest_path, edge_travel_time
import config



class TCar:

    def __init__(self, env, G, source, density_map, parking_lot):
        self.env = env
        self.G = G
        self.source = source
        self.density_map = density_map
        self.parking_lot = parking_lot
        self.car_full_event = env.event()

        #Initialize capacity resource
        self.passenger_resource = simpy.Resource(env, np.random.randint(
            config.CAR['CarCapacityDistribution']['low'], config.CAR['CarCapacityDistribution']['high']+1)) 
        
        self.process = env.process(self.run())


    def run(self):
        yield simpy.AnyOf(self.env, 
            [self.env.timeout(config.CAR['max_wait_time']),
            self.car_full_event])
        self.path = shortest_path(self.G, self.source, config.ROAD_NETWORK['ParkingLotNode'], self.density_map)
        for u, v in zip(self.path[:-1], self.path[1:]):
            self.density_map.update_density(u, v, 1) # Increment density for this edge
            travel_time = edge_travel_time(u, v, self.density_map)
            yield self.env.timeout(travel_time)
            self.density_map.update_density(u, v, -1) # Decrement density after traversing

        yield self.parking_lot.request()
        
            