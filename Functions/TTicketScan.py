import config
#The TTicketScan class (PDL: TTicketScan)


class TTicketScan:
    """Final ticket-scan stage where all transport paths converge.

    The PDL describes a single scanner loop. Here we honour the
    TICKET_SCAN['NumScanLanes'] config by running that many identical scanner
    processes over one shared FIFO queue, since the number of scanners is a key
    experimental design parameter (too few -> the queue grows uncontrollably;
    too many -> scanners sit idle).

    The shared queue is created in main.py and injected into both visitors and
    ticket scanners.

    SimPy translation note: the PDL `while MyQueue.Length == 0: Standby` busy
    wait is replaced by a blocking `yield self.queue.get()`, which suspends the
    scanner until a visitor is available.
    """

    def __init__(self, env, ticketqueue, logger=None):
        self.env = env
        self.logger = logger

        # Shared FIFO queue of visitors waiting to be scanned (PDL: MyQueue).
        # Created in main.py and injected so all shared queues live in one place.
        self.queue = ticketqueue

        self.scan_time = config.TICKET_SCAN['ScanTimePerTicket']

        # Run one scanner process per lane over the shared queue
        num_lanes = config.TICKET_SCAN['NumScanLanes']
        self.processes = [env.process(self.run()) for _ in range(num_lanes)]

    def run(self):
        while True:
            # Wait (Standby) until a visitor is queued, then take the first one
            visitor = yield self.queue.get()        # FirstOfQueue + LeaveQueue
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
            yield self.env.timeout(self.scan_time)   # Wait ScanTicket
            visitor.reactivate()                     # visitor leaves the system
