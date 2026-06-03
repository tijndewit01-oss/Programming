#The TCarGenerator class



class TCarGenerator:

    def __init__(self, env, config):
        self.env = env
        self.config = config
        # Initialize any other necessary attributes here



        self.process = env.process(self.run())