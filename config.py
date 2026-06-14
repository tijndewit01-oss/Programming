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
"""

from typing import Tuple, Dict, Any


# Type aliases
NodeID = int
Distance = float
RoadEdge = Tuple[NodeID, NodeID, Distance]

SIMULATION: Dict[str, Any] = {
	# total number of visitors in the simulation
	'NumberVisitors': 10000, #5100,
	# event ending time in simulation time units (e.g., seconds)
    'EventStartTime': 63000, #17:30 in seconds
	'EventEndingTime': 86400, #24:00 in seconds (Saturday)
	# time unit description (for documentation only)
	'TimeUnit': 'seconds',
}

LOGGING: Dict[str, Any] = {
    'OutputDir': 'OUTPUT Data Files/logs',
    'RunId': None,
    'QueueSampleInterval': 60,
    'SegmentSampleInterval': 300,
}

EMISSIONS: Dict[str, Any] = {
    # https://tools.ce.nl/stream/?advanced=false&last_emission_calculation_method=1&year=4&vehicle_technology=370&distance_type=1&emission_calculation_method=1&emission=energy_consumption&emission=co2_eq&emission=nox&emission=pm2_5_combustion&emission=pm10_wear
    'CarKgCO2PerKm': 0.141742,#kg/km per Car
    'BusKgCO2PerKm': 0.574999,#kg/km per OV-Bus
}

ROAD_NETWORK: Dict[str, Any] = {
    'StartNodes':  {'Node1': 46354890, 'Node2': 46336597, 'Node3': 46527746, 'Node4': 46493064, 'Node5': 3611512307},
    'CarStartNodeProb': {
        'Node1': 0.4854844416,
        'Node2': 0.009832219139,
        'Node3': 0.02623787267,
        'Node4': 0.0528667995,
        'Node5': 0.4214074226,
    },
    'Bus_start': 46477307,
    'Parkinglot': 46445656,
    'Interpolate': 1200, #Seconds (must be a whole minute) of interpolation time 
    					#for the traffic density update (so time before + after hour change)
    'N_local': 0.5, #Conversion of flow rate from N roads and local in percentage
    'Min_segment_length': 150, #m
}

TRAFFIC_MODEL: Dict[str, Any] = {
	# free-flow speed (u_max) units consistent with distances/time
	'speed_fallback': 30.0, #In case the osm had no speed limit, default to 30 kph (8.33 m/s)
	# minimum speed used when an edge is at/above jam occupancy
	'min_crawl_speed_ms': 0.1,
	# average space one car occupies on the road (bumper-to-bumper, meters)
	'Car_Spacing': 7.5,
}

CAR: Dict[str, Any] = {
	# time (seconds) to find a parking space after passing the parking entrance
	'FindSpaceParkCar': 60,
	# number of parallel parking entrance lanes and service time per car
	'ParkingLotEntryLanes': 2,
	'ParkingLotEntryDelay': lambda: 7.0,
	# maximum wait time (seconds) a car will tolerate (e.g., at entry)
	'MaxWaitTime': 180, # s, PLACEHOLDER
	# Uniform distribution
	'CarCapacityDistribution': {'dist': 'equal', 'low': 1, 'high': 4}, 
}

SHUTTLE_BUS: Dict[str, Any] = {
	'n_buses': 4,
	'capacity': 40, # typical full-size shuttle bus capacity
	'MaxWaitTime': 600,  # Seconds
	'BoardingTimePerPassenger': 2, # Seconds
	'AlightingTimePerPassenger': 2, # Seconds
	# passenger car equivalents for buses (how many cars a bus counts as)
	'bus_equivalent': 3, 
}

TICKET_SCAN: Dict[str, Any] = {
	'ScanTimePerTicket': 3 + 10,  # seconds per ticket + Bag search
	'NumScanLanes': 8,
}

VISITOR: Dict[str, Any] = {
    'VisitorWalkSpeed': 1.4, # m/s
	'Dist_WalkToShuttlebus': 200, # m
	'Dist_WalkToTicketScan': 100, # m
}

VISITOR_GENERATOR: Dict[str, Any] = {
	# inter-departure distribution parameters
	# {'dist': 'exponential', 'rate': 0.01}
	'InterDepartDistributionParams': {'dist': 'gamma', 'kappa' : 1.4593, 'theta': 4606.5, 'shift': 66271.6 - 45*60}, #shifting by average travel time
	# mode split fractions: share of visitors choosing each mode (sum to 1)
	'ModeSplit': {'car': 0.73, 'shuttle': 0.27},
}
