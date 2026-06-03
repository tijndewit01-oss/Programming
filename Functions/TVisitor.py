import numpy as np
#Creates the TVisitor class


class TVisitor:
    
    def __init__(self, env, config):
        self.env = env
        self.config = config
        
        #Determine the mode of transport for the visitor based on the mode split in config
        mode_split = config.VISITOR_GENERATOR['ModeSplit']
        self.mode = np.random.choice(list(mode_split.keys()), p=list(mode_split.values()))

        #Determine start node if mode is car
        if self.mode == 'car':
            start_node_split = config.VISITOR_GENERATOR['CarStartNode']
            self.start_node = np.random.choice(list(start_node_split.keys()), p=list(start_node_split.values()))
        else:
            self.start_node = config.VISITOR_GENERATOR['BusStartNode'] 

        self.process = env.process(self.run())

        def run(self):
            pass