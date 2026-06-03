#The TCar class
import simpy

class TCar:

    def __init__(self, env, config, G, source, density_map, parking_lot):
        self.env = env
        self.config = config
        self.G = G
        self.source = source
        self.density_map = density_map
        self.parking_lot = parking_lot

        #Initialize capacity resource
        number_of_passengers = 
        self.passenger_resource = simpy.Resource(env, np.random.randint) 