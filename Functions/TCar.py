#The TCar class
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
        self.departed_event = env.event()
        self.parking_lot_node = config.ROAD_NETWORK['Parkinglot']
        self.max_wait_time = config.CAR['MaxWaitTime']
        carcap_dist = config.CAR['CarCapacityDistribution']
        carcap_low = carcap_dist['low']
        carcap_high = carcap_dist['high']

        #Initialize capacity resource
        self.passenger_capacity = np.random.randint(carcap_low, carcap_high+1) 
        
        self.process = env.process(self.run())

    def board_visitors(self):
        deadline = self.env.now + self.max_wait_time
        while len(self.passengers) < self.passenger_capacity:
            if len(self.carqueues[self.source].items) > 0:
                visitor = yield self.carqueues[self.source].get()
                self.passengers.append(visitor)
                continue

            remaining = deadline - self.env.now
            if remaining <= 0:
                break

            get = self.carqueues[self.source].get()
            result = yield get | self.env.timeout(remaining)
            if get in result:
                self.passengers.append(result[get])
            else:
                get.cancel()
                break


    def run(self):
        yield from self.board_visitors()
        self.departed_event.succeed()
        if not self.passengers:
            return

        self.path = shortest_path(self.G, self.source, self.parking_lot_node , self.density_map)
        for u, v in zip(self.path[:-1], self.path[1:]):
            travel_time = edge_travel_time(u, v, self.density_map)
            self.density_map.update_density(u, v, 1) # Increment density for this edge
            yield self.env.timeout(travel_time)
            self.density_map.update_density(u, v, -1) # Decrement density after traversing

        yield self.parking_lot.request()

        for visitor in self.passengers:
            visitor.reactivate()
        
            
