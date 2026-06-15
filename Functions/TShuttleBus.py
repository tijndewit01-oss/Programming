"""TShuttleBus: shuttle fleet carrying public-transport visitors to the festival."""
from Functions.Trafficflowmodel import shortest_path, edge_travel_time, edge_state
import config

class TShuttleBus:
    """A fleet of shuttle buses running between the NS station and the festival.

    Each bus repeats a cycle: board visitors at the station (until full or until
    MaxWaitTime elapses), drive to the festival over the live road network,
    release passengers, then drive back empty and start again. Empty trips are
    skipped so a bus with no passengers simply keeps waiting.

    SHUTTLE_BUS['n_buses'] identical bus processes share the single boarding
    queue created in main.py. Passengers "passivate" while riding and are
    reactivated on arrival so they walk on to the ticket scan.
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

        # One process per bus; bus IDs are 1-based.
        n_buses = config.SHUTTLE_BUS['n_buses']
        self.processes = [env.process(self.run(bus_id + 1)) for bus_id in range(n_buses)]

    def _board(self):
        """Board up to capacity passengers, departing early after MaxWaitTime.

        A boarding-time delay is incurred for each passenger as they board; once
        the bus is full or the wait deadline is reached it drives away with
        whoever is aboard. Returns the list of boarded visitors.
        """
        passengers = []
        wait_start = self.env.now
        deadline = wait_start + self.max_wait
        while len(passengers) < self.capacity:
            # Fast path: a visitor is already queued, so board them now.
            if len(self.busqueue.items) > 0:
                visitor = yield self.busqueue.get()
                visitor.set_state('in_bus', 'bus')
                self._log_queue(len(self.busqueue.items), 'dequeue', visitor.visitor_id)
                yield self.env.timeout(self.boarding_time)
                passengers.append(visitor)
                continue
            # Otherwise wait for one, bounded by the remaining deadline.
            remaining = deadline - self.env.now
            if remaining <= 0:
                break  # Deadline reached: depart even if not full.
            # Race a queued arrival against the timeout to see which fired.
            get = self.busqueue.get()
            result = yield get | self.env.timeout(remaining)
            if get in result:
                result[get].set_state('in_bus', 'bus')
                self._log_queue(len(self.busqueue.items), 'dequeue', result[get].visitor_id)
                yield self.env.timeout(self.boarding_time)
                passengers.append(result[get])
            else:
                get.cancel()  # Cancel the pending get so it cannot grab a later visitor.
                break
        return passengers

    def run(self, bus_id):
        """Run one bus forever: board, drive out, unload, drive back, repeat."""
        trip_id = 0
        while True:
            # --- boarding phase at the station ---
            passengers = yield from self._board()

            # Skip empty trips: a bus with no passengers keeps waiting at the
            # station rather than driving an empty round trip that would only
            # add noise to the trip log.
            if not passengers:
                continue

            # --- drive to the festival over the live road network ---
            trip_id += 1
            depart_time = self.env.now
            path = shortest_path(self.G, self.source, self.destination, self.density_map)
            outbound_distance_m = self._path_length(path)
            for u, v in zip(path[:-1], path[1:]):
                travel_time = edge_travel_time(u, v, self.density_map)
                self.density_map.update_density(u, v, self.bus_equivalent)  # Bus occupies the edge.
                self._log_segment('enter', bus_id, u, v)
                yield self.env.timeout(travel_time)
                self.density_map.update_density(u, v, -self.bus_equivalent)  # Bus clears the edge.
                self._log_segment('exit', bus_id, u, v)

            arrival_time = self.env.now

            # --- discharge passengers at the festival parking area ---
            for visitor in passengers:
                yield self.env.timeout(self.alighting_time)
                visitor.reactivate()  # Visitor walks on to the ticket scan.

            # --- drive back to the station, empty ---
            return_depart_time = self.env.now
            path = shortest_path(self.G, self.destination, self.source, self.density_map)
            return_distance_m = self._path_length(path)
            for u, v in zip(path[:-1], path[1:]):
                travel_time = edge_travel_time(u, v, self.density_map)
                self.density_map.update_density(u, v, self.bus_equivalent)  # Bus occupies the edge.
                self._log_segment('enter_return', bus_id, u, v)
                yield self.env.timeout(travel_time)
                self.density_map.update_density(u, v, -self.bus_equivalent)  # Bus clears the edge.
                self._log_segment('exit_return', bus_id, u, v)

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
        """Log a shuttle-queue enqueue/dequeue event, if logging is on."""
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
        """Return the total length [m] of a node-ID path summed over its edges."""
        return sum(
            self.density_map.get_length(u, v) or 0
            for u, v in zip(path[:-1], path[1:])
        )

    def _log_segment(self, event_type, bus_id, u, v):
        """Log a bus entering or leaving road edge (u,v), if logging is on."""
        if not self.logger:
            return
        state = edge_state(u, v, self.density_map)
        self.logger.log_segment_density(
            sim_time=self.env.now,
            event_type=event_type,
            actor_type='bus',
            actor_id=bus_id,
            u=u,
            v=v,
            segment_id=f"{u}->{v}",
            **state,
        )
