"""TTicketScan: the final ticket-scan stage where all visitors converge."""
import config


class TTicketScan:
    """The ticket-scan stage that every visitor passes through last.

    TICKET_SCAN['NumScanLanes'] identical scanner processes share one FIFO
    queue (created in main.py). The lane count is a key experiment knob: too few
    lanes lets the queue grow without bound, too many leaves scanners idle.

    Each scanner blocks on the shared queue until a visitor is available, scans
    them for ScanTimePerTicket seconds, then reactivates the visitor so they
    leave the system.
    """

    def __init__(self, env, ticketqueue, logger=None):
        self.env = env
        self.logger = logger

        # Shared FIFO queue of visitors awaiting scanning, injected by main.py
        # so that every shared queue is created in one place.
        self.queue = ticketqueue

        self.scan_time = config.TICKET_SCAN['ScanTimePerTicket']

        # Run one scanner process per lane over the shared queue.
        num_lanes = config.TICKET_SCAN['NumScanLanes']
        self.processes = [env.process(self.run()) for _ in range(num_lanes)]

    def run(self):
        """Run one scanner lane forever: take a visitor, scan, release."""
        while True:
            # Block until a visitor is queued, then take the first in line.
            visitor = yield self.queue.get()
            visitor.set_state('scanning', 'ticket_scan')
            if self.logger:
                self.logger.log_queue(
                    sim_time=self.env.now,
                    queue_name='ticket_scan_queue',
                    location='ticket_scan',
                    length=len(self.queue.items),
                    event_type='dequeue',
                    actor_type='visitor',
                    actor_id=visitor.visitor_id,
                )
            yield self.env.timeout(self.scan_time)   # Time spent scanning this visitor.
            visitor.reactivate()                     # Visitor has now left the system.
