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


LogDir = pathlib.Path(config.LOGGING['OutputDir'])
ScenarioDir = pathlib.Path('OUTPUT Data Files/scenarios')
ScenarioDir.mkdir(parents=True, exist_ok=True)
visitor_log = LogDir / 'visitor_log.csv'
queue_log = LogDir / 'queue_log.csv'

scenarios = list(product(TRAIN_DISCOUNTS, SHUTTLE_FREQS_PER_HOUR, PARKING_FEE_FRACTIONS_OF_TICKET))
sim_baseline = (0, 3, 0)
sim_max = (1.00, 6, 0.50)
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

n_runs = 10


def make_run_id(
        train_disc,
        shuttle_freq,
        parking_fee,
        n_rep,       
):
    return f"tr_{train_disc}sf_{shuttle_freq}pf_{parking_fee}rep_{n_rep}"


def get_run_average():
    clear_logs()
    for t, s , p in tqdm(scenarios, desc="Running scenarios", position=0):
        if (t, s, p) == sim_baseline or (t, s, p) == sim_max:
            config.LOGGING['SegmentSampleInterval'] = 300
        else: 
            config.LOGGING['SegmentSampleInterval'] = 0
        
        
        s_pt, s_car = modal_split(t, s, p)
        config.VISITOR_GENERATOR['ModeSplit'] = {'car': s_car, 'shuttle': s_pt}
        for i in tqdm(range(n_runs), desc="Reps", position=1, leave=False):
            run_id = make_run_id(t, s, p, i)
            config.LOGGING['RunId'] = run_id
            with contextlib.redirect_stdout(io.StringIO()):
                main()
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
    log_dir = pathlib.Path(config.LOGGING['OutputDir'])
    for f in log_dir.glob('*.csv'):
        f.unlink(missing_ok=True)
    for f in log_dir.glob('*.jsonl'):
        f.unlink(missing_ok=True)



def runid_type(run_id_value):
    return run_id_value.rsplit("rep_", 1)[0]

def average_visitor_log(visitor_data):
    visitor_data['run_id'] = visitor_data['run_id'].apply(runid_type)
    visitor_cols = ['total_time', 'waiting_bus_time', 'waiting_ticket_time', 'in_car_time', 'in_bus_time', 'parking_time']
    visitor_log_avg = visitor_data.groupby('run_id')[visitor_cols].mean()
    return visitor_log_avg

def average_queue_log(queue_data):
    queue_data['run_id'] = queue_data['run_id'].apply(runid_type)
    queue_log_avg = queue_data.groupby(['run_id', 'queue_name'])['length'].mean().unstack()
    return queue_log_avg

def compute_averages():
    
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

    # Group by metric
    groups = {}
    for f in heatmap_files:
        # filename: heatmap_{metric}_park{parking_fee}.png
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
            rel = f.name  # same folder as html
            html_parts.append(
                f"<div><img src='{rel}'><div class='label'>{f.stem}</div></div>"
            )
        html_parts.append("</div>")

    html_parts.append("</body></html>")

    out = ScenarioDir / 'heatmap_viewer.html'
    out.write_text('\n'.join(html_parts))
    print(f"Viewer written to {out}")


def heatmap_gen(data):
    data = data.reset_index()
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
                index='shuttle_freq',        # y axis
                columns='train_disc',        # x axis
                values=metric                # the value in each cell
            )

            fig, ax = plt.subplots(figsize=(8, 5))
            image = ax.imshow(pivot.values, aspect="auto")

            cbar = fig.colorbar(image, ax=ax)
            cbar.set_label(label)

            ax.set_xticks(np.arange(len(pivot.columns)))
            ax.set_xticklabels(pivot.columns)        # train discount values
            ax.set_yticks(np.arange(len(pivot.index)))
            ax.set_yticklabels(pivot.index)          # shuttle freq values

            ax.set_xlabel("Train Discount")
            ax.set_ylabel("Shuttle Frequency")
            ax.set_title(f"{label} | Parking Fee = €{parking_fee * BASE_FESTIVAL_TICKET_PRICE_EUR:.2f}")

            fig.savefig(ScenarioDir / f"heatmap_{metric}_park{parking_fee}.png", dpi=200)
            plt.close(fig)




if __name__ == '__main__':
    get_run_average()