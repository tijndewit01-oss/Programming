# Carbon-Neutral Festivals — Transport Simulation

A discrete-event simulation (Python + [SimPy](https://simpy.readthedocs.io/)) of how
visitors travel to the **Ribs & Blues Festival** in Raalte (NL). It models the report's
"carbon-neutral" idea — a mandatory sustainability fee that funds a train discount to
nudge visitors from car to public transport — and measures the effect on modal split,
CO₂, road congestion, and queue lengths.

This repo implements the *dynamic flow* half of the model (simulating visitor journeys
on a real road network). The *decision* half — computing the modal split from price
elasticities — is **not** implemented: the split is a fixed fraction in `config.py`
(`VISITOR_GENERATOR['ModeSplit']`). See `TASKLIST` for the full status and known issues.

## Quick start

```bash
# 1. Run the simulation -> writes log files under "OUTPUT Data Files/logs/"
python3 main.py

# 2. Build the analysis dashboard (KPI charts + congestion map) from the latest run
python3 dashboard.py            # -> OUTPUT Data Files/simulation_dashboard.html
```

Open the generated `.html` file in a browser. `dashboard.py` reads the most recent
run from the log directory and also accepts `--run-id` / `--log-dir`.

**Dependencies:** `simpy`, `networkx`, `pandas`, `plotly`, `scipy`, `numpy`.
(`osmnx` is only needed by the one-time data-prep scripts, not to run the simulation.)

## How it fits together (data flow)

```
config.py  ──parameters──►  main.py  (wires the SimPy environment)
                               │
        ┌──────────────────────┼───────────────────────────┐
        ▼                      ▼                            ▼
 TVisitorGenerator       TCarGenerator                 TShuttleBus
 (spawn visitors on   (keeps a car waiting        (buses ferry public-transport
  a gamma arrival       at each entry node)         visitors station → festival)
  curve)                     │                            │
        │                    ▼                            │
   each TVisitor ──► car? ──► TCar (carpool, drive the OSM road network with
        │                     congestion + real background traffic, then park)
        │                                                  │
        └──────────── both modes converge ────────────────┘
                               ▼
                         TTicketScan  (final bottleneck; visitor exits the system)
                               │
                         SimulationLogger  ──► CSV + JSONL logs in OUTPUT Data Files/logs/
                               │
                               ▼
                          dashboard.py
        (KPI charts + static road-congestion map → one HTML file)
```

`Trafficflowmodel.py` provides the shared road state: a `TrafficDensityMap` (vehicle
occupancy per road segment), the Greenshields speed/travel-time model, congestion-aware
shortest-path routing, and the real-world background-traffic process.

## File map

| Path | Role |
|------|------|
| `config.py` | All tunable parameters (visitor count, mode split, capacities, timings, emission factors, logging intervals). Start here to change a scenario. |
| `main.py` | Initialization: builds the SimPy env, loads the road graph, creates the shared queues + parking lot, starts every component, runs the sim, prints a summary. |
| `Functions/TVisitorGenerator.py` | Spawns visitors over time using the fitted gamma arrival distribution. |
| `Functions/TVisitor.py` | One visitor: picks a mode and walks the car→park or shuttle→festival→ticket-scan path. |
| `Functions/TCarGenerator.py` | Keeps a car available at each entry node. |
| `Functions/TCar.py` | A car: carpools waiting visitors, drives the road network, queues at parking, parks. |
| `Functions/TShuttleBus.py` | The shuttle fleet: board at the station, drive to the festival, drop off, return. |
| `Functions/TTicketScan.py` | The final ticket-scan stage where all visitors converge. |
| `Functions/Trafficflowmodel.py` | Road density state, Greenshields travel-time, routing, background traffic. |
| `Functions/SimulationLogger.py` | Collects rows in memory and writes the CSV / JSONL log files. |
| `dashboard.py` | Builds the whole analysis dashboard: KPI cards, scenario comparison, queues, travel/phase times, bus use, and a static road-congestion map. |
| `INPUT_Data_Files/` | Prepared inputs + one-time prep scripts (see below). |
| `OUTPUT Data Files/` | Generated logs and HTML outputs. |
| `TASKLIST` | Development notes, fixed-bug log, and remaining work. |

## Inputs and how to regenerate them

At **run time** the simulation only needs two prepared files (already in the repo):

- `INPUT_Data_Files/network.pkl` — the OSMnx road graph (with per-edge capacity/speed).
- `INPUT_Data_Files/ROAD_DATA/flow_2_3_avg.csv` — hourly background traffic flow.

The remaining scripts in `INPUT_Data_Files/` are **one-time tools** (they require
`osmnx`) used to (re)build those inputs from raw data:

| Script | Produces |
|--------|----------|
| `RoadData_converter.py` | Converts raw `RoadData.json` into OSM XML (`network.osm`). |
| `Prepare_network.py` | Builds `network.pkl` from `network.osm` (computes `rho_max`, `u_max_ms`). |
| `roaddata_prep.py` | Extracts `flow_2_3_avg.csv` from the loop-detector Excel file. |
| `find_nodes.py` | Maps GPS coordinates (entry points, station, parking) to graph node IDs. |
| `Gamma_curve.py` | Interactive tool used to fit the visitor arrival gamma distribution. |

You do not need to run these unless you are changing the underlying road/traffic data.
