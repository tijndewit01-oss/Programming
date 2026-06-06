#The TCar class
import simpy
import numpy as np
from Functions.Trafficflowmodel import shortest_path, edge_travel_time
import config



class TCar:

    def __init__(self, env, G, source, density_map, parking_lot,carqueues):
        self.env = env
        self.G = G
        self.source = source
        self.density_map = density_map
        self.parking_lot = parking_lot
        self.carqueues = carqueues
        self.passengers = []
        self.car_full_event = env.event()
        self.departed_event = env.event()
        self.parking_lot_node = config.ROAD_NETWORK['Parkinglot']
        self.max_wait_time = config.CAR['MaxWaitTime']
        carcap_low = config.CAR['CarCapacityDistribution']['low']
        carcap_high = config.CAR['CarCapacityDistribution']['high']

        #Initialize capacity resource
        self.passenger_capacity = np.random.randint(carcap_low, carcap_high+1) 
        
        self.process = env.process(self.run())

    def board_visitors(self):
        while len(self.passengers) < self.passenger_capacity:
            try:
                visitor = yield self.carqueues[self.source].get()
            except simpy.Interrupt:
                break
            self.passengers.append(visitor)
        self.car_full_event.succeed()


    def run(self):
        boarding = self.env.process(self.board_visitors())
        yield simpy.AnyOf(self.env, 
            [self.env.timeout(self.max_wait_time), # and not empty,
            self.car_full_event])
        if not boarding.processed:
            boarding.interrupt()
        self.departed_event.succeed()
        if not self.passengers:
            return

        self.path = shortest_path(self.G, self.source, self.parking_lot_node , self.density_map)
        for u, v in zip(self.path[:-1], self.path[1:]):
            self.density_map.update_density(u, v, 1) # Increment density for this edge
            travel_time = edge_travel_time(u, v, self.density_map)
            yield self.env.timeout(travel_time)
            self.density_map.update_density(u, v, -1) # Decrement density after traversing

        yield self.parking_lot.request()

        for visitor in self.passengers:
            visitor.reactivate()
        
            