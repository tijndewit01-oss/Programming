"""TCarGenerator: keeps one car waiting at every entry node at all times."""
import config
from Functions.TCar import TCar


class TCarGenerator:
    """Ensures a car is always ready to load at each car entry node.

    A separate process per entry node spawns a TCar, waits for it to depart,
    then immediately spawns the next one, so visitors arriving at any node
    always find a car waiting to pick them up.

    Implementation note: the car signals its departure via a SimPy event
    (TCar.departed_event); awaiting that event is how the generator knows it is
    time to create the replacement car.
    """

    def __init__(self, env, G, density_map, parking_lot, parking_entry, carqueues, logger=None):
        self.env = env
        self.G = G
        self.density_map = density_map
        self.parking_lot = parking_lot
        self.parking_entry = parking_entry
        self.carqueues = carqueues
        self.logger = logger
        self.start_nodes = config.ROAD_NETWORK['StartNodes']

        self.process = env.process(self.run())



    def run(self):
        """Start one independent car-management process per entry node."""
        # start_nodes maps name -> node_id; iterate node IDs so the source
        # matches both the carqueue keys and the road-graph nodes.
        for node in self.start_nodes.values():
            self.env.process(self.manage_node(node))
        # Yield control to the SimPy event loop for one tick so the freshly
        # spawned manage_node processes can start running before this generator
        # returns. Without it the node processes never begin.
        yield self.env.timeout(0)

    def manage_node(self, node):
        """Continuously replace the car at one node as soon as it departs."""
        while True:
            car_id = self.logger.next_id('car') if self.logger else None
            car = TCar(
                self.env,
                self.G,
                node,
                self.density_map,
                self.parking_lot,
                self.parking_entry,
                self.carqueues,
                car_id=car_id,
                logger=self.logger,
            )
            yield car.departed_event
