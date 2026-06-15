"""TVisitorGenerator: spawns visitors over time per the fitted arrival curve."""
from scipy.stats import gamma
import numpy as np
import config

from Functions.TVisitor import TVisitor


class TVisitorGenerator:
    """Generates all visitors at times drawn from the configured gamma curve.

    On construction it samples one absolute departure time per visitor from the
    fitted gamma distribution and sorts them. Its SimPy process then sleeps from
    one departure time to the next, creating a TVisitor at each.
    """

    def __init__(self, env, busqueue, carqueues, ticketqueue, logger=None):
        # Sample and sort every visitor's absolute departure time up front.
        gamma_params = config.VISITOR_GENERATOR['InterDepartDistributionParams']
        departure_times = self._sample_departure_times(gamma_params)
        departure_times.sort()
        self.departure_times = departure_times


        self.env = env
        self.busqueue = busqueue
        self.carqueues = carqueues
        self.ticketqueue = ticketqueue
        self.logger = logger


        self.process = env.process(self.run())

    def _sample_departure_times(self, gamma_params):
        """Draw NumberVisitors departure times from the gamma curve, within the window.

        Samples are drawn in batches and rejected if they fall outside the event
        window, repeating until enough valid times are collected.
        """
        n_visitors = config.SIMULATION['NumberVisitors']
        start_time = config.SIMULATION['EventStartTime']
        end_time = config.SIMULATION['EventEndingTime']
        departure_times = []

        while len(departure_times) < n_visitors:
            needed = n_visitors - len(departure_times)
            samples = gamma.rvs(a=gamma_params['kappa'],
                                scale=gamma_params['theta'],
                                loc=gamma_params['shift'],
                                size=needed)
            samples = np.asarray(samples)
            # Keep only samples that land inside the simulated event window.
            valid_samples = samples[(samples >= start_time) & (samples < end_time)]
            departure_times.extend(valid_samples.tolist())

        return np.array(departure_times[:n_visitors])



    def run(self):
        """Wait until each scheduled departure time and spawn a visitor there."""
        for departure_time in self.departure_times:
            wait_time = max(0.0, departure_time - self.env.now)
            yield self.env.timeout(wait_time)
            # Create the visitor due at this time.
            visitor_id = self.logger.next_id('visitor') if self.logger else None
            TVisitor(
                self.env,
                self.busqueue,
                self.carqueues,
                self.ticketqueue,
                visitor_id=visitor_id,
                logger=self.logger,
            )
