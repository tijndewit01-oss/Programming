from scipy.stats import gamma
import numpy as np
import config

from Functions.TVisitor import TVisitor

#Creating the visitor generator in a class
#Based on the number of visitors and the gamma distribution parameters in config

class TVisitorGenerator:


    def __init__(self, env, busqueue, carqueues, ticketqueue):
        # Get randomized absolute departure times based on the fitted gamma distribution.
        gamma_params = config.VISITOR_GENERATOR['InterDepartDistributionParams']
        departure_times = self._sample_departure_times(gamma_params)
        departure_times.sort()
        self.departure_times = departure_times


        self.env = env
        self.busqueue = busqueue
        self.carqueues = carqueues
        self.ticketqueue = ticketqueue


        self.process = env.process(self.run())

    def _sample_departure_times(self, gamma_params):
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
            valid_samples = samples[(samples >= start_time) & (samples < end_time)]
            departure_times.extend(valid_samples.tolist())

        return np.array(departure_times[:n_visitors])
    


    def run(self):
        #Activate the visitor generator process
        for departure_time in self.departure_times:
            wait_time = max(0.0, departure_time - self.env.now)
            yield self.env.timeout(wait_time)
            #Generate a visitor
            TVisitor(self.env, self.busqueue, self.carqueues, self.ticketqueue)
