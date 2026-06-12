"""Build the static analysis dashboard (HTML) from the simulation log files.

Reads the latest logged run from "OUTPUT Data Files/logs/" and renders a set of
Plotly charts — scenario comparison, queue development, travel-time and journey
phase breakdowns, a road-congestion map, and headline KPI cards — into one
self-contained HTML file. Run after main.py:  python3 dashboard.py
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import pickle
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

import config


LOG_DIR = config.LOGGING['OutputDir']
NETWORK_PATH = os.path.join('INPUT_Data_Files', 'network.pkl')
DASHBOARD_OUTPUT_PATH = os.path.join('OUTPUT Data Files', 'simulation_dashboard.html')

# Congestion colour scale for the road map: (label, upper congestion-ratio bound, colour).
ROAD_BUCKETS = [
    ('Free flowing', 0.25, '#2ca25f'),
    ('Busy', 0.50, '#fdd835'),
    ('Congested', 0.75, '#fb8c00'),
    ('Very congested', math.inf, '#d73027'),
]


def safe_float(value: Any, default: float = math.nan) -> float:
    """Coerce a value to float, returning `default` for None/blank/NaN inputs."""
    try:
        output = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(output):
        return default
    return output


def seconds_to_clock(seconds: float) -> str:
    """Format a simulation time (seconds since midnight) as a 'HH:MM' clock string."""
    if not math.isfinite(float(seconds)):
        return ''
    total = int(round(float(seconds)))
    hours = (total // 3600) % 24
    minutes = (total % 3600) // 60
    return f'{hours:02d}:{minutes:02d}'

QUEUE_LABELS = {
    'shuttle_bus_queue': 'Shuttle queue',
    'ticket_scan_queue': 'Ticket scan',
    'parking_entry_queue': 'Parking entry',
    'car_queues_total': 'Car pickup queues',
    'parking_lot_occupancy': 'Parked cars',
}

PHASE_LABELS = {
    'walking_time': 'Walking',
    'waiting_car_time': 'Waiting car',
    'waiting_bus_time': 'Waiting bus',
    'waiting_ticket_time': 'Waiting ticket',
    'in_car_time': 'In car',
    'in_bus_time': 'In bus',
    'parking_time': 'Parking',
    'scanning_time': 'Scanning',
}

PLOT_CONFIG = {
    'displaylogo': False,
    'responsive': True,
}


def load_all_summaries(log_dir: str = LOG_DIR) -> list[dict[str, Any]]:
    path = os.path.join(log_dir, 'scenario_summary.jsonl')
    if not os.path.exists(path):
        raise FileNotFoundError(f'Missing scenario summary log: {path}')

    summaries = []
    with open(path) as f:
        for line in f:
            if line.strip():
                summaries.append(json.loads(line))

    if not summaries:
        raise ValueError(f'No scenario summaries found in {path}')
    return summaries


def latest_run_id(summaries: list[dict[str, Any]]) -> str:
    return str(summaries[-1]['run_id'])


def load_run_logs(log_dir: str, run_id: str) -> dict[str, pd.DataFrame]:
    return {
        'visitors': read_run_csv(
            log_dir,
            'visitor_log.csv',
            run_id,
            [
                'run_id', 'visitor_id', 'mode', 'depart_time', 'arrival_time',
                'completed', 'final_state', 'total_time', *PHASE_LABELS.keys(),
            ],
        ),
        'queues': read_run_csv(
            log_dir,
            'queue_log.csv',
            run_id,
            ['run_id', 'sim_time', 'queue_name', 'length', 'event_type'],
        ),
        'buses': read_run_csv(
            log_dir,
            'bus_log.csv',
            run_id,
            [
                'run_id', 'bus_id', 'trip_id', 'depart_time', 'arrival_time',
                'return_arrival_time', 'passenger_count', 'capacity',
                'load_factor', 'station_queue_left', 'outbound_drive_time',
                'return_drive_time', 'outbound_distance_m', 'return_distance_m',
            ],
        ),
        'segments': read_run_csv(
            log_dir,
            'segment_density_log.csv',
            run_id,
            [
                'run_id', 'sim_time', 'event_type', 'actor_type', 'segment_id',
                'occupancy', 'background_occupancy', 'rho_max',
                'congestion_ratio', 'speed_ms', 'max_speed_ms', 'length_m',
            ],
        ),
    }


def read_run_csv(log_dir: str, filename: str, run_id: str, requested_columns: list[str]) -> pd.DataFrame:
    path = os.path.join(log_dir, filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=requested_columns)

    header = pd.read_csv(path, nrows=0).columns.tolist()
    usecols = [column for column in requested_columns if column in header]
    df = pd.read_csv(path, usecols=usecols)
    if 'run_id' in df.columns:
        df = df[df['run_id'].astype(str) == str(run_id)].copy()

    numeric_columns = [
        'visitor_id', 'depart_time', 'arrival_time', 'total_time',
        'sim_time', 'length', 'bus_id', 'trip_id', 'passenger_count',
        'capacity', 'load_factor', 'station_queue_left',
        'outbound_drive_time', 'return_drive_time', 'outbound_distance_m',
        'return_distance_m', 'occupancy', 'background_occupancy',
        'rho_max', 'congestion_ratio', 'speed_ms', 'length_m',
        *PHASE_LABELS.keys(),
    ]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors='coerce')
    return df


def scenario_dataframe(summaries: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for index, summary in enumerate(summaries, start=1):
        peak_queues = summary.get('peak_queues') or {}
        mode_counts = summary.get('mode_counts') or {}
        visitors_generated = safe_float(summary.get('visitors_generated') or summary.get('number_visitors_config'), 0)
        visitors_completed = safe_float(summary.get('visitors_completed'), 0)
        run_id = str(summary.get('run_id', f'run_{index}'))

        rows.append({
            'scenario': f'Run {index}',
            'run_id': run_id,
            'run_label': run_id[-8:],
            'visitors_generated': visitors_generated,
            'visitors_completed': visitors_completed,
            'completion_rate': visitors_completed / visitors_generated if visitors_generated else math.nan,
            'avg_travel_min': seconds_to_minutes(summary.get('avg_travel_time')),
            'median_travel_min': seconds_to_minutes(summary.get('median_travel_time')),
            'p95_travel_min': seconds_to_minutes(summary.get('p95_travel_time')),
            'car_co2_kg': safe_float(summary.get('car_co2_kg'), 0),
            'bus_co2_kg': safe_float(summary.get('bus_co2_kg'), 0),
            'total_co2_kg': safe_float(summary.get('total_co2_kg'), math.nan),
            'car_km': safe_float(summary.get('car_km'), math.nan),
            'bus_km': safe_float(summary.get('bus_km'), math.nan),
            'car_visitors': safe_float(mode_counts.get('car'), math.nan),
            'shuttle_visitors': safe_float(mode_counts.get('shuttle'), math.nan),
            'n_buses': safe_float(summary.get('n_buses'), math.nan),
            'ticket_scan_lanes': safe_float(summary.get('ticket_scan_lanes'), math.nan),
            'parking_entry_lanes': safe_float(summary.get('parking_entry_lanes'), math.nan),
            'peak_shuttle_queue': safe_float(peak_queues.get('shuttle_bus_queue'), 0),
            'peak_ticket_queue': safe_float(peak_queues.get('ticket_scan_queue'), 0),
            'peak_parking_entry_queue': safe_float(peak_queues.get('parking_entry_queue'), 0),
            'peak_parking_lot_occupancy': safe_float(peak_queues.get('parking_lot_occupancy'), 0),
            'max_congestion_ratio': safe_float(summary.get('max_congestion_ratio'), math.nan),
        })
    return pd.DataFrame(rows)


def create_dashboard(
    log_dir: str = LOG_DIR,
    output_path: str = DASHBOARD_OUTPUT_PATH,
    run_id: str | None = None,
) -> str:
    summaries = load_all_summaries(log_dir)
    selected_run_id = run_id or latest_run_id(summaries)
    selected_summary = select_summary(summaries, selected_run_id)
    logs = load_run_logs(log_dir, selected_run_id)
    scenario_df = scenario_dataframe(summaries)

    figures = [
        ('Scenario Comparison', figure_scenario_comparison(scenario_df)),
        ('Scenario Summary Table', figure_scenario_table(scenario_df)),
        ('Travel Time Distribution', figure_travel_time_distribution(logs['visitors'])),
        ('Queue Development', figure_queue_timeseries(logs['queues'])),
        ('Journey Phase Times', figure_phase_times(logs['visitors'], selected_summary)),
        ('Bus Utilisation', figure_bus_utilisation(logs['buses'])),
        ('Road Congestion Map', figure_congestion_map(logs['segments'])),
        ('Visitor Generation Distribution', figure_visitor_generation(logs['visitors'])),
    ]

    html_output = render_html(
        selected_run_id=selected_run_id,
        selected_summary=selected_summary,
        scenario_df=scenario_df,
        figures=figures,
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    return output_path


def select_summary(summaries: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    for summary in reversed(summaries):
        if str(summary.get('run_id')) == str(run_id):
            return summary
    return summaries[-1]


def figure_scenario_comparison(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            'Completion Rate',
            'Travel Time',
            'CO2 by Mode',
            'Peak Queues',
        ),
        vertical_spacing=0.16,
        horizontal_spacing=0.12,
    )
    x = df['scenario'] + '<br>' + df['run_label']

    fig.add_trace(
        go.Bar(
            x=x,
            y=df['completion_rate'] * 100,
            marker_color='#2563eb',
            text=[format_percent(value) for value in df['completion_rate']],
            textposition='outside',
            hovertemplate='%{x}<br>%{y:.1f}% completed<extra></extra>',
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    for column, label, color in [
        ('avg_travel_min', 'Average', '#0f766e'),
        ('median_travel_min', 'Median', '#7c3aed'),
        ('p95_travel_min', 'P95', '#dc2626'),
    ]:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df[column],
                mode='lines+markers',
                name=label,
                line={'color': color, 'width': 2.5},
                hovertemplate=f'{label}: %{{y:.1f}} min<extra></extra>',
            ),
            row=1,
            col=2,
        )

    fig.add_trace(
        go.Bar(x=x, y=df['car_co2_kg'], name='Car CO2', marker_color='#64748b'),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(x=x, y=df['bus_co2_kg'], name='Bus CO2', marker_color='#10b981'),
        row=2,
        col=1,
    )

    for column, label, color in [
        ('peak_shuttle_queue', 'Shuttle', '#2563eb'),
        ('peak_ticket_queue', 'Ticket', '#dc2626'),
        ('peak_parking_entry_queue', 'Parking entry', '#f59e0b'),
    ]:
        fig.add_trace(
            go.Bar(x=x, y=df[column], name=label, marker_color=color),
            row=2,
            col=2,
        )

    fig.update_layout(
        template='plotly_white',
        height=760,
        barmode='group',
        legend={'orientation': 'h', 'y': -0.10},
        margin={'l': 55, 'r': 25, 't': 75, 'b': 95},
    )
    fig.update_yaxes(title_text='%', rangemode='tozero', row=1, col=1)
    fig.update_yaxes(title_text='Minutes', rangemode='tozero', row=1, col=2)
    fig.update_yaxes(title_text='kg CO2', rangemode='tozero', row=2, col=1)
    fig.update_yaxes(title_text='Visitors / cars', rangemode='tozero', row=2, col=2)
    return fig


def figure_scenario_table(df: pd.DataFrame) -> go.Figure:
    table = df.copy()
    table['completion_rate'] = table['completion_rate'].map(format_percent)
    for column in ['avg_travel_min', 'median_travel_min', 'p95_travel_min']:
        table[column] = table[column].map(lambda value: format_number(value, 1))
    for column in ['total_co2_kg', 'peak_shuttle_queue', 'peak_ticket_queue', 'max_congestion_ratio']:
        table[column] = table[column].map(lambda value: format_number(value, 1))

    columns = [
        ('scenario', 'Run'),
        ('run_label', 'Run ID'),
        ('visitors_generated', 'Generated'),
        ('visitors_completed', 'Completed'),
        ('completion_rate', 'Completion'),
        ('avg_travel_min', 'Avg min'),
        ('p95_travel_min', 'P95 min'),
        ('total_co2_kg', 'CO2 kg'),
        ('peak_shuttle_queue', 'Peak shuttle'),
        ('peak_ticket_queue', 'Peak ticket'),
        ('max_congestion_ratio', 'Max congestion'),
    ]

    fig = go.Figure(
        go.Table(
            header={
                'values': [label for _, label in columns],
                'fill_color': '#111827',
                'font': {'color': 'white', 'size': 12},
                'align': 'left',
            },
            cells={
                'values': [table[column] for column, _ in columns],
                'fill_color': '#f8fafc',
                'align': 'left',
                'height': 28,
            },
        )
    )
    fig.update_layout(template='plotly_white', height=255, margin={'l': 0, 'r': 0, 't': 10, 'b': 0})
    return fig


def figure_travel_time_distribution(visitors: pd.DataFrame) -> go.Figure:
    travel_minutes = completed_travel_minutes(visitors)
    if travel_minutes.empty:
        return blank_figure('Travel Time Distribution', 'No completed visitor travel times available.')

    sorted_minutes = travel_minutes.sort_values()
    cdf = pd.Series(range(1, len(sorted_minutes) + 1), index=sorted_minutes.index) / len(sorted_minutes) * 100

    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(
        go.Histogram(
            x=travel_minutes,
            nbinsx=45,
            name='Visitors',
            marker_color='#2563eb',
            opacity=0.78,
            hovertemplate='%{x:.1f} min<br>%{y} visitors<extra></extra>',
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=sorted_minutes,
            y=cdf,
            mode='lines',
            name='CDF',
            line={'color': '#dc2626', 'width': 3},
            hovertemplate='%{x:.1f} min<br>%{y:.1f}% complete<extra></extra>',
        ),
        secondary_y=True,
    )

    mean_value = travel_minutes.mean()
    median_value = travel_minutes.median()
    fig.add_vline(x=mean_value, line_color='#0f766e', line_dash='dash')
    fig.add_vline(x=median_value, line_color='#7c3aed', line_dash='dot')
    fig.add_annotation(
        x=mean_value,
        y=0.96,
        yref='paper',
        text=f'Mean {mean_value:.1f} min',
        showarrow=False,
        font={'color': '#0f766e'},
    )
    fig.add_annotation(
        x=median_value,
        y=0.88,
        yref='paper',
        text=f'Median {median_value:.1f} min',
        showarrow=False,
        font={'color': '#7c3aed'},
    )
    fig.update_layout(
        template='plotly_white',
        height=460,
        bargap=0.05,
        margin={'l': 55, 'r': 55, 't': 45, 'b': 55},
        legend={'orientation': 'h', 'y': 1.10},
    )
    fig.update_xaxes(title_text='Total travel time (minutes)')
    fig.update_yaxes(title_text='Visitors', secondary_y=False)
    fig.update_yaxes(title_text='Cumulative %', range=[0, 100], secondary_y=True)
    return fig


def figure_queue_timeseries(queues: pd.DataFrame) -> go.Figure:
    queue_series = queue_snapshot_pivot(queues)
    if queue_series.empty:
        return blank_figure('Queue Development', 'No queue snapshots available.')

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.62, 0.38],
        vertical_spacing=0.08,
        subplot_titles=('Queue lengths', 'Parking lot occupancy'),
    )
    x = queue_series.index
    colors = {
        'shuttle_bus_queue': '#2563eb',
        'ticket_scan_queue': '#dc2626',
        'parking_entry_queue': '#f59e0b',
        'car_queues_total': '#7c3aed',
        'parking_lot_occupancy': '#0f766e',
    }

    for queue_name in ['shuttle_bus_queue', 'ticket_scan_queue', 'parking_entry_queue', 'car_queues_total']:
        if queue_name in queue_series:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=queue_series[queue_name],
                    mode='lines',
                    name=QUEUE_LABELS[queue_name],
                    line={'color': colors[queue_name], 'width': 2.5},
                    hovertemplate='%{y:.0f}<extra></extra>',
                ),
                row=1,
                col=1,
            )

    if 'parking_lot_occupancy' in queue_series:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=queue_series['parking_lot_occupancy'],
                mode='lines',
                name=QUEUE_LABELS['parking_lot_occupancy'],
                fill='tozeroy',
                line={'color': colors['parking_lot_occupancy'], 'width': 2},
                hovertemplate='%{y:.0f} parked cars<extra></extra>',
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        template='plotly_white',
        height=560,
        margin={'l': 55, 'r': 25, 't': 70, 'b': 65},
        legend={'orientation': 'h', 'y': -0.12},
    )
    configure_time_axis(fig, x, row=2, col=1)
    fig.update_yaxes(title_text='Visitors / vehicles', rangemode='tozero', row=1, col=1)
    fig.update_yaxes(title_text='Cars', rangemode='tozero', row=2, col=1)
    return fig


def figure_phase_times(visitors: pd.DataFrame, summary: dict[str, Any]) -> go.Figure:
    values = average_phase_minutes(visitors, summary)
    if not values:
        return blank_figure('Journey Phase Times', 'No phase-duration fields available.')

    labels = [PHASE_LABELS[column] for column in values]
    minutes = [values[column] for column in values]

    fig = go.Figure(
        go.Bar(
            x=minutes,
            y=labels,
            orientation='h',
            marker_color=['#38bdf8', '#c084fc', '#2563eb', '#dc2626', '#7c3aed', '#1d4ed8', '#10b981', '#991b1b'][:len(labels)],
            text=[format_number(value, 1) for value in minutes],
            textposition='outside',
            hovertemplate='%{y}: %{x:.1f} min<extra></extra>',
        )
    )
    fig.update_layout(
        template='plotly_white',
        height=430,
        margin={'l': 120, 'r': 45, 't': 35, 'b': 45},
    )
    fig.update_xaxes(title_text='Average minutes per generated visitor', rangemode='tozero')
    fig.update_yaxes(autorange='reversed')
    return fig


def figure_bus_utilisation(buses: pd.DataFrame) -> go.Figure:
    if buses.empty or 'load_factor' not in buses:
        return blank_figure('Bus Utilisation', 'No bus trip log available.')

    pivot = buses.pivot_table(index='bus_id', columns='trip_id', values='load_factor', aggfunc='mean')
    if pivot.empty:
        return blank_figure('Bus Utilisation', 'No bus load factors available.')

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values * 100,
            x=[int(column) for column in pivot.columns],
            y=[f'Bus {int(index)}' for index in pivot.index],
            colorscale=[
                [0, '#eff6ff'],
                [0.4, '#60a5fa'],
                [0.75, '#2563eb'],
                [1, '#111827'],
            ],
            colorbar={'title': 'Load %'},
            hovertemplate='Trip %{x}<br>%{y}<br>%{z:.0f}% full<extra></extra>',
        )
    )
    fig.update_layout(
        template='plotly_white',
        height=360,
        margin={'l': 70, 'r': 30, 't': 35, 'b': 55},
    )
    fig.update_xaxes(title_text='Trip number')
    return fig


def load_network_geometry(network_path: str = NETWORK_PATH):
    """Load road geometry from network.pkl for the congestion map.

    Returns (edge_coords, node_lookup):
      edge_coords: {segment_id 'u->v' -> [(lon, lat), ...]}
      node_lookup: {node_id -> (lon, lat)}
    """
    with open(network_path, 'rb') as f:
        graph = pickle.load(f)
    node_lookup = {
        int(node): (float(data['x']), float(data['y']))
        for node, data in graph.nodes(data=True)
        if 'x' in data and 'y' in data
    }
    edge_coords: dict[str, list[tuple[float, float]]] = {}
    for u, v, data in graph.edges(data=True):
        geometry = data.get('geometry')
        if geometry is not None and hasattr(geometry, 'coords'):
            coords = [(float(x), float(y)) for x, y in geometry.coords]
        elif int(u) in node_lookup and int(v) in node_lookup:
            coords = [node_lookup[int(u)], node_lookup[int(v)]]
        else:
            continue
        edge_coords[f'{int(u)}->{int(v)}'] = coords
    return edge_coords, node_lookup


def road_bucket_index(congestion_ratio: float) -> int:
    """Map a congestion ratio to its colour-bucket index in ROAD_BUCKETS."""
    for index, (_, upper_bound, _) in enumerate(ROAD_BUCKETS):
        if congestion_ratio <= upper_bound:
            return index
    return len(ROAD_BUCKETS) - 1


def figure_congestion_map(segments: pd.DataFrame) -> go.Figure:
    """Static map of Raalte's roads, each segment coloured by its peak congestion.

    Replaces the old animated replay with one polyline trace per congestion bucket,
    plus markers for the car entry nodes, the station/shuttle stop, and the parking
    lot. Peak congestion is taken over the periodic segment snapshots.
    """
    try:
        edge_coords, node_lookup = load_network_geometry()
    except (FileNotFoundError, OSError):
        return blank_figure('Road Congestion Map', 'Road network file not found.')

    if segments.empty or 'congestion_ratio' not in segments:
        return blank_figure('Road Congestion Map', 'No segment density log available.')

    source = segments[segments['event_type'] == 'snapshot']
    if source.empty:
        source = segments
    peak = (
        source.dropna(subset=['segment_id', 'congestion_ratio'])
        .groupby('segment_id')['congestion_ratio']
        .max()
    )
    if peak.empty:
        return blank_figure('Road Congestion Map', 'No congestion ratios available.')

    # One polyline trace per congestion bucket; None entries break the line between segments.
    bucket_x: list[list] = [[] for _ in ROAD_BUCKETS]
    bucket_y: list[list] = [[] for _ in ROAD_BUCKETS]
    bucket_text: list[list] = [[] for _ in ROAD_BUCKETS]
    for segment_id, ratio in peak.items():
        coords = edge_coords.get(str(segment_id))
        if not coords:
            continue
        index = road_bucket_index(safe_float(ratio, 0.0))
        label = f'{segment_id}<br>peak congestion {ratio:.2f}'
        for lon, lat in coords:
            bucket_x[index].append(lon)
            bucket_y[index].append(lat)
            bucket_text[index].append(label)
        bucket_x[index].append(None)
        bucket_y[index].append(None)
        bucket_text[index].append(None)

    fig = go.Figure()
    for index, (name, _, color) in enumerate(ROAD_BUCKETS):
        fig.add_trace(go.Scatter(
            x=bucket_x[index] or [None],
            y=bucket_y[index] or [None],
            mode='lines',
            line={'color': color, 'width': 3},
            name=name,
            hoverinfo='text',
            text=bucket_text[index] or [None],
            connectgaps=False,
        ))

    # Markers for the key locations.
    markers = [(f'Car entry {name}', node_id, '#8b5cf6', 'circle')
               for name, node_id in config.ROAD_NETWORK['StartNodes'].items()]
    markers.append(('Train station / shuttle stop', config.ROAD_NETWORK['Bus_start'], '#0ea5e9', 'diamond'))
    markers.append(('Car parking / festival', config.ROAD_NETWORK['Parkinglot'], '#dc2626', 'star'))
    for label, node_id, color, symbol in markers:
        point = node_lookup.get(int(node_id))
        if not point:
            continue
        fig.add_trace(go.Scatter(
            x=[point[0]], y=[point[1]], mode='markers',
            marker={'color': color, 'size': 12, 'symbol': symbol, 'line': {'color': 'white', 'width': 1}},
            name=label, hoverinfo='text', text=[label],
        ))

    fig.update_layout(
        template='plotly_white',
        height=620,
        margin={'l': 30, 'r': 30, 't': 35, 'b': 30},
        legend={'orientation': 'h', 'yanchor': 'bottom', 'y': 1.01},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def figure_visitor_generation(visitors):
    visitor_in_system = visitors['depart_time']
    if visitor_in_system.empty:
        return blank_figure('Visitor Start Time Distribution', 'No completed visitor start times available.')

    sorted_visitors = visitor_in_system.sort_values()
    cdf = pd.Series(range(1, len(sorted_visitors) + 1), index=sorted_visitors.index) / len(sorted_visitors) * 100


    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(
        go.Histogram(
            x=sorted_visitors,
            nbinsx=45,
            name='Visitors Generated',
            marker_color='#2563eb',
            opacity=0.78,
            hovertemplate='%{x:.1f} min<br>%{y} visitors<extra></extra>',
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=sorted_visitors,
            y=cdf,
            mode='lines',
            name='CDF',
            line={'color': '#dc2626', 'width': 3},
            hovertemplate='%{x:.1f} min<br>%{y:.1f}% complete<extra></extra>',
        ),
        secondary_y=True,
    )

    mean_value = visitor_in_system.mean()
    median_value = visitor_in_system.median()
    fig.add_vline(x=mean_value, line_color='#0f766e', line_dash='dash')
    fig.add_vline(x=median_value, line_color='#7c3aed', line_dash='dot')
    fig.add_annotation(
        x=mean_value,
        y=0.96,
        yref='paper',
        text=f'Mean {seconds_to_clock(mean_value)}',
        showarrow=False,
        font={'color': '#0f766e'},
    )
    fig.add_annotation(
        x=median_value,
        y=0.88,
        yref='paper',
        text=f'Median {seconds_to_clock(median_value)}',
        showarrow=False,
        font={'color': '#7c3aed'},
    )
    fig.update_layout(
        template='plotly_white',
        height=460,
        bargap=0.05,
        margin={'l': 55, 'r': 55, 't': 45, 'b': 55},
        legend={'orientation': 'h', 'y': 1.10},
    )
    configure_time_axis(fig, sorted_visitors)
    fig.update_yaxes(title_text='Visitors', secondary_y=False)
    fig.update_yaxes(title_text='Cumulative %', range=[0, 100], secondary_y=True)
    return fig

def completed_travel_minutes(visitors: pd.DataFrame) -> pd.Series:
    if visitors.empty:
        return pd.Series(dtype=float)

    completed = visitors.get('completed', pd.Series(False, index=visitors.index)).astype(str).str.lower().isin(['true', '1', 'yes'])
    total_time = visitors.get('total_time', pd.Series(math.nan, index=visitors.index)).copy()
    computed_total = visitors.get('arrival_time', pd.Series(math.nan, index=visitors.index)) - visitors.get('depart_time', pd.Series(math.nan, index=visitors.index))
    total_time = total_time.fillna(computed_total)
    travel_minutes = total_time[completed].dropna() / 60
    return travel_minutes[travel_minutes >= 0]


def queue_snapshot_pivot(queues: pd.DataFrame) -> pd.DataFrame:
    if queues.empty:
        return pd.DataFrame()

    snapshots = queues[queues['event_type'] == 'snapshot'].copy()
    if snapshots.empty:
        snapshots = queues.copy()
    snapshots = snapshots.dropna(subset=['sim_time', 'queue_name'])
    if snapshots.empty:
        return pd.DataFrame()

    pivot = snapshots.pivot_table(index='sim_time', columns='queue_name', values='length', aggfunc='last').sort_index().ffill().fillna(0)
    car_columns = [column for column in pivot.columns if str(column).startswith('car_queue_')]
    if car_columns:
        pivot['car_queues_total'] = pivot[car_columns].sum(axis=1)

    selected = [name for name in QUEUE_LABELS if name in pivot.columns]
    return pivot[selected]


def average_phase_minutes(visitors: pd.DataFrame, summary: dict[str, Any]) -> dict[str, float]:
    summary_phases = summary.get('avg_phase_times') or {}
    values: dict[str, float] = {}
    for column in PHASE_LABELS:
        if column in summary_phases:
            value = seconds_to_minutes(summary_phases[column])
        elif column in visitors and not visitors[column].dropna().empty:
            value = visitors[column].fillna(0).mean() / 60
        else:
            value = math.nan
        if math.isfinite(value):
            values[column] = value
    return values


def render_html(
    selected_run_id: str,
    selected_summary: dict[str, Any],
    scenario_df: pd.DataFrame,
    figures: list[tuple[str, go.Figure]],
) -> str:
    sections = []
    include_plotlyjs: bool | str = True
    for title, figure in figures:
        sections.append(
            f"""
            <section class="panel">
                <h2>{html.escape(title)}</h2>
                {pio.to_html(figure, full_html=False, include_plotlyjs=include_plotlyjs, config=PLOT_CONFIG)}
            </section>
            """
        )
        include_plotlyjs = False

    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Simulation Dashboard</title>
    <style>
        :root {{
            color-scheme: light;
            --page: #f3f4f6;
            --panel: #ffffff;
            --ink: #111827;
            --muted: #64748b;
            --line: #d8dee8;
            --blue: #2563eb;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background: var(--page);
            color: var(--ink);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        header {{
            padding: 24px 32px 18px;
            background: #ffffff;
            border-bottom: 1px solid var(--line);
        }}
        h1 {{
            margin: 0 0 8px;
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 0;
        }}
        h2 {{
            margin: 0 0 12px;
            font-size: 17px;
            font-weight: 650;
            letter-spacing: 0;
        }}
        .meta {{
            color: var(--muted);
            font-size: 14px;
        }}
        main {{
            width: min(1500px, calc(100vw - 32px));
            margin: 18px auto 40px;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }}
        .card {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 13px 14px;
        }}
        .label {{
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 6px;
        }}
        .value {{
            font-size: 23px;
            line-height: 1.1;
            font-weight: 720;
        }}
        .sub {{
            color: var(--muted);
            font-size: 12px;
            margin-top: 6px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }}
        .panel {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px;
            min-width: 0;
        }}
        .panel:first-child,
        .panel:nth-child(2),
        .panel:nth-child(5),
        .panel:nth-child(8) {{
            grid-column: 1 / -1;
        }}
        @media (max-width: 980px) {{
            header {{ padding: 20px; }}
            main {{ width: calc(100vw - 20px); }}
            .grid {{ grid-template-columns: 1fr; }}
            .panel {{ grid-column: 1 / -1; }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>Simulation Dashboard</h1>
        <div class="meta">Latest selected run: {html.escape(selected_run_id)} | Logged runs: {len(scenario_df)}</div>
    </header>
    <main>
        {kpi_cards(selected_summary)}
        <div class="grid">
            {''.join(sections)}
        </div>
    </main>
</body>
</html>
"""


def kpi_cards(summary: dict[str, Any]) -> str:
    generated = safe_float(summary.get('visitors_generated') or summary.get('number_visitors_config'), 0)
    completed = safe_float(summary.get('visitors_completed'), 0)
    completion = completed / generated if generated else math.nan
    peak_queues = summary.get('peak_queues') or {}

    cards = [
        ('Generated', format_number(generated, 0), 'visitors'),
        ('Completed', format_number(completed, 0), format_percent(completion)),
        ('Average Travel', format_duration(summary.get('avg_travel_time')), 'completed visitors'),
        ('P95 Travel', format_duration(summary.get('p95_travel_time')), 'slowest 5% threshold'),
        ('Total CO2', format_number(summary.get('total_co2_kg'), 1), 'kg'),
        ('Peak Shuttle Queue', format_number(peak_queues.get('shuttle_bus_queue'), 0), 'visitors'),
        ('Peak Ticket Queue', format_number(peak_queues.get('ticket_scan_queue'), 0), 'visitors'),
        ('Max Congestion', format_number(summary.get('max_congestion_ratio'), 2), 'ratio'),
    ]

    return '<div class="cards">' + ''.join(
        f"""
        <div class="card">
            <div class="label">{html.escape(label)}</div>
            <div class="value">{html.escape(value)}</div>
            <div class="sub">{html.escape(sub)}</div>
        </div>
        """
        for label, value, sub in cards
    ) + '</div>'


def blank_figure(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False)
    fig.update_layout(template='plotly_white', height=330, title=title)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def configure_time_axis(fig: go.Figure, values: pd.Index | pd.Series | list[float], row: int | None = None, col: int | None = None) -> None:
    numeric_values = [float(value) for value in values if pd.notna(value)]
    if not numeric_values:
        return

    start = min(numeric_values)
    end = max(numeric_values)
    step = 1800 if end - start <= 8 * 3600 else 3600
    ticks = list(range(int(math.floor(start / step) * step), int(math.ceil(end / step) * step) + 1, step))
    axis_args = {
        'title_text': 'Simulation time',
        'tickmode': 'array',
        'tickvals': ticks,
        'ticktext': [seconds_to_clock(tick) for tick in ticks],
    }
    if row is None or col is None:
        fig.update_xaxes(**axis_args)
    else:
        fig.update_xaxes(**axis_args, row=row, col=col)


def seconds_to_minutes(value: Any) -> float:
    seconds = safe_float(value)
    return seconds / 60 if math.isfinite(seconds) else math.nan


def format_duration(value: Any) -> str:
    minutes = seconds_to_minutes(value)
    if not math.isfinite(minutes):
        return 'n/a'
    if minutes >= 90:
        return f'{minutes / 60:.1f} h'
    return f'{minutes:.1f} min'


def format_percent(value: Any) -> str:
    number = safe_float(value)
    return 'n/a' if not math.isfinite(number) else f'{number * 100:.1f}%'


def format_number(value: Any, decimals: int = 0) -> str:
    number = safe_float(value)
    if not math.isfinite(number):
        return 'n/a'
    return f'{number:,.{decimals}f}'


def main() -> None:
    parser = argparse.ArgumentParser(description='Build the simulation analysis dashboard.')
    parser.add_argument('--run-id', default=None, help='Run ID to use for detailed charts. Defaults to latest run.')
    parser.add_argument('--log-dir', default=LOG_DIR, help='Directory containing simulation log files.')
    parser.add_argument('--output', default=DASHBOARD_OUTPUT_PATH, help='HTML output path.')
    args = parser.parse_args()

    output_path = create_dashboard(log_dir=args.log_dir, output_path=args.output, run_id=args.run_id)
    print(f'Wrote dashboard to {output_path}')


if __name__ == '__main__':
    main()
