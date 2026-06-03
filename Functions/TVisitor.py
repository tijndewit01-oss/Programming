import numpy as np
#Creates the TVisitor class


class TVisitor:
    """A single festival visitor entity (PDL: TVisitor).

    A visitor picks a transport mode, then moves through the system:
      - public transport: walk to the shuttle stop -> shuttle bus -> ticket scan
      - car: carpool queue -> car -> ticket scan

    SimPy translation note: the PDL uses Passivate / Reactivate. Here a visitor
    "passivates" by yielding a one-shot event (self._wake); the consuming
    component (car, shuttle bus, or ticket scan) calls self.reactivate() to
    wake it again.

    Queue dependencies (set up by the other components when they are built):
      - config.CAR['MyCarQueue']        : car carpool queue   (TCarGenerator/TCar)
      - config.SHUTTLE_BUS['MyBusQueue'] : shuttle stop queue  (TShuttleBus)
      - config.TICKET_SCAN['MyQueue']    : ticket scan queue   (TTicketScan)
    These should be simpy.Store instances created once the SimPy env exists.
    """

    def __init__(self, env, config):
        self.env = env
        self.config = config

        #Determine the mode of transport for the visitor based on the mode split in config
        mode_split = config.VISITOR_GENERATOR['ModeSplit']
        self.mode = np.random.choice(list(mode_split.keys()), p=list(mode_split.values()))

        #Determine start node if mode is car
        if self.mode == 'car':
            start_node_split = config.VISITOR_GENERATOR['CarStartNodeProb']
            self.start_node = np.random.choice(list(start_node_split.keys()), p=list(start_node_split.values()))
        else:
            self.start_node = config.VISITOR_GENERATOR['BusStartNodeProb']

        # PDL attributes
        self.depart_time = env.now   # DepartTime = Now
        self.arrival_time = None     # ArrivalTime, set when the visitor exits the system

        # Reactivation event (replaces PDL Passivate / Reactivate)
        self._wake = env.event()

        self.process = env.process(self.run())

    def reactivate(self):
        """Wake this visitor after it has passivated (PDL: Reactivate)."""
        if not self._wake.triggered:
            self._wake.succeed()

    def run(self):
        # --- get to the parking area / drop-off, depending on mode ---
        if self.mode != 'car':
            # Public transport: walk to the shuttle stop and queue for the bus
            yield self.env.timeout(self.config.VISITOR['WalkToShuttlebus'])
            self.config.SHUTTLE_BUS['MyBusQueue'].put(self)   # EnterQueue
            yield self._wake                                  # Passivate; bus reactivates
            self._wake = self.env.event()
        else:
            # Car: join the carpool queue and wait until the car has parked
            self.config.CAR['MyCarQueue'].put(self)           # EnterQueue
            yield self._wake                                  # Passivate; car reactivates
            self._wake = self.env.event()

        # --- both modes merge here: walk to the ticket scan and get scanned ---
        yield self.env.timeout(self.config.VISITOR['WalkToTicketScan'])
        self.config.TICKET_SCAN['MyQueue'].put(self)          # EnterQueue
        yield self._wake                                      # Passivate; scanner reactivates

        # ArrivalTime = Now (visitor has passed the festival entrance)
        self.arrival_time = self.env.now
