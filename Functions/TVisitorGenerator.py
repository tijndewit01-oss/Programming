from scipy.stats import gamma
import config

from Functions.TVisitor import TVisitor

#Creating the visitor generator in a class
#Based on the number of visitors and the gamma distribution parameters in config

class TVisitorGenerator:


    def __init__(self, env, busqueue, carqueues, ticketqueue):
        #Get the randomized inter departure times for the visitors based on the gamma distribution parameters in config
        gamma_params = config.VISITOR_GENERATOR['InterDepartDistributionParams']
        inter_depart_params = gamma.rvs(a=gamma_params['kappa'],
                                        scale=gamma_params['theta'],
                                        loc=gamma_params['shift'],
                                        size=config.SIMULATION['NumberVisitors'])
        inter_depart_params.sort()  # Sort arrival times in ascending order (Returns a sorted numpy array))
        self.inter_depart_time = inter_depart_params[1:] - inter_depart_params[:-1]  # Calculate inter-departure times


        self.env = env
        self.busqueue = busqueue
        self.carqueues = carqueues
        self.ticketqueue = ticketqueue


        self.process = env.process(self.run())
    


    def run(self):
        #Activate the visitor generator process
        for wait_time in self.inter_depart_time:
            #Wait for the inter-departure time before generating the next visitor
            yield self.env.timeout(wait_time)
            #Generate a visitor
            TVisitor(self.env, self.busqueue, self.carqueues, self.ticketqueue)
