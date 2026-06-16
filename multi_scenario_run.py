"""Run the full scenario sweep and aggregate the results into heatmaps.

For every (train discount, shuttle frequency, parking fee) combination this
script derives the car/shuttle mode split, runs the simulation n_runs times with
that split, and averages the per-visitor and queue metrics across the
repetitions. It writes a combined averages CSV, one heatmap PNG per metric and
parking fee, and an HTML viewer to browse them, plus a full map replay for the
baseline and maximum-intervention scenarios.

Run with:  python multi_scenario_run.py
"""

import config
from main import main
from modal_split_model_with_heatmap import modal_split, TRAIN_DISCOUNTS, SHUTTLE_FREQS_PER_HOUR, PARKING_FEE_FRACTIONS_OF_TICKET, BASE_FESTIVAL_TICKET_PRICE_EUR
import matplotlib.pyplot as plt
import visualisation
import numpy as np
import pandas as pd
import pathlib
from itertools import product
import contextlib, io
from tqdm import tqdm


# Input log files (per-run) and the output folder for aggregated scenario results.
LogDir = pathlib.Path(config.LOGGING['OutputDir'])
ScenarioDir = pathlib.Path('OUTPUT Data Files/scenarios')
ScenarioDir.mkdir(parents=True, exist_ok=True)
visitor_log = LogDir / 'visitor_log.csv'
queue_log = LogDir / 'queue_log.csv'

# Every parameter combination to simulate, plus the two scenarios worth a replay.
scenarios = list(product(TRAIN_DISCOUNTS, SHUTTLE_FREQS_PER_HOUR, PARKING_FEE_FRACTIONS_OF_TICKET))
sim_baseline = (0, 3, 0)
sim_max = (1.00, 6, 0.50)
# Metrics averaged across runs and rendered as heatmaps.
METRICS = [
    'total_time',
    'waiting_bus_time', 'waiting_ticket_time',
    'in_car_time', 'in_bus_time', 'parking_time',
    'shuttle_bus_queue', 'ticket_scan_queue', 
    'parking_entry_queue', 'parking_lot_occupancy'
]
METRIC_LABELS = {
    'total_time': 'Average Total Travel Time (s)',
    'waiting_bus_time': 'Average Bus Wait Time (s)',
    'waiting_ticket_time': 'Average Ticket Wait Time (s)',
    'in_car_time': 'Average Time in Car (s)',
    'in_bus_time': 'Average Time in Bus (s)',
    'parking_time': 'Average Parking Time (s)',
    'shuttle_bus_queue': 'Avg Shuttle Bus Queue Length (pax)',
    'ticket_scan_queue': 'Avg Ticket Scan Queue Length (pax)',
    'parking_entry_queue': 'Avg Parking Entry Queue Length (pax)',
    'parking_lot_occupancy': 'Avg Parking Lot Occupancy (cars)',
}

# Number of repetitions per scenario, averaged to smooth out randomness.
n_runs = 10


def make_run_id(
        train_disc,
        shuttle_freq,
        parking_fee,
        n_rep,
):
    """Build a run_id encoding the scenario parameters and repetition index."""
    return f"tr_{train_disc}sf_{shuttle_freq}pf_{parking_fee}rep_{n_rep}"


def get_run_average():
    """Run every scenario n_runs times, then aggregate and visualise the results."""
    clear_logs()
    for t, s , p in tqdm(scenarios, desc="Running scenarios", position=0):
        # Turn this scenario's policy levers into the mode split the sim uses.
        s_pt, s_car = modal_split(t, s, p)
        config.VISITOR_GENERATOR['ModeSplit'] = {'car': s_car, 'shuttle': s_pt}
        # Update to this scenario's bus frequency. 
        config.SHUTTLE_BUS['n_buses'] = s
        for i in tqdm(range(n_runs), desc="Reps", position=1, leave=False):
            # Only log road-segment density for the two scenarios that get a replay;
            # disabling it elsewhere keeps the sweep fast and the logs small.
            if i == 0 and ((t, s, p) == sim_baseline  or (t, s, p) == sim_max ):
                config.LOGGING['SegmentSampleInterval'] = 300
            else:
                config.LOGGING['SegmentSampleInterval'] = 0

            run_id = make_run_id(t, s, p, i)
            config.LOGGING['RunId'] = run_id
            # Silence main()'s console summary during the sweep.
            with contextlib.redirect_stdout(io.StringIO()):
                main()
            # Build a map replay from the first repetition of the two key scenarios.
            if i == 0 and (t, s, p) == sim_baseline:
                visualisation.build_simulation_replay(
                    run_id=run_id,
                    output_path=(ScenarioDir / 'simulation_baseline.html')
                )
            if i == 0 and (t, s, p) == sim_max:
                visualisation.build_simulation_replay(
                    run_id=run_id,
                    output_path=(ScenarioDir / 'simulation_max.html')
                )

    compute_averages()

def clear_logs():
    """Delete any existing per-run CSV/JSONL logs so the sweep starts clean."""
    log_dir = pathlib.Path(config.LOGGING['OutputDir'])
    for f in log_dir.glob('*.csv'):
        f.unlink(missing_ok=True)
    for f in log_dir.glob('*.jsonl'):
        f.unlink(missing_ok=True)



def runid_type(run_id_value):
    """Strip the repetition suffix so all reps of a scenario share one key."""
    return run_id_value.rsplit("rep_", 1)[0]

def average_visitor_log(visitor_data):
    """Average the per-visitor time metrics across repetitions of each scenario."""
    visitor_data['run_id'] = visitor_data['run_id'].apply(runid_type)
    visitor_cols = ['total_time', 'waiting_bus_time', 'waiting_ticket_time', 'in_car_time', 'in_bus_time', 'parking_time']
    visitor_log_avg = visitor_data.groupby('run_id')[visitor_cols].mean()
    return visitor_log_avg

def average_queue_log(queue_data):
    """Average each queue's length across repetitions, one column per queue."""
    queue_data['run_id'] = queue_data['run_id'].apply(runid_type)
    queue_log_avg = queue_data.groupby(['run_id', 'queue_name'])['length'].mean().unstack()
    return queue_log_avg

def compute_averages():
    """Combine the averaged visitor and queue metrics and produce the outputs."""
    visitor_data = pd.read_csv(visitor_log)
    queue_data = pd.read_csv(queue_log)
    visitor_log_avg = average_visitor_log(visitor_data)
    queue_log_avg = average_queue_log(queue_data)
    average_results = pd.concat([visitor_log_avg, queue_log_avg], axis=1) 
    average_results.to_csv(ScenarioDir / 'scenario_averages.csv')
    heatmap_gen(average_results)
    generate_html_viewer()

    
def generate_html_viewer():
    """Generate a simple HTML file to view all heatmaps in one place."""
    heatmap_files = sorted(ScenarioDir.glob('heatmap_*.png'))

    # Group the PNG files by the metric encoded in their filename.
    groups = {}
    for f in heatmap_files:
        # Filenames look like heatmap_{metric}_park{parking_fee}.png.
        parts = f.stem.replace('heatmap_', '').rsplit('_park', 1)
        metric = parts[0]
        groups.setdefault(metric, []).append(f)

    html_parts = ["""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Scenario Heatmaps</title>
    <style>
        body { font-family: sans-serif; background: #f4f4f4; margin: 20px; }
        h1   { color: #333; }
        h2   { color: #555; border-bottom: 2px solid #ccc; padding-bottom: 6px; margin-top: 40px; }
        .row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
        .row img { width: 380px; border: 1px solid #ccc; border-radius: 4px;
                   background: white; padding: 4px; }
        .label { font-size: 12px; color: #888; text-align: center; }
    </style>
</head>
<body>
<h1>Scenario Heatmaps — Ribs & Blues Simulation</h1>
"""]

    for metric in METRICS:
        files = groups.get(metric, [])
        if not files:
            continue
        label = metric.replace('_', ' ').title()
        html_parts.append(f"<h2>{label}</h2><div class='row'>")
        for f in sorted(files):
            rel = f.name  # The viewer sits in the same folder as the images.
            html_parts.append(
                f"<div><img src='{rel}'><div class='label'>{f.stem}</div></div>"
            )
        html_parts.append("</div>")

    html_parts.append("</body></html>")

    out = ScenarioDir / 'heatmap_viewer.html'
    out.write_text('\n'.join(html_parts))
    print(f"Viewer written to {out}")


def heatmap_gen(data):
    """Render one heatmap per metric and parking fee from the averaged results.

    The averaged rows are joined back to their scenario parameters, then for each
    parking fee a metric is pivoted over shuttle frequency (y) and train discount
    (x) and saved as a PNG.
    """
    data = data.reset_index()
    # Rebuild the scenario parameters from each run_id so they can be plotted on axes.
    scenario_df = pd.DataFrame([
    {'run_id': make_run_id(t, s, p, 0).rsplit('rep_', 1)[0], 
     'train_disc': t, 
     'shuttle_freq': s, 
     'parking_fee': p}
    for t, s, p in scenarios
    ])
    results = pd.merge(scenario_df, data, on='run_id')
    for parking_fee in PARKING_FEE_FRACTIONS_OF_TICKET:
        subset = results[results['parking_fee'] == parking_fee]

        for metric in METRICS:
            label = METRIC_LABELS[metric]
            pivot = subset.pivot(
                index='shuttle_freq',        # Rows: shuttle frequency (y axis).
                columns='train_disc',        # Columns: train discount (x axis).
                values=metric                # Cell value: the chosen metric.
            )

            fig, ax = plt.subplots(figsize=(8, 5))
            image = ax.imshow(pivot.values, aspect="auto")

            cbar = fig.colorbar(image, ax=ax)
            cbar.set_label(label)

            ax.set_xticks(np.arange(len(pivot.columns)))
            ax.set_xticklabels(pivot.columns)        # Train discount values.
            ax.set_yticks(np.arange(len(pivot.index)))
            ax.set_yticklabels(pivot.index)          # Shuttle frequency values.

            ax.set_xlabel("Train Discount")
            ax.set_ylabel("Shuttle Frequency")
            ax.set_title(f"{label} | Parking Fee = €{parking_fee * BASE_FESTIVAL_TICKET_PRICE_EUR:.2f}")

            fig.savefig(ScenarioDir / f"heatmap_{metric}_park{parking_fee}.png", dpi=200)
            plt.close(fig)




if __name__ == '__main__':
    get_run_average()