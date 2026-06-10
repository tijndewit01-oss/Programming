import csv
import json
import os
import uuid
from datetime import datetime


class SimulationLogger:
    """Collect simulation rows in memory and write appendable CSV/JSONL outputs."""

    CSV_SCHEMAS = {
        'visitor_log.csv': [
            'run_id', 'visitor_id', 'mode', 'start_node_name', 'start_node',
            'depart_time', 'arrival_time', 'completed', 'final_state',
        ],
        'arrival_funnel_log.csv': [
            'run_id', 'visitor_id', 'sim_time', 'state', 'mode', 'location',
        ],
        'car_log.csv': [
            'run_id', 'car_id', 'source_node', 'capacity', 'passenger_count',
            'depart_time', 'road_arrival_time', 'parked_time', 'route_length_m',
        ],
        'bus_log.csv': [
            'run_id', 'bus_id', 'trip_id', 'depart_time', 'arrival_time',
            'return_arrival_time', 'passenger_count', 'capacity',
            'load_factor', 'station_queue_left',
        ],
        'segment_density_log.csv': [
            'run_id', 'sim_time', 'event_type', 'actor_type', 'actor_id',
            'u', 'v', 'segment_id', 'occupancy', 'rho_max', 'length_m',
        ],
    }

    def __init__(self, output_dir, run_id=None):
        self.output_dir = output_dir
        self.run_id = run_id or self._make_run_id()
        self._counters = {}
        self._rows = {filename: [] for filename in self.CSV_SCHEMAS}
        self._scenario_summaries = []
        self._visitors = {}

    def _make_run_id(self):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{stamp}_{uuid.uuid4().hex[:8]}"

    def next_id(self, entity_name):
        self._counters[entity_name] = self._counters.get(entity_name, 0) + 1
        return self._counters[entity_name]

    def register_visitor(self, visitor_id, mode, start_node_name, start_node, depart_time):
        self._visitors[visitor_id] = {
            'run_id': self.run_id,
            'visitor_id': visitor_id,
            'mode': mode,
            'start_node_name': start_node_name,
            'start_node': start_node,
            'depart_time': depart_time,
            'arrival_time': '',
            'completed': False,
            'final_state': 'generated',
        }

    def log_visitor_state(self, visitor_id, sim_time, state, mode='', location=''):
        if visitor_id in self._visitors:
            self._visitors[visitor_id]['final_state'] = state
        self._rows['arrival_funnel_log.csv'].append({
            'run_id': self.run_id,
            'visitor_id': visitor_id,
            'sim_time': sim_time,
            'state': state,
            'mode': mode,
            'location': location,
        })

    def complete_visitor(self, visitor_id, arrival_time):
        if visitor_id not in self._visitors:
            return
        self._visitors[visitor_id]['arrival_time'] = arrival_time
        self._visitors[visitor_id]['completed'] = True
        self._visitors[visitor_id]['final_state'] = 'scanned'

    def log_car(self, **row):
        self._rows['car_log.csv'].append(self._with_run_id(row))

    def log_bus_trip(self, **row):
        self._rows['bus_log.csv'].append(self._with_run_id(row))

    def log_segment_density(self, **row):
        self._rows['segment_density_log.csv'].append(self._with_run_id(row))

    def log_scenario_summary(self, summary):
        summary = dict(summary)
        summary['run_id'] = self.run_id
        self._scenario_summaries.append(self._json_safe(summary))

    def visitor_count(self):
        return len(self._visitors)

    def completed_visitor_count(self):
        return sum(1 for visitor in self._visitors.values() if visitor['completed'])

    def _with_run_id(self, row):
        output = dict(row)
        output['run_id'] = self.run_id
        return output

    def _json_safe(self, value):
        if isinstance(value, dict):
            return {str(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(v) for v in value]
        if callable(value):
            return repr(value)
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    def flush(self):
        os.makedirs(self.output_dir, exist_ok=True)
        self._rows['visitor_log.csv'] = list(self._visitors.values())

        for filename, fieldnames in self.CSV_SCHEMAS.items():
            path = os.path.join(self.output_dir, filename)
            should_write_header = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                if should_write_header:
                    writer.writeheader()
                for row in self._rows[filename]:
                    writer.writerow(row)

        summary_path = os.path.join(self.output_dir, 'scenario_summary.jsonl')
        with open(summary_path, 'a') as f:
            for summary in self._scenario_summaries:
                f.write(json.dumps(summary, sort_keys=True) + '\n')
