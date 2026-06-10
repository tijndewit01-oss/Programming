"""Generate replay-oriented visualisations from simulation log files.

Prompt 3 scope: create a standalone interactive simulation replay, not the
full scenario-analysis dashboard.
"""

from __future__ import annotations

import bisect
import json
import math
import os
import pickle
from collections import Counter
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config


LOG_DIR = config.LOGGING['OutputDir']
NETWORK_PATH = os.path.join('INPUT_Data_Files', 'network.pkl')
REPLAY_OUTPUT_PATH = os.path.join('OUTPUT Data Files', 'simulation_replay.html')

FRAME_STEP_SECONDS = 60

ROAD_BUCKETS = [
    ('free', 'Free', 0.25, '#2ca25f', 2.5),
    ('busy', 'Busy', 0.50, '#fdd835', 3.0),
    ('congested', 'Congested', 0.75, '#fb8c00', 3.5),
    ('jammed', 'Very congested', math.inf, '#d73027', 4.5),
]

QUEUE_ORDER = [
    ('shuttle_bus_queue', 'Shuttle queue'),
    ('ticket_scan_queue', 'Ticket scan'),
    ('parking_entry_queue', 'Parking entry'),
    ('car_queues_total', 'Car pickup queues'),
    ('parking_lot_occupancy', 'Parked cars'),
]

QUEUE_COLORS = ['#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6', '#10b981']

VISITOR_STATES = [
    ('not_started', 'Not started'),
    ('generated', 'Generated'),
    ('walking_to_bus', 'Walking to bus'),
    ('waiting_bus', 'Waiting bus'),
    ('in_bus', 'In bus'),
    ('waiting_car', 'Waiting car'),
    ('in_car', 'In car'),
    ('parking', 'Parking'),
    ('walking_ticket', 'Walking ticket'),
    ('waiting_ticket', 'Waiting ticket'),
    ('scanning', 'Scanning'),
    ('scanned', 'Scanned'),
]

STATE_COLORS = [
    '#d1d5db',
    '#64748b',
    '#38bdf8',
    '#2563eb',
    '#1d4ed8',
    '#c084fc',
    '#7c3aed',
    '#10b981',
    '#f59e0b',
    '#ef4444',
    '#991b1b',
    '#16a34a',
]

BUS_COLORS = ['#111827', '#0f766e', '#7c2d12', '#581c87', '#1e40af']

LOCATION_STYLES = {
    'car_entry': {'color': '#8b5cf6', 'symbol': 'circle', 'size': 9},
    'train_station': {'color': '#0ea5e9', 'symbol': 'diamond', 'size': 13},
    'festival': {'color': '#dc2626', 'symbol': 'star', 'size': 15},
    'merged': {'color': '#be123c', 'symbol': 'star-diamond', 'size': 16},
}


def load_latest_run_id(log_dir: str = LOG_DIR) -> str:
    """Return the most recent run_id, preferring scenario_summary.jsonl."""

    summary_path = os.path.join(log_dir, 'scenario_summary.jsonl')
    if os.path.exists(summary_path):
        latest_run_id = ''
        with open(summary_path) as f:
            for line in f:
                if not line.strip():
                    continue
                latest_run_id = json.loads(line).get('run_id', latest_run_id)
        if latest_run_id:
            return latest_run_id

    for filename in (
        'visitor_log.csv',
        'arrival_funnel_log.csv',
        'segment_density_log.csv',
        'queue_log.csv',
    ):
        path = os.path.join(log_dir, filename)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, usecols=['run_id'])
        if not df.empty:
            return str(df['run_id'].iloc[-1])

    raise FileNotFoundError(f'No simulation logs found in {log_dir!r}')


def load_logs(log_dir: str = LOG_DIR, run_id: str | None = None) -> tuple[str, dict[str, pd.DataFrame], dict[str, Any]]:
    """Load all replay inputs for a single run."""

    selected_run_id = run_id or load_latest_run_id(log_dir)
    csv_files = {
        'segments': 'segment_density_log.csv',
        'queues': 'queue_log.csv',
        'funnel': 'arrival_funnel_log.csv',
        'buses': 'bus_log.csv',
        'visitors': 'visitor_log.csv',
    }

    logs: dict[str, pd.DataFrame] = {}
    for key, filename in csv_files.items():
        path = os.path.join(log_dir, filename)
        if not os.path.exists(path):
            logs[key] = pd.DataFrame()
            continue
        df = pd.read_csv(path)
        if 'run_id' in df.columns:
            df = df[df['run_id'].astype(str) == str(selected_run_id)].copy()
        for column in ('sim_time', 'depart_time', 'arrival_time', 'return_arrival_time', 'return_drive_time'):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors='coerce')
        logs[key] = df

    summary = load_summary(log_dir, selected_run_id)
    return selected_run_id, logs, summary


def load_summary(log_dir: str, run_id: str) -> dict[str, Any]:
    summary_path = os.path.join(log_dir, 'scenario_summary.jsonl')
    if not os.path.exists(summary_path):
        return {}

    selected: dict[str, Any] = {}
    with open(summary_path) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get('run_id')) == str(run_id):
                selected = row
    return selected


def load_network(network_path: str = NETWORK_PATH) -> tuple[dict[str, dict[str, Any]], dict[int, tuple[float, float]], tuple[float, float, float, float]]:
    """Load the road network and convert nodes/edges into Plotly-ready geometry."""

    with open(network_path, 'rb') as f:
        graph = pickle.load(f)

    node_lookup = {
        int(node): (float(data['x']), float(data['y']))
        for node, data in graph.nodes(data=True)
        if 'x' in data and 'y' in data
    }

    edge_lookup: dict[str, dict[str, Any]] = {}
    all_x: list[float] = []
    all_y: list[float] = []

    for u, v, data in graph.edges(data=True):
        coords = edge_coordinates(graph, int(u), int(v), data)
        if not coords:
            continue

        x_values = [float(x) for x, _ in coords]
        y_values = [float(y) for _, y in coords]
        segment_id = f'{int(u)}->{int(v)}'
        edge_lookup[segment_id] = {
            'x': x_values,
            'y': y_values,
            'coords': list(zip(x_values, y_values)),
            'length_m': float(data.get('length', 0) or 0),
            'name': data.get('name', segment_id),
        }
        all_x.extend(x_values)
        all_y.extend(y_values)

    bounds = (
        min(all_x),
        max(all_x),
        min(all_y),
        max(all_y),
    )
    return edge_lookup, node_lookup, bounds


def edge_coordinates(graph: Any, u: int, v: int, data: dict[str, Any]) -> list[tuple[float, float]]:
    geometry = data.get('geometry')
    if geometry is not None and hasattr(geometry, 'coords'):
        return [(float(x), float(y)) for x, y in geometry.coords]

    if u in graph.nodes and v in graph.nodes:
        start = graph.nodes[u]
        end = graph.nodes[v]
        if 'x' in start and 'y' in start and 'x' in end and 'y' in end:
            return [
                (float(start['x']), float(start['y'])),
                (float(end['x']), float(end['y'])),
            ]
    return []


def build_frame_times(logs: dict[str, pd.DataFrame], summary: dict[str, Any], step_seconds: int) -> list[float]:
    start_time = summary.get('event_start_time') or config.SIMULATION['EventStartTime']
    end_time = summary.get('finished_at') or summary.get('event_ending_time') or config.SIMULATION['EventEndingTime']

    observed_times: list[float] = []
    for key in ('segments', 'queues', 'funnel'):
        df = logs.get(key, pd.DataFrame())
        if not df.empty and 'sim_time' in df.columns:
            observed_times.extend(df['sim_time'].dropna().astype(float).tolist())

    if observed_times:
        start_time = min(float(start_time), min(observed_times))
        end_time = max(float(end_time), max(observed_times))

    start = int(math.floor(float(start_time) / step_seconds) * step_seconds)
    end = int(math.ceil(float(end_time) / step_seconds) * step_seconds)
    frame_times = [float(t) for t in range(start, end + 1, step_seconds)]
    if frame_times[-1] < float(end_time):
        frame_times.append(float(end_time))
    return frame_times


def build_static_network_payload(edge_lookup: dict[str, dict[str, Any]]) -> dict[str, list[float | None]]:
    x_values: list[float | None] = []
    y_values: list[float | None] = []
    for edge in edge_lookup.values():
        x_values.extend(edge['x'])
        y_values.extend(edge['y'])
        x_values.append(None)
        y_values.append(None)
    return {'x': x_values, 'y': y_values}


def build_location_marker_groups(node_lookup: dict[int, tuple[float, float]]) -> list[dict[str, Any]]:
    """Build map markers for static event locations, merged per physical node."""

    poi_rows: list[dict[str, Any]] = []
    for start_name, node_id in config.ROAD_NETWORK['StartNodes'].items():
        poi_rows.append({
            'node_id': int(node_id),
            'label': f'Car entry {start_name}',
            'legend_group': 'Car entry nodes',
            'style': 'car_entry',
        })

    poi_rows.extend([
        {
            'node_id': int(config.ROAD_NETWORK['Bus_start']),
            'label': 'Train station / shuttle stop',
            'legend_group': 'Train station / shuttle stop',
            'style': 'train_station',
        },
        {
            'node_id': int(config.ROAD_NETWORK['Parkinglot']),
            'label': 'Car parking',
            'legend_group': 'Car parking',
            'style': 'festival',
        },
        {
            # No separate festival-entrance node exists in config yet; current
            # visitor logic treats the parking/ticket-scan area as the merge point.
            'node_id': int(config.ROAD_NETWORK['Parkinglot']),
            'label': 'Festival entrance',
            'legend_group': 'Festival entrance',
            'style': 'festival',
        },
    ])

    by_node: dict[int, list[dict[str, Any]]] = {}
    for row in poi_rows:
        if row['node_id'] not in node_lookup:
            continue
        by_node.setdefault(row['node_id'], []).append(row)

    marker_groups: dict[str, dict[str, Any]] = {}
    for node_id, rows in by_node.items():
        x, y = node_lookup[node_id]
        labels = [row['label'] for row in rows]
        styles = {row['style'] for row in rows}
        is_merged = len(rows) > 1 and len({row['legend_group'] for row in rows}) > 1
        style_key = 'merged' if is_merged else rows[0]['style']
        style = LOCATION_STYLES[style_key]
        legend_name = ' & '.join(labels) if is_merged else rows[0]['legend_group']

        group = marker_groups.setdefault(legend_name, {
            'name': legend_name,
            'x': [],
            'y': [],
            'text': [],
            'hovertext': [],
            'style': style,
        })
        group['x'].append(x)
        group['y'].append(y)
        group['text'].append(' & '.join(labels) if is_merged else rows[0]['label'])
        group['hovertext'].append(
            f"{' & '.join(labels)}<br>Node {node_id}<br>lon {x:.6f}, lat {y:.6f}"
        )

    return sorted(
        marker_groups.values(),
        key=lambda group: (
            0 if group['name'] == 'Car entry nodes' else 1,
            group['name'],
        ),
    )


def build_road_snapshots(segment_log: pd.DataFrame, edge_lookup: dict[str, dict[str, Any]]) -> dict[float, list[dict[str, list[float | None]]]]:
    if segment_log.empty:
        return {}

    snapshots = segment_log[segment_log['event_type'] == 'snapshot'].copy()
    if snapshots.empty:
        return {}

    snapshots['sim_time'] = pd.to_numeric(snapshots['sim_time'], errors='coerce')
    snapshots = snapshots.dropna(subset=['sim_time'])

    road_snapshots: dict[float, list[dict[str, list[float | None]]]] = {}
    for sim_time, rows in snapshots.groupby('sim_time', sort=True):
        road_snapshots[float(sim_time)] = road_bucket_payloads(rows, edge_lookup)
    return road_snapshots


def road_bucket_payloads(rows: pd.DataFrame, edge_lookup: dict[str, dict[str, Any]]) -> list[dict[str, list[float | None]]]:
    # Seed empty buckets with None so Plotly still shows every congestion
    # category in the legend before all categories appear in the animation.
    payloads = [{'x': [None], 'y': [None]} for _ in ROAD_BUCKETS]

    for row in rows.itertuples(index=False):
        segment_id = str(getattr(row, 'segment_id', ''))
        edge = edge_lookup.get(segment_id)
        if edge is None:
            u = getattr(row, 'u', None)
            v = getattr(row, 'v', None)
            if pd.notna(u) and pd.notna(v):
                edge = edge_lookup.get(f'{int(u)}->{int(v)}')
        if edge is None:
            continue

        ratio = safe_float(getattr(row, 'congestion_ratio', 0), default=0.0)
        bucket_index = road_bucket_index(ratio)
        payloads[bucket_index]['x'].extend(edge['x'])
        payloads[bucket_index]['y'].extend(edge['y'])
        payloads[bucket_index]['x'].append(None)
        payloads[bucket_index]['y'].append(None)

    return payloads


def road_bucket_index(congestion_ratio: float) -> int:
    for index, (_, _, upper_bound, _, _) in enumerate(ROAD_BUCKETS):
        if congestion_ratio <= upper_bound:
            return index
    return len(ROAD_BUCKETS) - 1


def build_queue_series(queue_log: pd.DataFrame, frame_times: list[float]) -> dict[float, dict[str, float]]:
    empty = {name: 0.0 for name, _ in QUEUE_ORDER}
    if queue_log.empty:
        return {time: dict(empty) for time in frame_times}

    snapshots = queue_log[queue_log['event_type'] == 'snapshot'].copy()
    if snapshots.empty:
        snapshots = queue_log.copy()
    snapshots['sim_time'] = pd.to_numeric(snapshots['sim_time'], errors='coerce')
    snapshots['length'] = pd.to_numeric(snapshots['length'], errors='coerce').fillna(0)
    snapshots = snapshots.dropna(subset=['sim_time'])

    pivot = snapshots.pivot_table(
        index='sim_time',
        columns='queue_name',
        values='length',
        aggfunc='last',
    ).sort_index()
    frame_index = pd.Index(frame_times, name='sim_time')
    pivot = pivot.reindex(pivot.index.union(frame_index)).sort_index().ffill().reindex(frame_index).fillna(0)

    car_queue_columns = [column for column in pivot.columns if str(column).startswith('car_queue_')]
    series: dict[float, dict[str, float]] = {}
    for sim_time, row in pivot.iterrows():
        values: dict[str, float] = {}
        values['car_queues_total'] = float(row[car_queue_columns].sum()) if car_queue_columns else 0.0
        for queue_name, _ in QUEUE_ORDER:
            if queue_name == 'car_queues_total':
                continue
            values[queue_name] = safe_float(row.get(queue_name, 0), default=0.0)
        series[float(sim_time)] = values
    return series


def build_visitor_state_series(funnel_log: pd.DataFrame, frame_times: list[float], summary: dict[str, Any]) -> dict[float, dict[str, int]]:
    total_visitors = int(summary.get('visitors_generated') or summary.get('number_visitors_config') or 0)
    if funnel_log.empty:
        return {
            time: {'not_started': total_visitors}
            for time in frame_times
        }

    events = funnel_log.copy().reset_index(drop=True)
    events['_row_order'] = range(len(events))
    events['sim_time'] = pd.to_numeric(events['sim_time'], errors='coerce')
    events = events.dropna(subset=['sim_time']).sort_values(['sim_time', '_row_order'], kind='mergesort')
    if total_visitors <= 0:
        total_visitors = int(events['visitor_id'].nunique())

    visitor_states: dict[Any, str] = {}
    rows = list(events[['sim_time', 'visitor_id', 'state']].itertuples(index=False, name=None))
    row_index = 0
    state_series: dict[float, dict[str, int]] = {}

    for frame_time in frame_times:
        while row_index < len(rows) and float(rows[row_index][0]) <= frame_time:
            _, visitor_id, state = rows[row_index]
            visitor_states[visitor_id] = str(state)
            row_index += 1

        counts = Counter(visitor_states.values())
        counts['not_started'] = max(0, total_visitors - len(visitor_states))
        state_series[frame_time] = {state: int(counts.get(state, 0)) for state, _ in VISITOR_STATES}

    return state_series


def build_bus_intervals(segment_log: pd.DataFrame) -> dict[int, list[dict[str, Any]]]:
    if segment_log.empty:
        return {}

    bus_events = segment_log[segment_log['actor_type'] == 'bus'].copy()
    if bus_events.empty:
        return {}

    bus_events['_row_order'] = range(len(bus_events))
    bus_events['sim_time'] = pd.to_numeric(bus_events['sim_time'], errors='coerce')
    bus_events = bus_events.dropna(subset=['sim_time', 'actor_id'])
    bus_events = bus_events.sort_values(['actor_id', 'sim_time', '_row_order'], kind='mergesort')

    intervals_by_bus: dict[int, list[dict[str, Any]]] = {}
    for actor_id, rows in bus_events.groupby('actor_id', sort=True):
        bus_id = int(actor_id)
        pending_enter: Any | None = None
        intervals: list[dict[str, Any]] = []
        for row in rows.itertuples(index=False):
            event_type = str(row.event_type)
            if event_type in ('enter', 'enter_return'):
                pending_enter = row
                continue
            if event_type not in ('exit', 'exit_return') or pending_enter is None:
                continue

            start = float(pending_enter.sim_time)
            end = float(row.sim_time)
            if end >= start:
                intervals.append({
                    'start': start,
                    'end': end,
                    'segment_id': str(pending_enter.segment_id),
                    'u': int(pending_enter.u),
                    'v': int(pending_enter.v),
                    'direction': 'return' if event_type == 'exit_return' else 'outbound',
                })
            pending_enter = None
        intervals_by_bus[bus_id] = intervals

    return intervals_by_bus


def build_bus_trips(bus_log: pd.DataFrame) -> dict[int, list[dict[str, float]]]:
    if bus_log.empty:
        return {}

    trips_by_bus: dict[int, list[dict[str, float]]] = {}
    for bus_id, rows in bus_log.sort_values(['bus_id', 'depart_time']).groupby('bus_id', sort=True):
        trips: list[dict[str, float]] = []
        for row in rows.itertuples(index=False):
            depart = safe_float(row.depart_time)
            arrival = safe_float(row.arrival_time)
            return_arrival = safe_float(row.return_arrival_time)
            return_drive = safe_float(getattr(row, 'return_drive_time', math.nan))
            return_depart = return_arrival - return_drive if math.isfinite(return_arrival) and math.isfinite(return_drive) else math.nan
            trips.append({
                'depart': depart,
                'arrival': arrival,
                'return_depart': return_depart,
                'return_arrival': return_arrival,
            })
        trips_by_bus[int(bus_id)] = trips
    return trips_by_bus


def build_bus_position_series(
    frame_times: list[float],
    intervals_by_bus: dict[int, list[dict[str, Any]]],
    trips_by_bus: dict[int, list[dict[str, float]]],
    edge_lookup: dict[str, dict[str, Any]],
    node_lookup: dict[int, tuple[float, float]],
) -> dict[float, dict[str, list[Any]]]:
    bus_ids = sorted(set(intervals_by_bus) | set(trips_by_bus))
    source = int(config.ROAD_NETWORK['Bus_start'])
    destination = int(config.ROAD_NETWORK['Parkinglot'])
    station_xy = node_lookup.get(source)
    festival_xy = node_lookup.get(destination)

    series: dict[float, dict[str, list[Any]]] = {}
    for frame_time in frame_times:
        x_values: list[float] = []
        y_values: list[float] = []
        labels: list[str] = []
        hover: list[str] = []
        colors: list[str] = []

        for bus_id in bus_ids:
            position = active_bus_position(bus_id, frame_time, intervals_by_bus, edge_lookup)
            status = 'Driving'
            if position is None:
                location = stationary_bus_location(frame_time, trips_by_bus.get(bus_id, []))
                if location == 'festival' and festival_xy:
                    position = festival_xy
                    status = 'At festival'
                elif station_xy:
                    position = station_xy
                    status = 'At bus stop'

            if position is None:
                continue

            x_values.append(position[0])
            y_values.append(position[1])
            labels.append(f'Bus {bus_id}')
            hover.append(f'Bus {bus_id}<br>{status}<br>{seconds_to_clock(frame_time)}')
            colors.append(BUS_COLORS[(bus_id - 1) % len(BUS_COLORS)])

        series[frame_time] = {
            'x': x_values,
            'y': y_values,
            'text': labels,
            'hovertext': hover,
            'color': colors,
        }
    return series


def active_bus_position(
    bus_id: int,
    frame_time: float,
    intervals_by_bus: dict[int, list[dict[str, Any]]],
    edge_lookup: dict[str, dict[str, Any]],
) -> tuple[float, float] | None:
    for interval in intervals_by_bus.get(bus_id, []):
        if interval['start'] <= frame_time <= interval['end']:
            edge = edge_lookup.get(interval['segment_id'])
            if edge is None:
                return None
            duration = max(0.001, interval['end'] - interval['start'])
            fraction = (frame_time - interval['start']) / duration
            return interpolate_polyline(edge['coords'], fraction)
    return None


def stationary_bus_location(frame_time: float, trips: list[dict[str, float]]) -> str:
    for trip in trips:
        depart = trip['depart']
        arrival = trip['arrival']
        return_depart = trip['return_depart']
        return_arrival = trip['return_arrival']

        if math.isfinite(depart) and frame_time < depart:
            return 'station'
        if math.isfinite(arrival) and math.isfinite(return_depart) and arrival < frame_time < return_depart:
            return 'festival'
        if math.isfinite(return_arrival) and frame_time <= return_arrival:
            return 'driving'
    return 'station'


def interpolate_polyline(coords: list[tuple[float, float]], fraction: float) -> tuple[float, float] | None:
    if not coords:
        return None
    if fraction <= 0:
        return coords[0]
    if fraction >= 1:
        return coords[-1]

    segment_lengths: list[float] = []
    total_length = 0.0
    for start, end in zip(coords[:-1], coords[1:]):
        length = math.dist(start, end)
        segment_lengths.append(length)
        total_length += length

    if total_length <= 0:
        return coords[0]

    target = total_length * fraction
    travelled = 0.0
    for index, length in enumerate(segment_lengths):
        if travelled + length >= target:
            local_fraction = (target - travelled) / max(length, 0.000001)
            start_x, start_y = coords[index]
            end_x, end_y = coords[index + 1]
            return (
                start_x + (end_x - start_x) * local_fraction,
                start_y + (end_y - start_y) * local_fraction,
            )
        travelled += length
    return coords[-1]


def build_simulation_replay(
    log_dir: str = LOG_DIR,
    network_path: str = NETWORK_PATH,
    output_path: str = REPLAY_OUTPUT_PATH,
    run_id: str | None = None,
    frame_step_seconds: int = FRAME_STEP_SECONDS,
) -> str:
    selected_run_id, logs, summary = load_logs(log_dir, run_id)
    edge_lookup, node_lookup, bounds = load_network(network_path)
    frame_times = build_frame_times(logs, summary, frame_step_seconds)

    road_snapshots = build_road_snapshots(logs['segments'], edge_lookup)
    road_snapshot_times = sorted(road_snapshots)
    queue_series = build_queue_series(logs['queues'], frame_times)
    visitor_state_series = build_visitor_state_series(logs['funnel'], frame_times, summary)
    bus_intervals = build_bus_intervals(logs['segments'])
    bus_trips = build_bus_trips(logs['buses'])
    bus_series = build_bus_position_series(frame_times, bus_intervals, bus_trips, edge_lookup, node_lookup)
    location_marker_groups = build_location_marker_groups(node_lookup)

    fig = create_replay_figure(
        run_id=selected_run_id,
        summary=summary,
        edge_lookup=edge_lookup,
        bounds=bounds,
        frame_times=frame_times,
        road_snapshots=road_snapshots,
        road_snapshot_times=road_snapshot_times,
        queue_series=queue_series,
        visitor_state_series=visitor_state_series,
        bus_series=bus_series,
        location_marker_groups=location_marker_groups,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_html(output_path, include_plotlyjs=True, full_html=True)
    return output_path


def create_replay_figure(
    run_id: str,
    summary: dict[str, Any],
    edge_lookup: dict[str, dict[str, Any]],
    bounds: tuple[float, float, float, float],
    frame_times: list[float],
    road_snapshots: dict[float, list[dict[str, list[float | None]]]],
    road_snapshot_times: list[float],
    queue_series: dict[float, dict[str, float]],
    visitor_state_series: dict[float, dict[str, int]],
    bus_series: dict[float, dict[str, list[Any]]],
    location_marker_groups: list[dict[str, Any]],
) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[[{'rowspan': 2}, {}], [None, {}]],
        column_widths=[0.68, 0.32],
        row_heights=[0.46, 0.54],
        horizontal_spacing=0.07,
        vertical_spacing=0.14,
        subplot_titles=(
            'Road congestion and shuttle buses',
            'Queues and parking occupancy',
            'Visitor journey states',
        ),
    )

    first_time = frame_times[0]
    static_network = build_static_network_payload(edge_lookup)
    first_roads = road_payload_at(first_time, road_snapshots, road_snapshot_times)
    first_queues = queue_values_at(first_time, queue_series)
    first_states = state_values_at(first_time, visitor_state_series)
    first_buses = bus_series[first_time]

    fig.add_trace(
        go.Scatter(
            x=static_network['x'],
            y=static_network['y'],
            mode='lines',
            line={'color': '#d1d5db', 'width': 1},
            opacity=0.45,
            hoverinfo='skip',
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    for bucket, payload in zip(ROAD_BUCKETS, first_roads):
        _, label, _, color, width = bucket
        fig.add_trace(
            go.Scatter(
                x=payload['x'],
                y=payload['y'],
                mode='lines',
                name=label,
                line={'color': color, 'width': width},
                hoverinfo='skip',
                legendgroup='roads',
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=first_buses['x'],
            y=first_buses['y'],
            mode='markers+text',
            name='Shuttle bus',
            text=first_buses['text'],
            textposition='top center',
            hovertext=first_buses['hovertext'],
            hovertemplate='%{hovertext}<extra></extra>',
            marker={
                'color': first_buses['color'],
                'size': 14,
                'line': {'color': '#ffffff', 'width': 2},
            },
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=first_queues['values'],
            y=first_queues['labels'],
            orientation='h',
            name='Queue length',
            marker={'color': QUEUE_COLORS},
            text=first_queues['text'],
            textposition='outside',
            hovertemplate='%{y}: %{x:.0f}<extra></extra>',
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Bar(
            x=first_states['values'],
            y=first_states['labels'],
            orientation='h',
            name='Visitors',
            marker={'color': STATE_COLORS},
            text=first_states['text'],
            textposition='outside',
            hovertemplate='%{y}: %{x:.0f}<extra></extra>',
            showlegend=False,
        ),
        row=2,
        col=2,
    )

    add_location_markers(fig, location_marker_groups)

    fig.frames = build_frames(
        run_id=run_id,
        summary=summary,
        frame_times=frame_times,
        road_snapshots=road_snapshots,
        road_snapshot_times=road_snapshot_times,
        queue_series=queue_series,
        visitor_state_series=visitor_state_series,
        bus_series=bus_series,
    )

    configure_layout(fig, run_id, summary, bounds, frame_times, queue_series, visitor_state_series)
    return fig


def add_location_markers(fig: go.Figure, location_marker_groups: list[dict[str, Any]]) -> None:
    for group in location_marker_groups:
        style = group['style']
        fig.add_trace(
            go.Scatter(
                x=group['x'],
                y=group['y'],
                mode='markers+text',
                name=group['name'],
                text=group['text'],
                textposition='bottom center',
                hovertext=group['hovertext'],
                hovertemplate='%{hovertext}<extra></extra>',
                marker={
                    'color': style['color'],
                    'symbol': style['symbol'],
                    'size': style['size'],
                    'line': {'color': '#ffffff', 'width': 1.5},
                },
                showlegend=True,
            ),
            row=1,
            col=1,
        )


def build_frames(
    run_id: str,
    summary: dict[str, Any],
    frame_times: list[float],
    road_snapshots: dict[float, list[dict[str, list[float | None]]]],
    road_snapshot_times: list[float],
    queue_series: dict[float, dict[str, float]],
    visitor_state_series: dict[float, dict[str, int]],
    bus_series: dict[float, dict[str, list[Any]]],
) -> list[go.Frame]:
    frames: list[go.Frame] = []
    for frame_time in frame_times:
        roads = road_payload_at(frame_time, road_snapshots, road_snapshot_times)
        queues = queue_values_at(frame_time, queue_series)
        states = state_values_at(frame_time, visitor_state_series)
        buses = bus_series[frame_time]

        frame_data: list[Any] = []
        for payload in roads:
            frame_data.append(go.Scatter(x=payload['x'], y=payload['y']))
        frame_data.append(
            go.Scatter(
                x=buses['x'],
                y=buses['y'],
                text=buses['text'],
                hovertext=buses['hovertext'],
                marker={'color': buses['color']},
            )
        )
        frame_data.append(
            go.Bar(
                x=queues['values'],
                y=queues['labels'],
                text=queues['text'],
            )
        )
        frame_data.append(
            go.Bar(
                x=states['values'],
                y=states['labels'],
                text=states['text'],
            )
        )

        frames.append(
            go.Frame(
                name=str(int(frame_time)),
                data=frame_data,
                traces=[1, 2, 3, 4, 5, 6, 7],
                layout=go.Layout(title_text=replay_title(run_id, summary, frame_time)),
            )
        )
    return frames


def configure_layout(
    fig: go.Figure,
    run_id: str,
    summary: dict[str, Any],
    bounds: tuple[float, float, float, float],
    frame_times: list[float],
    queue_series: dict[float, dict[str, float]],
    visitor_state_series: dict[float, dict[str, int]],
) -> None:
    min_x, max_x, min_y, max_y = bounds
    pad_x = (max_x - min_x) * 0.06
    pad_y = (max_y - min_y) * 0.06

    queue_max = max(
        max(values.values()) if values else 0
        for values in queue_series.values()
    )
    state_max = max(
        max(values.values()) if values else 0
        for values in visitor_state_series.values()
    )
    queue_axis_max = max(10, queue_max * 1.18)
    state_axis_max = max(10, state_max * 1.12)

    fig.update_layout(
        title=replay_title(run_id, summary, frame_times[0]),
        template='plotly_white',
        height=850,
        margin={'l': 42, 'r': 42, 't': 86, 'b': 105},
        legend={
            'orientation': 'h',
            'yanchor': 'bottom',
            'y': 1.02,
            'xanchor': 'left',
            'x': 0,
        },
        hovermode='closest',
        updatemenus=[
            {
                'type': 'buttons',
                'direction': 'left',
                'x': 0.02,
                'y': -0.11,
                'xanchor': 'left',
                'yanchor': 'top',
                'buttons': [
                    {
                        'label': 'Play',
                        'method': 'animate',
                        'args': [
                            None,
                            {
                                'frame': {'duration': 220, 'redraw': True},
                                'transition': {'duration': 0},
                                'fromcurrent': True,
                                'mode': 'immediate',
                            },
                        ],
                    },
                    {
                        'label': 'Pause',
                        'method': 'animate',
                        'args': [
                            [None],
                            {
                                'frame': {'duration': 0, 'redraw': False},
                                'transition': {'duration': 0},
                                'mode': 'immediate',
                            },
                        ],
                    },
                ],
            }
        ],
        sliders=[build_slider(frame_times)],
    )

    fig.update_xaxes(title_text='Longitude', range=[min_x - pad_x, max_x + pad_x], row=1, col=1)
    fig.update_yaxes(title_text='Latitude', range=[min_y - pad_y, max_y + pad_y], row=1, col=1)
    fig.update_yaxes(scaleanchor='x', scaleratio=1, row=1, col=1)

    fig.update_xaxes(title_text='Count', range=[0, queue_axis_max], zeroline=True, row=1, col=2)
    fig.update_yaxes(autorange='reversed', row=1, col=2)

    fig.update_xaxes(title_text='Visitors', range=[0, state_axis_max], zeroline=True, row=2, col=2)
    fig.update_yaxes(autorange='reversed', row=2, col=2)


def build_slider(frame_times: list[float]) -> dict[str, Any]:
    steps = []
    for index, frame_time in enumerate(frame_times):
        label = seconds_to_clock(frame_time) if index % 30 == 0 or index == len(frame_times) - 1 else ''
        steps.append({
            'method': 'animate',
            'label': label,
            'args': [
                [str(int(frame_time))],
                {
                    'mode': 'immediate',
                    'frame': {'duration': 0, 'redraw': True},
                    'transition': {'duration': 0},
                },
            ],
        })

    return {
        'active': 0,
        'x': 0.14,
        'y': -0.10,
        'len': 0.82,
        'xanchor': 'left',
        'yanchor': 'top',
        'currentvalue': {
            'prefix': 'Simulation time: ',
            'font': {'size': 13},
        },
        'pad': {'t': 25, 'b': 10},
        'steps': steps,
    }


def road_payload_at(
    frame_time: float,
    road_snapshots: dict[float, list[dict[str, list[float | None]]]],
    road_snapshot_times: list[float],
) -> list[dict[str, list[float | None]]]:
    if not road_snapshot_times:
        return [{'x': [], 'y': []} for _ in ROAD_BUCKETS]

    index = bisect.bisect_right(road_snapshot_times, frame_time) - 1
    if index < 0:
        index = 0
    return road_snapshots[road_snapshot_times[index]]


def queue_values_at(frame_time: float, queue_series: dict[float, dict[str, float]]) -> dict[str, list[Any]]:
    values_by_name = queue_series[frame_time]
    labels = [label for _, label in QUEUE_ORDER]
    values = [values_by_name.get(name, 0.0) for name, _ in QUEUE_ORDER]
    return {
        'labels': labels,
        'values': values,
        'text': [format_count(value) for value in values],
    }


def state_values_at(frame_time: float, visitor_state_series: dict[float, dict[str, int]]) -> dict[str, list[Any]]:
    values_by_state = visitor_state_series[frame_time]
    labels = [label for _, label in VISITOR_STATES]
    values = [values_by_state.get(state, 0) for state, _ in VISITOR_STATES]
    return {
        'labels': labels,
        'values': values,
        'text': [format_count(value) for value in values],
    }


def replay_title(run_id: str, summary: dict[str, Any], frame_time: float) -> str:
    visitors_completed = summary.get('visitors_completed', '?')
    visitors_generated = summary.get('visitors_generated', summary.get('number_visitors_config', '?'))
    return (
        f'Simulation replay | run {run_id} | {seconds_to_clock(frame_time)} '
        f'| completed {visitors_completed}/{visitors_generated}'
    )


def seconds_to_clock(seconds: float) -> str:
    if not math.isfinite(float(seconds)):
        return ''
    total = int(round(float(seconds)))
    hours = (total // 3600) % 24
    minutes = (total % 3600) // 60
    return f'{hours:02d}:{minutes:02d}'


def format_count(value: float) -> str:
    return f'{float(value):,.0f}'


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        output = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(output):
        return default
    return output


def main() -> None:
    output_path = build_simulation_replay()
    print(f'Wrote replay to {output_path}')


if __name__ == '__main__':
    main()
