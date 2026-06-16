"""Central configuration for the festival traffic simulation.

Every tunable parameter lives here so the simulation code never hard-codes a
value. The settings are grouped into dictionaries by topic:

 - SIMULATION:        visitor count and the simulated event window.
 - LOGGING:           where logs go and how often state is sampled.
 - EMISSIONS:         CO2 factors used to turn distance into kg CO2.
 - ROAD_NETWORK:      node IDs, entry probabilities and traffic-density tuning.
 - TRAFFIC_MODEL:     parameters of the Greenshields speed/density model.
 - CAR:               parking timing, entry lanes and car occupancy.
 - SHUTTLE_BUS:       shuttle fleet size, capacity and timing.
 - TICKET_SCAN:       scan duration and number of scan lanes.
 - VISITOR:           walking speed and walking distances.
 - VISITOR_GENERATOR: arrival-time distribution and car/shuttle mode split.

To change a scenario, edit the values here rather than the simulation logic.
"""

from typing import Tuple, Dict, Any


# Type aliases used throughout the road-network code for readability.
# Defined here and imported by other modules (e.g. the network/traffic code).
NodeID = int
Distance = float
RoadEdge = Tuple[NodeID, NodeID, Distance]

SIMULATION: Dict[str, Any] = {
	# Total number of visitors generated over the event.
	'NumberVisitors': 10000,
	# Simulation clock runs in seconds since midnight; these mark the event window.
    'EventStartTime': 63000, # 17:30 expressed in seconds since midnight.
	'EventEndingTime': 86400, # 24:00 (end of Saturday) in seconds.
	# Documentation only: the unit every time value in this file uses.
	'TimeUnit': 'seconds',
}

LOGGING: Dict[str, Any] = {
    # Folder all CSV/JSONL log files are written to.
    'OutputDir': 'OUTPUT Data Files/logs',
    # Optional fixed run identifier; None lets the logger generate a timestamped one.
    'RunId': None,
    # Seconds between periodic queue-length snapshots (0 disables them).
    'QueueSampleInterval': 60,
    # Seconds between periodic road-segment density snapshots (0 disables them).
    'SegmentSampleInterval': 300,
}

EMISSIONS: Dict[str, Any] = {
    # Emission factors sourced from the CE Delft STREAM tool (see URL below).
    # https://tools.ce.nl/stream/?advanced=false&last_emission_calculation_method=1&year=4&vehicle_technology=370&distance_type=1&emission_calculation_method=1&emission=energy_consumption&emission=co2_eq&emission=nox&emission=pm2_5_combustion&emission=pm10_wear
    'CarKgCO2PerKm': 0.141742, # kg CO2 per km for an average car.
    'BusKgCO2PerKm': 0.574999, # kg CO2 per km for an OV (public transport) bus.
}

ROAD_NETWORK: Dict[str, Any] = {
    # OSM node IDs where cars enter the network (one per approach direction).
    'StartNodes':  {'Node1': 46354890, 'Node2': 46336597, 'Node3': 46527746, 'Node4': 46493064, 'Node5': 3611512307},
    # Probability that an arriving car uses each entry node (must sum to 1).
    'CarStartNodeProb': {
        'Node1': 0.4857,
        'Node2': 0.0108,
        'Node3': 0.0272,
        'Node4': 0.0539,
        'Node5': 0.4224,
    },
    # OSM node IDs of the shuttle stop and the parking lot.
    'Bus_start': 46477307,
    'Parkinglot': 46445656,
    # Width (seconds, whole minute) of the linear ramp used when background
    # traffic density steps from one hourly value to the next.
    'Interpolate': 1200,
    # Fraction of N-road flow assumed to also load the surrounding local roads.
    'N_local': 0.5,
    # Minimum segment length (m) used when computing jam density, so very short
    # edges still hold at least a sensible number of cars.
    'Min_segment_length': 150,
}

TRAFFIC_MODEL: Dict[str, Any] = {
	# Speed (kph) assumed when an OSM edge has no maxspeed tag.
	'speed_fallback': 30.0, # 30 kph corresponds to ~8.33 m/s.
	# Floor speed (m/s) so a fully jammed edge still crawls instead of stopping forever.
	'min_crawl_speed_ms': 0.1,
	# Bumper-to-bumper space (m) one car occupies, used to derive jam density.
	'Car_Spacing': 7.5,
}

CAR: Dict[str, Any] = {
	# Time (s) a car spends finding a space after being admitted to the lot.
	'FindSpaceParkCar': 60,
	# Number of parallel parking-entry lanes and the service time per car at one.
	'ParkingLotEntryLanes': 2,
	'ParkingLotEntryDelay': 7.0,
	# Maximum time (s) a car will wait for passengers before giving up.
	'MaxWaitTime': 120,
	# Car occupancy is drawn uniformly from low..high passengers inclusive.
	'CarCapacityDistribution': {'dist': 'equal', 'low': 1, 'high': 4},
}

SHUTTLE_BUS: Dict[str, Any] = {
	# Number of shuttle buses in the fleet.
	'n_buses': 4,
	# Seated capacity of one shuttle bus.
	'capacity': 40,
	# Maximum time (s) a bus waits at the stop before departing not full.
	'MaxWaitTime': 600,
	# Per-passenger boarding and alighting durations (s).
	'BoardingTimePerPassenger': 2,
	'AlightingTimePerPassenger': 2,
	# How many car-equivalents a bus adds to a road segment's density.
	'bus_equivalent': 3,
}

TICKET_SCAN: Dict[str, Any] = {
	# Time (s) to process one visitor: ticket scan plus a bag search.
	'ScanTimePerTicket': 3 + 10,
	# Number of parallel ticket-scan lanes.
	'NumScanLanes': 12,
}

VISITOR: Dict[str, Any] = {
    # Average walking speed of a visitor (m/s).
    'VisitorWalkSpeed': 1.4,
	# Walking distances (m) from the entry points to the shuttle stop and scan.
	'Dist_WalkToShuttlebus': 200,
	'Dist_WalkToTicketScan': 100,
}

VISITOR_GENERATOR: Dict[str, Any] = {
	# Distribution of absolute departure times, fitted to scanner arrival data.
	# The 'shift' is the gamma location minus the mean travel time, so departures
	# are timed to produce the observed arrivals at the festival.
	# 45*60 subtracts an assumed 45-minute travel time to back-calculate
	# departure times from the observed scanner arrival times.
	'InterDepartDistributionParams': {'dist': 'gamma', 'kappa' : 1.4593, 'theta': 4606.5, 'shift': 66271.6 - 45*60},
	# Share of visitors choosing each transport mode (must sum to 1).
	'ModeSplit': {'car': 0.73, 'shuttle': 0.27},
}
