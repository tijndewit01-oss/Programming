#The TShuttleBus class (PDL: TShuttleBus)
import simpy
from Functions.Trafficflowmodel import shortest_path, edge_travel_time
import config

class TShuttleBus:
    """Shuttle fleet that transports public-transport visitors from the NS station
    to the festival parking area (PDL: TShuttleBus).

    Each bus repeats: board at the station (until full or MaxWaitTime), drive to
    the festival, release passengers, drive back empty, repeat.

    The PDL describes a single bus. Here we honour SHUTTLE_BUS['n_buses'] by
    running that many bus processes over one shared boarding queue, which is
    created here and registered in config.SHUTTLE_BUS['MyBusQueue'] so visitors
    can reach it (see TVisitor).

    SimPy translation note: the PDL Standby boarding loop is implemented by
    racing a queued arrival against the remaining wait time. Passengers are
    "reactivated" once the bus reaches the festival.

    PLACEHOLDER: road-network travel (node-to-node routing, TrafficDensity /
    BusEquivalent updates, NodeLog) is not yet implemented. The drive phases use
    a fixed DRIVE_TIME until roadnetwork.py (GetRoute / GetDistance) is ready.
    """


    def __init__(self, env, G, density_map, busqueue):
        self.env = env
        self.G = G
        self.density_map = density_map
        self.busqueue = busqueue

        self.capacity = config.SHUTTLE_BUS['capacity']
        self.max_wait = config.SHUTTLE_BUS['MaxWaitTime']
        self.boarding_time = config.SHUTTLE_BUS['BoardingTimePerPassenger']
        self.alighting_time = config.SHUTTLE_BUS['AlightingTimePerPassenger']
        self.bus_equivalent = config.SHUTTLE_BUS['bus_equivalent']
        self.source = config.ROAD_NETWORK['Bus_start']
        self.destination = config.ROAD_NETWORK['Parkinglot']

        n_buses = config.SHUTTLE_BUS['n_buses']
        self.processes = [env.process(self.run(bus_id)) for bus_id in range(n_buses)]

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
                yield self.env.timeout(self.boarding_time)
                passengers.append(visitor)
                continue
            remaining = deadline - self.env.now
            if remaining <= 0:
                break                                  # depart even if not full
            get = self.busqueue.get()
            result = yield get | self.env.timeout(remaining)
            if get in result:
                yield self.env.timeout(self.boarding_time)
                passengers.append(result[get])
            else:
                get.cancel()  # release the pending get so it can't grab a visitor later
                break
        return passengers

    def run(self, bus_id):
        trip_index = 0
        while True:
            # --- boarding phase at the station ---
            passengers = yield from self._board()

            # Deviation from the raw PDL: skip empty trips. A bus with no
            # passengers keeps waiting at the station rather than driving an
            # empty round trip (which would only add noise to the trip log).
            if not passengers:
                continue

            # --- drive to the festival (PLACEHOLDER for road-network routing) ---

            self.path = shortest_path(self.G, self.source, self.destination, self.density_map)
            for u, v in zip(self.path[:-1], self.path[1:]):
                self.density_map.update_density(u, v, self.bus_equivalent) # Increment density for this edge
                travel_time = edge_travel_time(u, v, self.density_map)
                yield self.env.timeout(travel_time)
                self.density_map.update_density(u, v, -self.bus_equivalent) # Decrement density after traversing



            # --- discharge passengers at the festival parking area ---
            for visitor in passengers:
                yield self.env.timeout(self.alighting_time)
                visitor.reactivate()  # visitor walks on to the ticket scan

            # --- drive back to the station, empty (PLACEHOLDER) ---
            self.path = shortest_path(self.G, self.destination, self.source, self.density_map)
            for u, v in zip(self.path[:-1], self.path[1:]):
                self.density_map.update_density(u, v, self.bus_equivalent) # Increment density for this edge
                travel_time = edge_travel_time(u, v, self.density_map)
                yield self.env.timeout(travel_time)
                self.density_map.update_density(u, v, -self.bus_equivalent) # Decrement density after traversing
