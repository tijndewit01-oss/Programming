import numpy as np
import config
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

    Queue dependencies are SimPy Store instances created in main.py and injected
    into the visitor, car, shuttle, and ticket-scan components.
    """

    def __init__(self, env, busqueue, carqueues, ticketqueue, visitor_id=None, logger=None):
        self.env = env
        self.visitor_id = visitor_id
        self.logger = logger

        #Determine the mode of transport for the visitor based on the mode split in config
        mode_split = config.VISITOR_GENERATOR['ModeSplit']
        self.mode = np.random.choice(list(mode_split.keys()), p=list(mode_split.values()))
        walk_speed = config.VISITOR['VisitorWalkSpeed']
        self.shuttlebus_walktime = config.VISITOR['Dist_WalkToShuttlebus'] / walk_speed
        self.ticket_walktime = config.VISITOR['Dist_WalkToTicketScan'] / walk_speed


        self.busqueue = busqueue
        self.carqueues = carqueues
        self.ticketqueue = ticketqueue
        #Determine start node if mode is car
        if self.mode == 'car':
            start_node_prob = config.ROAD_NETWORK['CarStartNodeProb']
            start_node_ids = config.ROAD_NETWORK['StartNodes']
            self.start_node_name = np.random.choice(list(start_node_prob.keys()), p=list(start_node_prob.values()))
            self.start_node = start_node_ids[self.start_node_name]
        else:
            self.start_node_name = 'Bus_start'
            self.start_node = config.ROAD_NETWORK['Bus_start']

        # PDL attributes
        self.depart_time = env.now   # DepartTime = Now
        self.arrival_time = None     # ArrivalTime, set when the visitor exits the system
        self.current_state = 'generated'

        if self.logger:
            self.logger.register_visitor(
                self.visitor_id,
                self.mode,
                self.start_node_name,
                self.start_node,
                self.depart_time,
            )
            self.set_state('generated', self.start_node_name)

        # Reactivation event (replaces PDL Passivate / Reactivate)
        self._wake = env.event()

        self.process = env.process(self.run())

    def reactivate(self):
        """Wake this visitor after it has passivated (PDL: Reactivate)."""
        if not self._wake.triggered:
            self._wake.succeed()

    def set_state(self, state, location=''):
        self.current_state = state
        if self.logger:
            self.logger.log_visitor_state(
                self.visitor_id,
                self.env.now,
                state,
                mode=self.mode,
                location=location,
            )

    def run(self):
        # --- get to the parking area / drop-off, depending on mode ---
        if self.mode != 'car':
            # Public transport: walk to the shuttle stop and queue for the bus
            self.set_state('walking_to_bus', self.start_node_name)
            yield self.env.timeout(self.shuttlebus_walktime)
            self.set_state('waiting_bus', 'bus_stop')
            self.busqueue.put(self)   # EnterQueue
            self._log_queue('shuttle_bus_queue', 'bus_stop', len(self.busqueue.items), 'enqueue')
            yield self._wake                                  # Passivate; bus reactivates
            self._wake = self.env.event()
        else:
            # Car: join the carpool queue and wait until the car has parked
            self.set_state('waiting_car', self.start_node_name)
            self.carqueues[self.start_node].put(self)         # EnterQueue
            self._log_queue(
                f"car_queue_{self.start_node}",
                self.start_node_name,
                len(self.carqueues[self.start_node].items),
                'enqueue',
            )
            yield self._wake                                  # Passivate; car reactivates
            self._wake = self.env.event()

        # --- both modes merge here: walk to the ticket scan and get scanned ---
        self.set_state('walking_ticket', 'parking_area')
        yield self.env.timeout(self.ticket_walktime)
        self.set_state('waiting_ticket', 'ticket_scan')
        self.ticketqueue.put(self)          # EnterQueue
        self._log_queue('ticket_scan_queue', 'ticket_scan', len(self.ticketqueue.items), 'enqueue')
        yield self._wake                                      # Passivate; scanner reactivates

        # ArrivalTime = Now (visitor has passed the festival entrance)
        self.arrival_time = self.env.now
        self.set_state('scanned', 'ticket_scan')
        if self.logger:
            self.logger.complete_visitor(self.visitor_id, self.arrival_time)

    def _log_queue(self, queue_name, location, length, event_type):
        if not self.logger:
            return
        self.logger.log_queue(
            sim_time=self.env.now,
            queue_name=queue_name,
            location=location,
            length=length,
            event_type=event_type,
            actor_type='visitor',
            actor_id=self.visitor_id,
        )
