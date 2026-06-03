import simpy
#The TTicketScan class (PDL: TTicketScan)


class TTicketScan:
    """Final ticket-scan stage where all transport paths converge.

    The PDL describes a single scanner loop. Here we honour the
    TICKET_SCAN['NumScanLanes'] config by running that many identical scanner
    processes over one shared FIFO queue, since the number of scanners is a key
    experimental design parameter (too few -> the queue grows uncontrollably;
    too many -> scanners sit idle).

    The shared queue is created here and registered in
    config.TICKET_SCAN['MyQueue'] so that visitors can reach it (see TVisitor).

    SimPy translation note: the PDL `while MyQueue.Length == 0: Standby` busy
    wait is replaced by a blocking `yield self.queue.get()`, which suspends the
    scanner until a visitor is available.
    """

    def __init__(self, env, config):
        self.env = env
        self.config = config

        # Shared FIFO queue of visitors waiting to be scanned (PDL: MyQueue)
        self.queue = simpy.Store(env)
        config.TICKET_SCAN['MyQueue'] = self.queue

        self.scan_time = config.TICKET_SCAN['ScanTimePerTicket']

        # Run one scanner process per lane over the shared queue
        num_lanes = config.TICKET_SCAN['NumScanLanes']
        self.processes = [env.process(self.run()) for _ in range(num_lanes)]

    def run(self):
        while True:
            # Wait (Standby) until a visitor is queued, then take the first one
            visitor = yield self.queue.get()        # FirstOfQueue + LeaveQueue
            yield self.env.timeout(self.scan_time)   # Wait ScanTicket
            visitor.reactivate()                     # visitor leaves the system
