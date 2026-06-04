"""
Application configuration organized by functional sections.

Sections:
 - SIMULATION: global simulation parameters
 - ROAD_NETWORK: placeholders for loaded road network data
 - TRAFFIC_MODEL: fundamental traffic model parameters
 - CAR: car/parking related timing and limits
 - CAR_GENERATOR: parameters for car arrival / capacity distributions
 - SHUTTLE_BUS: shuttle fleet parameters
 - TICKET_SCAN: ticket scanning configuration
 - VISITOR: visitor walk times and counts
 - VISITOR_GENERATOR: visitor departure distribution & mode split

Update values here or replace placeholders with real distribution objects.
Call `init_runtime_objects()` at program start to create runtime-only objects.
"""

from typing import List, Tuple, Dict, Any
from queue import Queue


# Type aliases
NodeID = int
Distance = float
RoadEdge = Tuple[NodeID, NodeID, Distance]


# --- SIMULATION ---
SIMULATION: Dict[str, Any] = {
	# total number of visitors in the simulation
	'NumberVisitors': 5100, #PLACEHOLDER

	# event ending time in simulation time units (e.g., seconds)
    'EventStartTime': 64800, #18:00 in seconds
	'EventEndingTime': 86400, #24:00 in seconds (Friday)

	# time unit description (for documentation only)
	'TimeUnit': 'seconds',
}


# --- ROAD_NETWORK ---
# placeholders; actual network should be loaded from files into these fields
ROAD_NETWORK: Dict[str, Any] = {
	'RoadNetwork': [],  # type: List[RoadEdge] PLACEHOLDER FOR LOADED DATA
	'TrafficDensity': [],  # type: List[Tuple[NodeID, int]]
	'LoadFunction': None,  # Optional callable to populate the above
    


	#Starting Nodes for the cars and bus
    'CarStartNodes':  {'location1': 1, 'location2': 2, 'location3': 3, 'location4': 4, 'location5': 5, 'bus_start': 6}, #PLACEHOLDER, check route
	'ParkingLotNode': 111
}


# --- TRAFFIC_MODEL ---
TRAFFIC_MODEL: Dict[str, Any] = {
	# free-flow speed (u_max) units consistent with distances/time
	'speed_fallback': 30.0, #In case the osm had no speed limit, default to 30 kph (8.33 m/s)

	# average space one car occupies on the road (bumper-to-bumper, meters)
	'Car_Spacing': 7.5,

	# maximum density (rho_max) vehicles per unit length; computed per edge in Data.py as (length / CAR_SPACING) * lanes
	'rho_max': 200.0, #PLACEHOLDER, overridden per edge in Data.py


	# optional speed function: f(density or car_count) -> speed
	'SpeedFunction': None, #PLACEHOLDER, is based on a specific model
    
}


# --- CAR ---
CAR: Dict[str, Any] = {
	# time (seconds) per parked car to find a space
	'FindSpaceParkCar': 30, #PLACEHOLDER

	# parking-lot entry delay distribution placeholder; call to sample
	'ParkingLotEntryDelay': lambda: 1.0, #PLACEHOLDER

	# maximum wait time (seconds) a car will tolerate (e.g., at entry)
	'MaxWaitTime': 600, #PLACEHOLDER

	# runtime-only shared queue for cars; set in init_runtime_objects()
	'MyCarQueue': None,  # type: Queue | None #PLACEHOLDER, idk what to do with this yet
    
	# {'dist': 'poisson', 'lambda': 2} or {'dist': 'custom', 'params': {...}}
	'CarCapacityDistribution': {'dist': 'equal', 'low': 1, 'high': 3}, #PLACEHOLDER
}


# --- CAR_GENERATOR ---
CAR_GENERATOR: Dict[str, Any] = {
	# parameters describing the car capacity distribution. Example format: PLACEHOLDER; replace with real distribution parameters or objects    
	#Car timeout time
    'CarTimeout': 60, #seconds
}


# --- SHUTTLE_BUS ---
SHUTTLE_BUS: Dict[str, Any] = {
	'n_buses': 1,
	'capacity': 60, #PLACEHOLDER, check literature for typical shuttle bus capacities
	'MaxWaitTime': 300,  # seconds, PLACEHOLDER, check literature for typical shuttle bus wait times
	'BoardingTimePerPassenger': 3, #PLACEHOLDER, check literature for typical boarding times per passenger
	'AlightingTimePerPassenger': 2, #PLACEHOLDER, check literature for typical alighting times per passenger
	# passenger car equivalents for buses (how many cars a bus counts as)
	'bus_equivalent': 3, #PLACEHOLDER, Check literature
}


# --- TICKET_SCAN ---
TICKET_SCAN: Dict[str, Any] = {
	'ScanTimePerTicket': 2,  # seconds per ticket, PLACEHOLDER, check literature for typical ticket scanning times
	'NumScanLanes': 2, #PLACEHOLDER, check literature for typical number of scan lanes
}


# --- VISITOR ---
VISITOR: Dict[str, Any] = {
	'WalkToShuttlebus': 300, #PLACEHOLDER, check route
	'WalkToTicketScan': 120, #PLACEHOLDER, check route
}


# --- VISITOR_GENERATOR ---
VISITOR_GENERATOR: Dict[str, Any] = {
	# inter-departure distribution parameters (example): PLACEHOLDER; replace with real distribution parameters or objects
	# {'dist': 'exponential', 'rate': 0.01}
	'InterDepartDistributionParams': {'dist': 'gamma', 'kappa' : 1.4593, 'theta': 4606.5, 'shift': 66271.6}, 

	# mode split fractions: share of visitors choosing each mode (sum to 1)
	# e.g. {'car': 0.6, 'shuttle': 0.3, 'walk': 0.1}
	'ModeSplit': {'car': 0.6, 'shuttle': 0.4},
    
	#Start node for cars probability
    'CarStartNodeProb': {'node1': 0.2, 'node2': 0.2, 'node3': 0.2, 'node4': 0.2, 'node5': 0.2}, #PLACEHOLDER, check route
	'BusStartNodeProb': 'bus_start_node_id', #PLACEHOLDER, check route
}


# Flat registry of sections for convenience
ALL_SECTIONS: Dict[str, Dict[str, Any]] = {
	'SIMULATION': SIMULATION,
	'ROAD_NETWORK': ROAD_NETWORK,
	'TRAFFIC_MODEL': TRAFFIC_MODEL,
	'CAR': CAR,
	'CAR_GENERATOR': CAR_GENERATOR,
	'SHUTTLE_BUS': SHUTTLE_BUS,
	'TICKET_SCAN': TICKET_SCAN,
	'VISITOR': VISITOR,
	'VISITOR_GENERATOR': VISITOR_GENERATOR,
}


