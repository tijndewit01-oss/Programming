from scipy.stats import gamma

#Creating the visitor generator in a class
#Based on the number of visitors and the gamma distribution parameters in config

class TVisitorGenerator:


    def __init__(self, env, config):
        #Get the randomized inter departure times for the visitors based on the gamma distribution parameters in config
        inter_depart_params = gamma.rvs(a=config.VISITOR_GENERATOR['InterDepartDistributionParams']['kappa'],
                                        scale=config.VISITOR_GENERATOR['InterDepartDistributionParams']['theta'],
                                        loc=config.VISITOR_GENERATOR['InterDepartDistributionParams']['shift'],
                                        size=config.SIMULATION['NumberVisitors'])
        inter_depart_params.sort()  # Sort arrival times in ascending order (Returns a sorted numpy array))
        self.inter_depart_time = inter_depart_params[1:] - inter_depart_params[:-1]  # Calculate inter-departure times


        self.env = env
        self.config = config
        self.process = env.process(self.run())
    


    def run(self):
        #Activate the visitor generator process
        for wait_time in self.inter_depart_time:
            #Wait for the inter-departure time before generating the next visitor
            yield self.env.timeout(wait_time)
            #Generate a visitor
            TVisitor(self.env, self.config)
