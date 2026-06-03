#The TShuttleBus class (PDL: TShuttleBus)
import simpy


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

    DRIVE_TIME_PLACEHOLDER = 300  # seconds, fixed one-way station <-> festival

    def __init__(self, env, config):
        self.env = env
        self.config = config

        # Shared boarding queue at the shuttle stop (PDL: MyBusQueue)
        self.queue = simpy.Store(env)
        config.SHUTTLE_BUS['MyBusQueue'] = self.queue

        self.capacity = config.SHUTTLE_BUS['capacity']
        self.max_wait = config.SHUTTLE_BUS['MaxWaitTime']
        self.boarding_time = config.SHUTTLE_BUS['BoardingTimePerPassenger']
        self.alighting_time = config.SHUTTLE_BUS['AlightingTimePerPassenger']
        # PCU equivalent for traffic density; used once road-network routing exists
        self.bus_equivalent = config.TRAFFIC_MODEL['bus_equivalent']

        # Output: (bus_id, trip_index, duration) per completed festival-bound trip
        self.trip_lengths = []

        n_buses = config.SHUTTLE_BUS['n_buses']
        self.processes = [env.process(self.run(bus_id)) for bus_id in range(n_buses)]

    def _board(self):
        """Collect up to capacity passengers, or stop after MaxWaitTime.

        Mirrors the PDL Standby loop. Per the PDL, boarding time is measured
        from when boarding started, so time already spent waiting for passengers
        counts toward it (a bus that filled slowly needs no extra boarding wait).
        Returns the list of boarded visitors.
        """
        passengers = []
        wait_start = self.env.now
        deadline = wait_start + self.max_wait
        while len(passengers) < self.capacity:
            if len(self.queue.items) > 0:
                visitor = yield self.queue.get()       # FirstOfQueue + LeaveQueue
                passengers.append(visitor)
                continue
            remaining = deadline - self.env.now
            if remaining <= 0:
                break                                  # depart even if not full
            get = self.queue.get()
            result = yield get | self.env.timeout(remaining)
            if get in result:
                passengers.append(result[get])
            else:
                get.cancel()  # release the pending get so it can't grab a visitor later
                break

        boarding_done = wait_start + len(passengers) * self.boarding_time
        yield self.env.timeout(max(0, boarding_done - self.env.now))
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
            depart = self.env.now
            yield self.env.timeout(self.DRIVE_TIME_PLACEHOLDER)
            arrive = self.env.now
            self.trip_lengths.append((bus_id, trip_index, arrive - depart))
            trip_index += 1

            # --- discharge passengers at the festival parking area ---
            yield self.env.timeout(len(passengers) * self.alighting_time)
            for visitor in passengers:
                visitor.reactivate()  # visitor walks on to the ticket scan

            # --- drive back to the station, empty (PLACEHOLDER) ---
            yield self.env.timeout(self.DRIVE_TIME_PLACEHOLDER)
