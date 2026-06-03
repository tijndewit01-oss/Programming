#The TCarGenerator class (PDL: TCarGenerator)
import random
import simpy
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

    # def __init__(self, env, config):
    #     self.env = env
    #     self.config = config

    #     # Shared queue visitors join when travelling by car (PDL: MyCarQueue)
    #     config.CAR['MyCarQueue'] = simpy.Store(env)

    #     # One-shot event signalled when a car slot becomes free
    #     self._slot_free = env.event()
    #     self._slot_free.succeed()  # first slot is free at t=0

    #     self.process = env.process(self.run())

    # def signal_slot_free(self):
    #     """Called by a departing car to wake the generator (PDL: CarFree = True)."""
    #     if not self._slot_free.triggered:
    #         self._slot_free.succeed()

    # def _sample_capacity(self):
    #     """Sample a car's passenger capacity (PDL: CarCapacity.sample)."""
    #     dist = self.config.CAR['CarCapacityDistribution']
    #     kind = dist.get('dist')
    #     if kind == 'fixed':
    #         return dist['value']
    #     if kind == 'equal':
    #         return random.randint(dist['low'], dist['high'])
    #     return dist.get('value', 4)  # fallback

    # def run(self):
    #     while True:
    #         # Wait until a loading slot is free (PDL: while not CarFree: Standby)
    #         yield self._slot_free
    #         self._slot_free = self.env.event()  # arm for the next cycle

    #         # Spawn a new car; the car will call signal_slot_free() when it departs
    #         TCar(self.env, self.config, capacity=self._sample_capacity())

    #         yield self.env.timeout(0)  # yield control so the car process can start


    def __init__(self, env, G, density_map, parking_lot):
        self.env = env
        self.G = G
        self.density_map = density_map
        self.parking_lot = parking_lot




        self.process = env.process(self.run())



    def run(self):
        for node in config.ROAD_NETWORK['CarStartNodes']:
            self.env.process(self.manage_node(node))
        yield self.env.timeout(0)

    def manage_node(self, node):
        while True:
            car = TCar(self.env, self.G, node, self.density_map, self.parking_lot)
            yield car.departed_event
            
