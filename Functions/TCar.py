#The TCar class
import numpy as np
from Functions.Trafficflowmodel import shortest_path, edge_travel_time
import config



class TCar:

    def __init__(
        self,
        env,
        G,
        source,
        density_map,
        parking_lot,
        parking_entry,
        carqueues,
        car_id=None,
        logger=None,
    ):
        self.env = env
        self.G = G
        self.source = source
        self.density_map = density_map
        self.parking_lot = parking_lot
        self.parking_entry = parking_entry
        self.carqueues = carqueues
        self.car_id = car_id
        self.logger = logger
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
                visitor.set_state('in_car', self.source)
                self._log_queue(len(self.carqueues[self.source].items), 'dequeue', visitor.visitor_id)
                continue

            remaining = deadline - self.env.now
            if remaining <= 0:
                break

            get = self.carqueues[self.source].get()
            result = yield get | self.env.timeout(remaining)
            if get in result:
                self.passengers.append(result[get])
                result[get].set_state('in_car', self.source)
                self._log_queue(len(self.carqueues[self.source].items), 'dequeue', result[get].visitor_id)
            else:
                get.cancel()
                break


    def run(self):
        yield from self.board_visitors()
        self.departed_event.succeed()
        if not self.passengers:
            return

        depart_time = self.env.now
        self.path = shortest_path(self.G, self.source, self.parking_lot_node, self.density_map)
        route_length_m = sum(
            self.density_map.get_length(u, v) or 0
            for u, v in zip(self.path[:-1], self.path[1:])
        )

        edges = list(zip(self.path[:-1], self.path[1:]))
        for i, (u, v) in enumerate(edges):
            is_last = (i == len(edges) - 1)
            travel_time = edge_travel_time(u, v, self.density_map)
            self.density_map.update_density(u, v, 1)  # Enter segment
            yield self.env.timeout(travel_time)
            if not is_last:
                self.density_map.update_density(u, v, -1)  # Leave segment
            # Last segment is intentionally NOT decremented here: the car is now
            # physically queued on the final road segment waiting to enter parking.

        road_arrival_time = self.env.now
        parking_entry_request_time = self.env.now
        with self.parking_entry.request() as entry_request:
            self._log_parking_queue('parking_entry_queue', len(self.parking_entry.queue), 'enqueue')
            yield entry_request
            parking_entry_start_time = self.env.now
            # Admitted to an entry lane -> car pulls off the through road now.
            if edges:
                last_u, last_v = edges[-1]
                self.density_map.update_density(last_u, last_v, -1)
            self._log_parking_queue('parking_entry_queue', len(self.parking_entry.queue), 'dequeue')
            parking_entry_service = config.CAR['ParkingLotEntryDelay']()
            yield self.env.timeout(parking_entry_service)

        self.parking_lot_request = self.parking_lot.request()
        yield self.parking_lot_request
        self._log_parking_queue('parking_lot_occupancy', self.parking_lot.count, 'occupancy')
        for visitor in self.passengers:
            visitor.set_state('parking', 'parking_lot')
        find_space_time = config.CAR['FindSpaceParkCar']
        yield self.env.timeout(find_space_time)

        parked_time = self.env.now
        if self.logger:
            self.logger.log_car(
                car_id=self.car_id,
                source_node=self.source,
                capacity=self.passenger_capacity,
                passenger_count=len(self.passengers),
                depart_time=depart_time,
                road_arrival_time=road_arrival_time,
                parked_time=parked_time,
                drive_time=road_arrival_time - depart_time,
                parking_entry_wait=parking_entry_start_time - parking_entry_request_time,
                parking_entry_service=parking_entry_service,
                find_space_time=find_space_time,
                route_length_m=route_length_m,
            )

        for visitor in self.passengers:
            visitor.reactivate()




    def _log_queue(self, length, event_type, visitor_id):
        if not self.logger:
            return
        self.logger.log_queue(
            sim_time=self.env.now,
            queue_name=f"car_queue_{self.source}",
            location=self.source,
            length=length,
            event_type=event_type,
            actor_type='visitor',
            actor_id=visitor_id,
        )

    def _log_parking_queue(self, queue_name, length, event_type):
        if not self.logger:
            return
        self.logger.log_queue(
            sim_time=self.env.now,
            queue_name=queue_name,
            location='parking_lot',
            length=length,
            event_type=event_type,
            actor_type='car',
            actor_id=self.car_id,
        )

