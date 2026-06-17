# Carbon-Neutral Festivals — Transport Simulation

A discrete-event simulation (Python + [SimPy](https://simpy.readthedocs.io/)) of how
visitors travel to the **Ribs & Blues Festival** in Raalte (NL). It models the report's
"carbon-neutral" idea — a mandatory sustainability fee that funds a train discount to
nudge visitors from car to public transport — and measures the effect on modal split,
CO₂, road congestion, and queue lengths.

The project now has **both halves** of the model:

- **Decision half** (`modal_split_model_with_heatmap.py`): an incremental-logit modal-split
  model that turns the policy levers (train discount, shuttle frequency, parking fee) into
  car/public-transport shares, CO₂ per visitor, and the break-even sustainability fee.
- **Dynamic-flow half** (the SimPy simulation): simulates the resulting visitor journeys on
  a real road network.
- **`multi_scenario_run.py`** couples the two: for each scenario it computes the modal split,
  feeds it into the simulation, runs repetitions, and aggregates the results into heatmaps.

A single `python3 main.py` run still uses the fixed mode split in `config.py`
(`VISITOR_GENERATOR['ModeSplit']`) — that value is only a default; the scenario sweep
overwrites it per scenario. See `Project_Summary` and `Project_data_structures` for scope,
modelling assumptions, and the logging plan.

## Quick start

```bash
# 1. Run a single simulation -> writes log files under "OUTPUT Data Files/logs/"
python3 main.py

# 2. Build the analysis dashboard (static charts) from the latest run
python3 dashboard.py            # -> OUTPUT Data Files/simulation_dashboard.html

# 3. Build the animated map replay from the latest run
python3 visualisation.py        # -> OUTPUT Data Files/simulation_replay.html

# 4. (Decision model only) modal split + CO2 + break-even fee heatmaps
python3 modal_split_model_with_heatmap.py   # -> modal_split_outputs/

# 5. Full experiment: derive the split per scenario, run the sim, aggregate
python3 multi_scenario_run.py   # -> OUTPUT Data Files/scenarios/
```

Open the generated `.html` files in a browser. Both viz scripts read the most recent
run from the log directory; `dashboard.py` also accepts `--run-id`, `--log-dir`, and
`--output`.

## The experiment grid

`modal_split_model_with_heatmap.py` and `multi_scenario_run.py` sweep the same
deterministic design from the report (5 × 4 × 3 = **60 scenarios**):

- **train discount:** 0, 25, 50, 75, 100 %
- **shuttle frequency:** 3, 4, 5, 6 departures/hour
- **parking fee:** 0, 25, 50 % of the festival ticket price

`multi_scenario_run.py` runs each scenario several times and averages the per-visitor
and queue metrics, writing one heatmap per metric and parking fee plus an HTML viewer,
and a full map replay for the baseline and maximum-intervention scenarios.

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
                ┌──────────────┴───────────────┐
                ▼                               ▼
          dashboard.py                    visualisation.py
       (KPI charts → HTML)          (animated congestion map → HTML)
```

The scenario sweep wraps this loop:

```
modal_split_model_with_heatmap.modal_split(discount, freq, fee)
        │  car/PT shares per scenario
        ▼
multi_scenario_run.py  ── sets config ModeSplit + bus frequency, runs main() ×N reps ──►
        logs (run_id-tagged)  ──► averaged ──► heatmaps + viewer + baseline/max replays
                                                       (OUTPUT Data Files/scenarios/)
```

`Trafficflowmodel.py` provides the shared road state: a `TrafficDensityMap` (vehicle
occupancy per road segment), the Greenshields speed/travel-time model, congestion-aware
shortest-path routing, and the real-world background-traffic process.

## File map

| Path | Role |
|------|------|
| `config.py` | All tunable parameters (visitor count, mode split, capacities, timings, emission factors, logging intervals). Start here to change a scenario. |
| `main.py` | Initialization: builds the SimPy env, loads the road graph, creates the shared queues + parking lot, starts every component, runs the sim, prints a summary. |
| `modal_split_model_with_heatmap.py` | Standalone incremental-logit modal-split model. Computes car/PT shares, CO₂, and the break-even sustainability fee over the experiment grid; saves its own heatmaps. Also imported by `multi_scenario_run.py`. |
| `multi_scenario_run.py` | Runs the full 60-scenario sweep: derives the split per scenario, runs the simulation with repetitions, averages the metrics, and builds the aggregated heatmaps + viewer + baseline/max replays. |
| `Functions/TVisitorGenerator.py` | Spawns visitors over time using the fitted gamma arrival distribution. |
| `Functions/TVisitor.py` | One visitor: picks a mode and walks the car→park or shuttle→festival→ticket-scan path. |
| `Functions/TCarGenerator.py` | Keeps a car available at each entry node. |
| `Functions/TCar.py` | A car: carpools waiting visitors, drives the road network, queues at parking, parks. |
| `Functions/TShuttleBus.py` | The shuttle fleet: board at the station, drive to the festival, drop off, return. |
| `Functions/TTicketScan.py` | The final ticket-scan stage where all visitors converge. |
| `Functions/Trafficflowmodel.py` | Road density state, Greenshields travel-time, routing, background traffic. |
| `Functions/SimulationLogger.py` | Collects rows in memory and writes the CSV / JSONL log files. |
| `dashboard.py` | Builds the static analysis dashboard (KPIs, queues, congestion, etc.). |
| `visualisation.py` | Builds the interactive animated map replay. |
| `viz_utils.py` | Small formatting helpers shared by the two viz scripts. |
| `Project_Summary` | Festival scope, goal, core concept, and modelling assumptions (context doc). |
| `Project_data_structures` | The logging plan: which log files exist, what each row means, and the `run_id` convention. |
| `INPUT_Data_Files/` | Prepared inputs + one-time prep scripts (see below). |
| `OUTPUT Data Files/` | Generated logs (`logs/`), aggregated sweep results (`scenarios/`), and HTML outputs. |
| `modal_split_outputs/` | Heatmaps + results CSV from `modal_split_model_with_heatmap.py`. |

## Dependencies

- **Core simulation** (`main.py`): `simpy`, `networkx`, `pandas`, `numpy`, `scipy`.
- **Dashboard / map replay** (`dashboard.py`, `visualisation.py`): `plotly`, `pandas`.
- **Modal-split model + scenario sweep** (`modal_split_model_with_heatmap.py`,
  `multi_scenario_run.py`): `matplotlib`, `tqdm` (plus `numpy`, `pandas`).
- **One-time data prep only:** `osmnx`, `pyosmium` (not needed to run the simulation).

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

## Status & assumptions

- Saturday (Day 1) only; no re-entry — each ticket scan is one unique visitor. The clock
  runs in seconds since midnight from the event start to 24:00.
- Parking capacity is effectively unlimited (`main.py` uses a very large slot count) until
  a real cap is modelled.
- For a single `main.py` run the mode split is the fixed `config.VISITOR_GENERATOR['ModeSplit']`;
  the sweep computes it per scenario from the modal-split model instead.
