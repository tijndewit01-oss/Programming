#The TShuttleBus class (PDL: TShuttleBus)
from Functions.Trafficflowmodel import shortest_path, edge_travel_time
import config

class TShuttleBus:
    """Shuttle fleet that transports public-transport visitors from the NS station
    to the festival parking area (PDL: TShuttleBus).

    Each bus repeats: board at the station (until full or MaxWaitTime), drive to
    the festival, release passengers, drive back empty, repeat.

    The PDL describes a single bus. Here we honour SHUTTLE_BUS['n_buses'] by
    running that many bus processes over one shared boarding queue injected by
    main.py.

    SimPy translation note: the PDL Standby boarding loop is implemented by
    racing a queued arrival against the remaining wait time. Passengers are
    "reactivated" once the bus reaches the festival.

    Road-network travel is routed dynamically over the OSMnx graph using the
    shared density map.
    """


    def __init__(self, env, G, density_map, busqueue, logger=None):
        self.env = env
        self.G = G
        self.density_map = density_map
        self.busqueue = busqueue
        self.logger = logger

        self.capacity = config.SHUTTLE_BUS['capacity']
        self.max_wait = config.SHUTTLE_BUS['MaxWaitTime']
        self.boarding_time = config.SHUTTLE_BUS['BoardingTimePerPassenger']
        self.alighting_time = config.SHUTTLE_BUS['AlightingTimePerPassenger']
        self.bus_equivalent = config.SHUTTLE_BUS['bus_equivalent']
        self.source = config.ROAD_NETWORK['Bus_start']
        self.destination = config.ROAD_NETWORK['Parkinglot']

        n_buses = config.SHUTTLE_BUS['n_buses']
        self.processes = [env.process(self.run(bus_id + 1)) for bus_id in range(n_buses)]

    def _board(self):
        """Collect up to capacity passengers, or stop after MaxWaitTime.

        Mirrors the PDL Standby loop. Per the PDL, boarding time is measured
        from when boarding started, so time already spent waiting for passengers
        counts toward it (a bus that filled slowly needs no extra boarding wait).
        Returns the list of boarded visitors.

        Edited to wait the board time everytime a passenger boards. It just drives away after the process is done.
        """
        passengers = []
        wait_start = self.env.now
        deadline = wait_start + self.max_wait
        while len(passengers) < self.capacity:
            if len(self.busqueue.items) > 0:
                visitor = yield self.busqueue.get()       # FirstOfQueue + LeaveQueue
                visitor.set_state('in_bus', 'bus')
                self._log_queue(len(self.busqueue.items), 'dequeue', visitor.visitor_id)
                yield self.env.timeout(self.boarding_time)
                passengers.append(visitor)
                continue
            remaining = deadline - self.env.now
            if remaining <= 0:
                break                                  # depart even if not full
            get = self.busqueue.get()
            result = yield get | self.env.timeout(remaining)
            if get in result:
                result[get].set_state('in_bus', 'bus')
                self._log_queue(len(self.busqueue.items), 'dequeue', result[get].visitor_id)
                yield self.env.timeout(self.boarding_time)
                passengers.append(result[get])
            else:
                get.cancel()  # release the pending get so it can't grab a visitor later
                break
        return passengers

    def run(self, bus_id):
        trip_id = 0
        while True:
            # --- boarding phase at the station ---
            passengers = yield from self._board()

            # Deviation from the raw PDL: skip empty trips. A bus with no
            # passengers keeps waiting at the station rather than driving an
            # empty round trip (which would only add noise to the trip log).
            if not passengers:
                continue

            # --- drive to the festival (PLACEHOLDER for road-network routing) ---

            trip_id += 1
            depart_time = self.env.now
            path = shortest_path(self.G, self.source, self.destination, self.density_map)
            outbound_distance_m = self._path_length(path)
            for u, v in zip(path[:-1], path[1:]):
                travel_time = edge_travel_time(u, v, self.density_map)
                self.density_map.update_density(u, v, self.bus_equivalent) # Increment density for this edge
                yield self.env.timeout(travel_time)
                self.density_map.update_density(u, v, -self.bus_equivalent) # Decrement density after traversing

            arrival_time = self.env.now


            # --- discharge passengers at the festival parking area ---
            for visitor in passengers:
                yield self.env.timeout(self.alighting_time)
                visitor.reactivate()  # visitor walks on to the ticket scan

            # --- drive back to the station, empty (PLACEHOLDER) ---
            return_depart_time = self.env.now
            path = shortest_path(self.G, self.destination, self.source, self.density_map)
            return_distance_m = self._path_length(path)
            for u, v in zip(path[:-1], path[1:]):
                travel_time = edge_travel_time(u, v, self.density_map)
                self.density_map.update_density(u, v, self.bus_equivalent) # Increment density for this edge
                yield self.env.timeout(travel_time)
                self.density_map.update_density(u, v, -self.bus_equivalent) # Decrement density after traversing

            return_arrival_time = self.env.now
            if self.logger:
                self.logger.log_bus_trip(
                    bus_id=bus_id,
                    trip_id=trip_id,
                    depart_time=depart_time,
                    arrival_time=arrival_time,
                    return_arrival_time=return_arrival_time,
                    passenger_count=len(passengers),
                    capacity=self.capacity,
                    load_factor=len(passengers) / self.capacity,
                    station_queue_left=len(self.busqueue.items),
                    outbound_drive_time=arrival_time - depart_time,
                    return_drive_time=return_arrival_time - return_depart_time,
                    outbound_distance_m=outbound_distance_m,
                    return_distance_m=return_distance_m,
                )

    def _log_queue(self, length, event_type, visitor_id):
        if not self.logger:
            return
        self.logger.log_queue(
            sim_time=self.env.now,
            queue_name='shuttle_bus_queue',
            location='bus_stop',
            length=length,
            event_type=event_type,
            actor_type='visitor',
            actor_id=visitor_id,
        )

    def _path_length(self, path):
        return sum(
            self.density_map.get_length(u, v) or 0
            for u, v in zip(path[:-1], path[1:])
        )
