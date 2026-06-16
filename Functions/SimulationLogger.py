"""SimulationLogger: buffers simulation events and writes them to CSV/JSONL.

Components push rows into the logger during a run; the logger holds them in
memory, derives per-visitor phase durations and summary KPIs at the end, and
appends everything to the log files. Each run is tagged with a run_id so several
runs can share the same files (used by the multi-scenario sweep).
"""
import csv
import json
import os
import statistics
import uuid
from datetime import datetime


class SimulationLogger:
    """Collect simulation rows in memory and write appendable CSV/JSONL outputs."""

    # Column order for each output CSV; rows missing a column are written blank.
    CSV_SCHEMAS = {
        'visitor_log.csv': [
            'run_id', 'visitor_id', 'mode', 'start_node_name', 'start_node',
            'depart_time', 'arrival_time', 'completed', 'final_state',
            'total_time', 'walking_time', 'waiting_car_time',
            'waiting_bus_time', 'waiting_ticket_time', 'in_car_time',
            'in_bus_time', 'parking_time', 'scanning_time',
        ],
        'arrival_funnel_log.csv': [
            'run_id', 'visitor_id', 'sim_time', 'state', 'mode', 'location',
        ],
        'car_log.csv': [
            'run_id', 'car_id', 'source_node', 'capacity', 'passenger_count',
            'depart_time', 'road_arrival_time', 'parked_time', 'drive_time',
            'parking_entry_wait', 'parking_entry_service', 'find_space_time',
            'route_length_m',
        ],
        'bus_log.csv': [
            'run_id', 'bus_id', 'trip_id', 'depart_time', 'arrival_time',
            'return_arrival_time', 'passenger_count', 'capacity',
            'load_factor', 'station_queue_left', 'outbound_drive_time',
            'return_drive_time', 'outbound_distance_m', 'return_distance_m',
        ],
        'segment_density_log.csv': [
            'run_id', 'sim_time', 'event_type', 'actor_type', 'actor_id',
            'u', 'v', 'segment_id', 'occupancy', 'background_occupancy',
            'rho_max', 'congestion_ratio', 'speed_ms', 'max_speed_ms', 'length_m',
        ],
        'queue_log.csv': [
            'run_id', 'sim_time', 'queue_name', 'location', 'length',
            'event_type', 'actor_type', 'actor_id',
        ],
    }

    # Per-visitor duration columns accumulated from the state-transition log.
    PHASE_COLUMNS = [
        'walking_time',
        'waiting_car_time',
        'waiting_bus_time',
        'waiting_ticket_time',
        'in_car_time',
        'in_bus_time',
        'parking_time',
        'scanning_time',
    ]

    # Maps each visitor state to the phase column that its duration adds to.
    STATE_DURATION_MAP = {
        'walking_to_bus': 'walking_time',
        'walking_ticket': 'walking_time',
        'waiting_car': 'waiting_car_time',
        'waiting_bus': 'waiting_bus_time',
        'waiting_ticket': 'waiting_ticket_time',
        'in_car': 'in_car_time',
        'in_bus': 'in_bus_time',
        'parking': 'parking_time',
        'scanning': 'scanning_time',
    }

    def __init__(self, output_dir, run_id=None):
        self.output_dir = output_dir
        # Use the supplied run_id, or generate a timestamped unique one.
        self.run_id = run_id or self._make_run_id()
        self._counters = {}                                       # Per-entity ID counters.
        self._rows = {filename: [] for filename in self.CSV_SCHEMAS}  # Buffered rows per file.
        self._scenario_summaries = []
        self._visitors = {}                                      # visitor_id -> accumulating row.
        self.final_time = None

    def _make_run_id(self):
        """Build a unique run_id from the current timestamp plus a random suffix."""
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # uuid4() produces a random UUID; hex[:8] takes the first 8 hex
        # characters as a short uniqueness suffix.
        return f"{stamp}_{uuid.uuid4().hex[:8]}"

    def next_id(self, entity_name):
        """Return the next sequential integer ID for the given entity type."""
        self._counters[entity_name] = self._counters.get(entity_name, 0) + 1
        return self._counters[entity_name]

    def register_visitor(self, visitor_id, mode, start_node_name, start_node, depart_time):
        """Create the in-memory visitor row, with all phase durations zeroed."""
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
            'total_time': '',
            'walking_time': 0.0,
            'waiting_car_time': 0.0,
            'waiting_bus_time': 0.0,
            'waiting_ticket_time': 0.0,
            'in_car_time': 0.0,
            'in_bus_time': 0.0,
            'parking_time': 0.0,
            'scanning_time': 0.0,
        }

    def log_visitor_state(self, visitor_id, sim_time, state, mode='', location=''):
        """Record a visitor state transition and update its latest known state."""
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
        """Mark a visitor as having finished the ticket scan and left the system."""
        if visitor_id not in self._visitors:
            return
        self._visitors[visitor_id]['arrival_time'] = arrival_time
        self._visitors[visitor_id]['completed'] = True
        self._visitors[visitor_id]['final_state'] = 'scanned'

    def log_car(self, **row):
        """Buffer a finished-car row."""
        self._rows['car_log.csv'].append(self._with_run_id(row))

    def log_bus_trip(self, **row):
        """Buffer a completed bus-trip row."""
        self._rows['bus_log.csv'].append(self._with_run_id(row))

    def log_segment_density(self, **row):
        """Buffer a road-segment density-event row."""
        self._rows['segment_density_log.csv'].append(self._with_run_id(row))

    def log_queue(self, **row):
        """Buffer a queue event/snapshot row."""
        self._rows['queue_log.csv'].append(self._with_run_id(row))

    def log_scenario_summary(self, summary):
        """Buffer a scenario-summary dict, tagged with the run_id and JSON-safe."""
        summary = dict(summary)
        summary['run_id'] = self.run_id
        self._scenario_summaries.append(self._json_safe(summary))

    def visitor_count(self):
        """Return the number of visitors registered this run."""
        return len(self._visitors)

    def completed_visitor_count(self):
        """Return the number of visitors that finished the ticket scan."""
        return sum(1 for visitor in self._visitors.values() if visitor['completed'])

    def set_final_time(self, final_time):
        """Record the simulation end time, used to close out unfinished visitors."""
        self.final_time = final_time

    def summary_metrics(self, emission_factors):
        """Compute the headline KPIs for the run (travel times, CO2, peaks, etc.)."""
        self._finalize_visitors()
        visitor_rows = list(self._visitors.values())
        completed_times = [
            row['total_time']
            for row in visitor_rows
            if row['completed'] and row['total_time'] != ''
        ]
        mode_counts = {}
        for row in visitor_rows:
            mode_counts[row['mode']] = mode_counts.get(row['mode'], 0) + 1

        # Turn logged distances into kilometres, then into kg CO2.
        car_distance_km = sum(float(row.get('route_length_m') or 0) for row in self._rows['car_log.csv']) / 1000
        bus_distance_km = sum(
            float(row.get('outbound_distance_m') or 0) + float(row.get('return_distance_m') or 0)
            for row in self._rows['bus_log.csv']
        ) / 1000
        car_co2_kg = car_distance_km * emission_factors['CarKgCO2PerKm']
        bus_co2_kg = bus_distance_km * emission_factors['BusKgCO2PerKm']

        return {
            'mode_counts': mode_counts,
            'avg_travel_time': self._mean(completed_times),
            'median_travel_time': self._median(completed_times),
            'p95_travel_time': self._percentile(completed_times, 95),
            'avg_phase_times': {
                column: self._mean([float(row.get(column) or 0) for row in visitor_rows])
                for column in self.PHASE_COLUMNS
            },
            'peak_queues': self._peak_queues(),
            'max_congestion_ratio': self._max_numeric('segment_density_log.csv', 'congestion_ratio'),
            'car_km': car_distance_km,
            'bus_km': bus_distance_km,
            'car_co2_kg': car_co2_kg,
            'bus_co2_kg': bus_co2_kg,
            'total_co2_kg': car_co2_kg + bus_co2_kg,
        }

    def _with_run_id(self, row):
        """Return a copy of row stamped with the current run_id."""
        output = dict(row)
        output['run_id'] = self.run_id
        return output

    def _json_safe(self, value):
        """Recursively convert a value into something json.dumps can serialise."""
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

    def flush(self, final_time=None):
        """Finalise visitors and append all buffered rows to the output files."""
        if final_time is not None:
            self.final_time = final_time
        os.makedirs(self.output_dir, exist_ok=True)
        self._finalize_visitors()
        self._rows['visitor_log.csv'] = list(self._visitors.values())

        for filename, fieldnames in self.CSV_SCHEMAS.items():
            path = os.path.join(self.output_dir, filename)
            # Rewrite the file header if an older run used a different schema.
            self._migrate_csv_schema(path, fieldnames)
            should_write_header = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, 'a', newline='') as f:
                # extrasaction='ignore' tells DictWriter to silently drop any
                # dict keys not listed in fieldnames, so rows with extra fields
                # do not raise an error.
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                if should_write_header:
                    writer.writeheader()
                for row in self._rows[filename]:
                    writer.writerow(row)

        # Scenario summaries are appended one JSON object per line.
        summary_path = os.path.join(self.output_dir, 'scenario_summary.jsonl')
        with open(summary_path, 'a') as f:
            for summary in self._scenario_summaries:
                f.write(json.dumps(summary, sort_keys=True) + '\n')

    def _finalize_visitors(self):
        """Derive each visitor's phase durations and total time from their events."""
        events_by_visitor = {}
        for row in self._rows['arrival_funnel_log.csv']:
            events_by_visitor.setdefault(row['visitor_id'], []).append(row)

        for visitor_id, visitor in self._visitors.items():
            for column in self.PHASE_COLUMNS:
                visitor[column] = 0.0

            # Each state lasts until the next state event (or until the run ends),
            # and that duration is added to the matching phase column.
            events = sorted(
                events_by_visitor.get(visitor_id, []),
                key=lambda row: float(row['sim_time']),
            )
            for index, event in enumerate(events):
                state = event['state']
                column = self.STATE_DURATION_MAP.get(state)
                if not column:
                    continue
                start = float(event['sim_time'])
                if index + 1 < len(events):
                    end = float(events[index + 1]['sim_time'])
                else:
                    end = self._visitor_end_time(visitor)
                visitor[column] += max(0.0, end - start)

            end_time = self._visitor_end_time(visitor)
            if end_time != '':
                visitor['total_time'] = max(0.0, end_time - float(visitor['depart_time']))

    def _visitor_end_time(self, visitor):
        """Return a visitor's end time: their arrival, else the run's final time."""
        if visitor['arrival_time'] != '':
            return float(visitor['arrival_time'])
        if self.final_time is not None:
            return float(self.final_time)
        return ''

    def _migrate_csv_schema(self, path, fieldnames):
        """Rewrite an existing CSV's header/rows if its columns no longer match."""
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return
        with open(path, newline='') as f:
            reader = csv.DictReader(f)
            old_fieldnames = reader.fieldnames or []
            if old_fieldnames == fieldnames:
                return
            rows = list(reader)
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _peak_queues(self):
        """Return the maximum length reached by each named queue this run."""
        peaks = {}
        for row in self._rows['queue_log.csv']:
            queue_name = row['queue_name']
            length = float(row.get('length') or 0)
            peaks[queue_name] = max(peaks.get(queue_name, 0), length)
        return peaks

    def _max_numeric(self, filename, column):
        """Return the maximum numeric value in one column of a buffered log."""
        values = [
            float(row.get(column) or 0)
            for row in self._rows[filename]
            if row.get(column) not in ('', None)
        ]
        return max(values) if values else 0.0

    def _mean(self, values):
        """Return the mean, or 0.0 for an empty sequence."""
        return statistics.mean(values) if values else 0.0

    def _median(self, values):
        """Return the median, or 0.0 for an empty sequence."""
        return statistics.median(values) if values else 0.0

    def _percentile(self, values, percentile):
        """Return the given percentile via linear interpolation, or 0.0 if empty."""
        if not values:
            return 0.0
        ordered = sorted(values)
        index = (len(ordered) - 1) * percentile / 100
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = index - lower
        return ordered[lower] * (1 - fraction) + ordered[upper] * fraction
