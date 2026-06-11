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

from typing import Tuple, Dict, Any


# Type aliases
NodeID = int
Distance = float
RoadEdge = Tuple[NodeID, NodeID, Distance]


# --- SIMULATION ---
SIMULATION: Dict[str, Any] = {
	# total number of visitors in the simulation
	'NumberVisitors': 5100, #PLACEHOLDER

	# event ending time in simulation time units (e.g., seconds)
    'EventStartTime': 63000, #17:30 in seconds
	'EventEndingTime': 86400, #24:00 in seconds (Saturday)

	# time unit description (for documentation only)
	'TimeUnit': 'seconds',
}


# --- LOGGING ---
LOGGING: Dict[str, Any] = {
    'OutputDir': 'OUTPUT Data Files/logs',
    'RunId': None,
    'QueueSampleInterval': 60,
    'SegmentSampleInterval': 300,
}


# --- EMISSIONS ---
EMISSIONS: Dict[str, Any] = {
    # PLACEHOLDER factors for scenario comparison; replace with cited final-report values.
    'CarKgCO2PerKm': 0.171,
    'BusKgCO2PerKm': 0.822,
}


# --- ROAD_NETWORK ---
# placeholders; actual network should be loaded from files into these fields
ROAD_NETWORK: Dict[str, Any] = {

    'StartNodes':  {'Node1': 46354890, 'Node2': 46336597, 'Node3': 3620826627, 'Node4': 46493064, 'Node5': 3611512307},
    # Node3 is intentionally excluded until BUG #8 is fixed: it has no directed path to the parking lot.
    'CarStartNodeProb': {
        'Node1': 0.6142851757100457,
        'Node2': 0.01244074154367358,
        'Node4': 0.0668925478086531,
        'Node5': 0.30638153493762754,
    },
    
    'Bus_start': 46477307,
    'Parkinglot': 46445656,

    'Interpolate': 1200, #Seconds (must be a whole minute) of interpolation time 
    					#for the traffic density update (so time before + after hour change)
    'N_local': 0.2 #Conversion of flow rate from N roads and local in percentage
}


# --- TRAFFIC_MODEL ---
TRAFFIC_MODEL: Dict[str, Any] = {
	# free-flow speed (u_max) units consistent with distances/time
	'speed_fallback': 30.0, #In case the osm had no speed limit, default to 30 kph (8.33 m/s)

	# minimum speed used when an edge is at/above jam occupancy
	'min_crawl_speed_kph': 5.0,

	# average space one car occupies on the road (bumper-to-bumper, meters)
	'Car_Spacing': 7.5,
}


# --- CAR ---
CAR: Dict[str, Any] = {
	# time (seconds) to find a parking space after passing the parking entrance
	'FindSpaceParkCar': 180,

	# number of parallel parking entrance lanes and service time per car
	'ParkingLotEntryLanes': 3,
	'ParkingLotEntryDelay': lambda: 10.0,

	# maximum wait time (seconds) a car will tolerate (e.g., at entry)
	'MaxWaitTime': 180, # s, PLACEHOLDER

	# {'dist': 'poisson', 'lambda': 2} or {'dist': 'custom', 'params': {...}}
	'CarCapacityDistribution': {'dist': 'equal', 'low': 1, 'high': 3}, #PLACEHOLDER
}


# --- CAR_GENERATOR ---
CAR_GENERATOR: Dict[str, Any] = {
	# parameters describing the car capacity distribution. Example format: PLACEHOLDER; replace with real distribution parameters or objects    
	#Car timeout time
}


# --- SHUTTLE_BUS ---
SHUTTLE_BUS: Dict[str, Any] = {
	'n_buses': 2,
	'capacity': 40, # typical full-size shuttle bus capacity
	'MaxWaitTime': 600,  # Seconds
	'BoardingTimePerPassenger': 2, # Seconds
	'AlightingTimePerPassenger': 2, # Seconds
	# passenger car equivalents for buses (how many cars a bus counts as)
	'bus_equivalent': 3, #PLACEHOLDER, Check literature
}


# --- TICKET_SCAN ---
TICKET_SCAN: Dict[str, Any] = {
	'ScanTimePerTicket': 3 + 10,  # seconds per ticket + Bag search
	'NumScanLanes': 8,
}


# --- VISITOR ---
VISITOR: Dict[str, Any] = {
    'VisitorWalkSpeed': 1.4, # m/s
	'Dist_WalkToShuttlebus': 300, # m, PLACEHOLDER, check route
	'Dist_WalkToTicketScan': 120, # m, PLACEHOLDER, check route
}


# --- VISITOR_GENERATOR ---
VISITOR_GENERATOR: Dict[str, Any] = {
	# inter-departure distribution parameters (example): PLACEHOLDER; replace with real distribution parameters or objects
	# {'dist': 'exponential', 'rate': 0.01}
	'InterDepartDistributionParams': {'dist': 'gamma', 'kappa' : 1.4593, 'theta': 4606.5, 'shift': 66271.6}, 

	# mode split fractions: share of visitors choosing each mode (sum to 1)
	# e.g. {'car': 0.6, 'shuttle': 0.3, 'walk': 0.1}
	'ModeSplit': {'car': 0.6, 'shuttle': 0.4},
    

}


# Flat registry of sections for convenience
ALL_SECTIONS: Dict[str, Dict[str, Any]] = {
	'SIMULATION': SIMULATION,
	'ROAD_NETWORK': ROAD_NETWORK,
	'TRAFFIC_MODEL': TRAFFIC_MODEL,
    'LOGGING': LOGGING,
    'EMISSIONS': EMISSIONS,
	'CAR': CAR,
	'CAR_GENERATOR': CAR_GENERATOR,
	'SHUTTLE_BUS': SHUTTLE_BUS,
	'TICKET_SCAN': TICKET_SCAN,
	'VISITOR': VISITOR,
	'VISITOR_GENERATOR': VISITOR_GENERATOR,
}
