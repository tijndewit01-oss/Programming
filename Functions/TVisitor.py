"""TVisitor: one festival visitor moving through the transport system."""
import numpy as np
import config


class TVisitor:
    """A single visitor entity that travels from arrival to the ticket scan.

    On creation the visitor picks a transport mode, then runs one of two paths:
      - shuttle: walk to the stop -> wait/ride the shuttle bus -> ticket scan.
      - car:     wait in the carpool queue -> ride the car to parking -> scan.

    While waiting for a car, bus or scanner the visitor "passivates" by yielding
    a one-shot SimPy event (self._wake); the serving component calls
    reactivate() to wake it. All queues are SimPy Stores created in main.py and
    injected here.
    """

    def __init__(self, env, busqueue, carqueues, ticketqueue, visitor_id=None, logger=None):
        self.env = env
        self.visitor_id = visitor_id
        self.logger = logger

        # Choose the transport mode at random from the configured mode split.
        mode_split = config.VISITOR_GENERATOR['ModeSplit']
        self.mode = np.random.choice(list(mode_split.keys()), p=list(mode_split.values()))
        walk_speed = config.VISITOR['VisitorWalkSpeed']
        self.shuttlebus_walktime = config.VISITOR['Dist_WalkToShuttlebus'] / walk_speed
        self.ticket_walktime = config.VISITOR['Dist_WalkToTicketScan'] / walk_speed


        self.busqueue = busqueue
        self.carqueues = carqueues
        self.ticketqueue = ticketqueue
        # Car visitors get a randomly weighted entry node; shuttle visitors all
        # start at the bus stop.
        if self.mode == 'car':
            start_node_prob = config.ROAD_NETWORK['CarStartNodeProb']
            start_node_ids = config.ROAD_NETWORK['StartNodes']
            self.start_node_name = np.random.choice(list(start_node_prob.keys()), p=list(start_node_prob.values()))
            self.start_node = start_node_ids[self.start_node_name]
        else:
            self.start_node_name = 'Bus_start'
            self.start_node = config.ROAD_NETWORK['Bus_start']

        # Timestamps tracking the visitor's life in the system.
        self.depart_time = env.now   # When the visitor entered the simulation.
        self.arrival_time = None     # Set when the visitor finishes the ticket scan.
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

        # One-shot event used to passivate/reactivate this visitor.
        self._wake = env.event()

        self.process = env.process(self.run())

    def reactivate(self):
        """Wake this visitor after it has passivated waiting for a component."""
        if not self._wake.triggered:
            self._wake.succeed()

    def set_state(self, state, location=''):
        """Update the visitor's current state and log the state transition."""
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
        """Walk the visitor through their mode-specific journey to the ticket scan."""
        # --- reach the festival parking area, depending on mode ---
        if self.mode != 'car':
            # Shuttle: walk to the stop, queue, and ride the bus.
            self.set_state('walking_to_bus', self.start_node_name)
            yield self.env.timeout(self.shuttlebus_walktime)
            self.set_state('waiting_bus', 'bus_stop')
            self.busqueue.put(self)   # Join the shuttle queue.
            self._log_queue('shuttle_bus_queue', 'bus_stop', len(self.busqueue.items), 'enqueue')
            yield self._wake          # Passivate until the bus reactivates us.
            # A SimPy event is one-shot: once triggered it can never fire again,
            # so create a fresh event before the visitor can passivate again.
            self._wake = self.env.event()
        else:
            # Car: join the carpool queue and wait until the car has parked.
            self.set_state('waiting_car', self.start_node_name)
            self.carqueues[self.start_node].put(self)         # Join the carpool queue.
            self._log_queue(
                f"car_queue_{self.start_node}",
                self.start_node_name,
                len(self.carqueues[self.start_node].items),
                'enqueue',
            )
            yield self._wake          # Passivate until the car reactivates us.
            # A SimPy event is one-shot: once triggered it can never fire again,
            # so create a fresh event before the visitor can passivate again.
            self._wake = self.env.event()

        # --- both modes merge here: walk to the ticket scan and get scanned ---
        self.set_state('walking_ticket', 'parking_area')
        yield self.env.timeout(self.ticket_walktime)
        self.set_state('waiting_ticket', 'ticket_scan')
        self.ticketqueue.put(self)          # Join the ticket-scan queue.
        self._log_queue('ticket_scan_queue', 'ticket_scan', len(self.ticketqueue.items), 'enqueue')
        yield self._wake                    # Passivate until a scanner reactivates us.

        # The visitor has now passed the entrance; record their arrival.
        self.arrival_time = self.env.now
        self.set_state('scanned', 'ticket_scan')
        if self.logger:
            self.logger.complete_visitor(self.visitor_id, self.arrival_time)

    def _log_queue(self, queue_name, location, length, event_type):
        """Log a queue enqueue event for this visitor, if logging is on."""
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
