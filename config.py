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
	'NumberVisitors': 100,

	# event ending time in simulation time units (e.g., seconds)
	'EventEndingTime': 36000,

	# time unit description (for documentation only)
	'TimeUnit': 'seconds',
}


# --- ROAD_NETWORK ---
# placeholders; actual network should be loaded from files into these fields
ROAD_NETWORK: Dict[str, Any] = {
	'RoadNetwork': [],  # type: List[RoadEdge]
	'TrafficDensity': [],  # type: List[Tuple[NodeID, int]]
	'LoadFunction': None,  # Optional callable to populate the above
}


# --- TRAFFIC_MODEL ---
TRAFFIC_MODEL: Dict[str, Any] = {
	# free-flow speed (u_max) units consistent with distances/time
	'u_max': 20.0,

	# maximum density (rho_max) vehicles per unit length
	'rho_max': 200.0,

	# passenger car equivalents for buses (how many cars a bus counts as)
	'bus_equivalent': 2.5,

	# optional speed function: f(density or car_count) -> speed
	'SpeedFunction': None,
}


# --- CAR ---
CAR: Dict[str, Any] = {
	# time (seconds) per parked car to find a space
	'FindSpaceParkCar': 30,

	# parking-lot entry delay distribution placeholder; call to sample
	'ParkingLotEntryDelay': lambda: 1.0,

	# maximum wait time (seconds) a car will tolerate (e.g., at entry)
	'MaxWaitTime': 600,

	# runtime-only shared queue for cars; set in init_runtime_objects()
	'MyCarQueue': None,  # type: Queue | None
}


# --- CAR_GENERATOR ---
CAR_GENERATOR: Dict[str, Any] = {
	# parameters describing the car capacity distribution. Example format:
	# {'dist': 'poisson', 'lambda': 2} or {'dist': 'custom', 'params': {...}}
	'CarCapacityDistribution': {'dist': 'fixed', 'value': 4},
}


# --- SHUTTLE_BUS ---
SHUTTLE_BUS: Dict[str, Any] = {
	'n_buses': 3,
	'capacity': 20,
	'MaxWaitTime': 900,  # seconds
	'BoardingTimePerPassenger': 3,
	'AlightingTimePerPassenger': 2,
}


# --- TICKET_SCAN ---
TICKET_SCAN: Dict[str, Any] = {
	'ScanTimePerTicket': 2,  # seconds per ticket
	'NumScanLanes': 2,
}


# --- VISITOR ---
VISITOR: Dict[str, Any] = {
	'WalkToShuttlebus': 300,
	'WalkToTicketScan': 120,
}


# --- VISITOR_GENERATOR ---
VISITOR_GENERATOR: Dict[str, Any] = {
	# inter-departure distribution parameters (example):
	# {'dist': 'exponential', 'rate': 0.01}
	'InterDepartDistributionParams': {'dist': 'exponential', 'rate': 0.001},

	# mode split fractions: share of visitors choosing each mode (sum to 1)
	# e.g. {'car': 0.6, 'shuttle': 0.3, 'walk': 0.1}
	'ModeSplit': {'car': 0.6, 'shuttle': 0.3, 'walk': 0.1},
}


def init_runtime_objects() -> None:
	"""Create and assign runtime-only objects (queues, locks, etc.)."""
	if CAR.get('MyCarQueue') is None:
		CAR['MyCarQueue'] = Queue()


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


