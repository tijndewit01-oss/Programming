#The TCarGenerator class (PDL: TCarGenerator)
import config
from Functions.TCar import TCar


class TCarGenerator:
    """Keeps a car waiting at the loading bay at all times (PDL: TCarGenerator).

    As soon as a car departs, a new one is immediately generated in its place
    so there is always a car available to pick up waiting visitors (per node CHANGED).

    SimPy translation note: the PDL uses CarFree as a boolean semaphore with
    a Standby loop. Here we use a simpy.Event that the departing car triggers,
    waking the generator so it can spawn the next car.
    """

    def __init__(self, env, G, density_map, parking_lot, parking_entry, carqueues):
        self.env = env
        self.G = G
        self.density_map = density_map
        self.parking_lot = parking_lot
        self.parking_entry = parking_entry
        self.carqueues = carqueues
        self.start_nodes = config.ROAD_NETWORK['StartNodes']

        self.process = env.process(self.run())



    def run(self):
        # start_nodes is a {name: node_id} dict; iterate the node IDs so that
        # the car's source matches the carqueue keys and the road-graph nodes
        for node in self.start_nodes.values():
            self.env.process(self.manage_node(node))
        yield self.env.timeout(0)

    def manage_node(self, node):
        while True:
            car = TCar(
                self.env,
                self.G,
                node,
                self.density_map,
                self.parking_lot,
                self.parking_entry,
                self.carqueues,
            )
            yield car.departed_event
            
