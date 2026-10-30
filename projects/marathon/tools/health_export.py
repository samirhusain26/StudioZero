"""Apple Health export -> one week's running facts (facts.json).

Reads export.zip (Health app > profile > Export All Health Data) or an unzipped export.xml, keeps the running
workouts that start between --from and --to (local dates, inclusive), and writes <out>/facts.json:
per run the watch's distance, time, pace, heart rate, energy, elevation and indoor flag, plus mile splits and a
privacy-trimmed route line from the route GPX. Stdlib only; streams the XML, so a large export is fine.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

RUNNING = 'HKWorkoutActivityTypeRunning'
MI_M = 1609.344
DATE_FMT = '%Y-%m-%d %H:%M:%S %z'


def local(name):
    return name.rsplit('}', 1)[-1]


def parse_date(value):
    return dt.datetime.strptime(value, DATE_FMT)


def to_miles(value, unit):
    value = float(value)
    return {'mi': value, 'km': value / 1.609344, 'm': value / MI_M, 'ft': value / 5280}.get(unit)


def to_seconds(value, unit):
    value = float(value)
    return {'min': value * 60, 's': value, 'sec': value, 'hr': value * 3600, 'h': value * 3600}.get(unit)


def quantity(text):
    """'1234 cm' -> (1234.0, 'cm')."""
    number, _, unit = (text or '').partition(' ')
    try:
        return float(number), unit
    except ValueError:
        return None, unit


def pace(seconds, miles):
    if not seconds or not miles:
        return None
    per = seconds / miles
    return f'{int(per // 60)}:{int(round(per % 60)):02d}'


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def parse_gpx(stream):
    points = []
    for _, el in ET.iterparse(stream):
        if local(el.tag) != 'trkpt':
            continue
        point = {'lat': float(el.get('lat')), 'lon': float(el.get('lon')), 'ele': None, 'time': None}
        for child in el:
            tag = local(child.tag)
            if tag == 'ele':
                point['ele'] = float(child.text)
            elif tag == 'time':
                point['time'] = dt.datetime.fromisoformat(child.text.replace('Z', '+00:00'))
        points.append(point)
        el.clear()
    return points


def route_facts(points, trim_mi):
    """Mile splits, GPS distance, elevation gain and the trimmed route line from GPX points."""
    if len(points) < 2:
        return {}
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine((a['lat'], a['lon']), (b['lat'], b['lon'])))
    total_m = cumulative[-1]

    splits = []
    timed = all(p['time'] for p in points)
    if timed:
        start = points[0]['time']
        boundary, last_t = MI_M, 0.0
        for i in range(1, len(points)):
            while cumulative[i] >= boundary:
                span = cumulative[i] - cumulative[i - 1]
                frac = (boundary - cumulative[i - 1]) / span if span else 0
                t0 = (points[i - 1]['time'] - start).total_seconds()
                t1 = (points[i]['time'] - start).total_seconds()
                t = t0 + frac * (t1 - t0)
                splits.append({'mile': len(splits) + 1, 'seconds': round(t - last_t), 'pace': pace(t - last_t, 1)})
                last_t, boundary = t, boundary + MI_M
        rest_m = total_m - (boundary - MI_M)
        rest_t = (points[-1]['time'] - start).total_seconds() - last_t
        if rest_m > 30:
            rest_mi = rest_m / MI_M
            splits.append({'mile': round(len(splits) + rest_mi, 2), 'seconds': round(rest_t),
                           'pace': pace(rest_t, rest_mi), 'partial': True})

    gain = 0.0
    eles = [p['ele'] for p in points if p['ele'] is not None]
    for a, b in zip(eles, eles[1:]):
        if b > a:
            gain += b - a

    trim_m = trim_mi * MI_M
    kept = [(round(p['lat'], 5), round(p['lon'], 5)) for p, c in zip(points, cumulative)
            if trim_m <= c <= total_m - trim_m]
    step = max(1, math.ceil(len(kept) / 500))
    return {
        'gpsDistanceMi': round(total_m / MI_M, 2),
        'gpsElevationGainFt': round(gain * 3.28084) if eles else None,
        'splits': splits,
        'routeTrimmed': [list(p) for p in kept[::step]],
        'routeTrimMi': trim_mi,
    }


def workout_facts(el):
    start, end = parse_date(el.get('startDate')), parse_date(el.get('endDate'))
    run = {
        'date': start.date().isoformat(),
        'start': start.isoformat(),
        'end': end.isoformat(),
        'source': el.get('sourceName'),
        'durationSec': None, 'distanceMi': None, 'pace': None,
        'avgHr': None, 'minHr': None, 'maxHr': None, 'activeKcal': None,
        'elevationGainFt': None, 'indoor': None, 'temperature': None, 'routeFile': None,
    }
    if el.get('duration'):
        run['durationSec'] = round(to_seconds(el.get('duration'), el.get('durationUnit', 'min')))
    if el.get('totalDistance'):
        run['distanceMi'] = to_miles(el.get('totalDistance'), el.get('totalDistanceUnit', 'mi'))
    for child in el:
        tag = local(child.tag)
        kind = child.get('type', '')
        if tag == 'WorkoutStatistics':
            if kind == 'HKQuantityTypeIdentifierDistanceWalkingRunning' and child.get('sum'):
                run['distanceMi'] = to_miles(child.get('sum'), child.get('unit'))
            elif kind == 'HKQuantityTypeIdentifierHeartRate':
                for key, attr in (('avgHr', 'average'), ('minHr', 'minimum'), ('maxHr', 'maximum')):
                    if child.get(attr):
                        run[key] = round(float(child.get(attr)))
            elif kind == 'HKQuantityTypeIdentifierActiveEnergyBurned' and child.get('sum'):
                run['activeKcal'] = round(float(child.get('sum')))
        elif tag == 'MetadataEntry':
            key, value = child.get('key'), child.get('value')
            if key == 'HKIndoorWorkout':
                run['indoor'] = value == '1'
            elif key == 'HKElevationAscended':
                amount, unit = quantity(value)
                if amount is not None:
                    run['elevationGainFt'] = round(amount / 30.48 if unit == 'cm' else amount * 3.28084 if unit == 'm' else amount)
            elif key == 'HKWeatherTemperature':
                run['temperature'] = value
        elif tag == 'WorkoutRoute':
            for ref in child:
                if local(ref.tag) == 'FileReference':
                    run['routeFile'] = ref.get('path')
    if run['distanceMi'] is not None:
        run['distanceMi'] = round(run['distanceMi'], 2)
        run['pace'] = pace(run['durationSec'], run['distanceMi'])
    return run


class Export:
    """export.zip, an export.xml, or an apple_health_export folder."""

    def __init__(self, path):
        self.zip = zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
        if self.zip:
            names = self.zip.namelist()
            xml_name = next(n for n in names if n.endswith('export.xml') and 'export_cda' not in n)
            self.root = xml_name[:-len('export.xml')]
            self.xml = lambda: self.zip.open(xml_name)
        else:
            xml_path = os.path.join(path, 'export.xml') if os.path.isdir(path) else path
            self.root = os.path.dirname(xml_path)
            self.xml = lambda: open(xml_path, 'rb')

    def open_route(self, ref):
        rel = ref.lstrip('/')
        if self.zip:
            name = self.root + rel
            return self.zip.open(name) if name in self.zip.namelist() else None
        full = os.path.join(self.root, rel)
        return open(full, 'rb') if os.path.exists(full) else None


def collect(path, first, last, trim_mi=0.2):
    export = Export(path)
    runs, other = [], {}
    with export.xml() as stream:
        root = None
        for event, el in ET.iterparse(stream, events=('start', 'end')):
            if root is None:
                root = el
            if event != 'end' or el.tag not in ('Workout', 'Record', 'ActivitySummary'):
                continue
            if el.tag == 'Workout' and first <= parse_date(el.get('startDate')).date() <= last:
                kind = el.get('workoutActivityType')
                if kind == RUNNING:
                    runs.append(workout_facts(el))
                else:
                    label = kind.replace('HKWorkoutActivityType', '')
                    other[label] = other.get(label, 0) + 1
            root.clear()  # drop parsed elements: exports reach millions of records
    for run in runs:
        stream = export.open_route(run['routeFile']) if run['routeFile'] else None
        if stream:
            with stream:
                run.update(route_facts(parse_gpx(stream), trim_mi))
    runs.sort(key=lambda r: r['start'])
    distance = sum(r['distanceMi'] or 0 for r in runs)
    duration = sum(r['durationSec'] or 0 for r in runs)
    return {
        'from': first.isoformat(),
        'to': last.isoformat(),
        'runs': runs,
        'totals': {
            'runs': len(runs),
            'distanceMi': round(distance, 2),
            'durationSec': duration,
            'pace': pace(duration, distance),
            'longestMi': max((r['distanceMi'] or 0 for r in runs), default=0),
        },
        'otherWorkouts': other,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('export', help='export.zip, export.xml or the apple_health_export folder')
    parser.add_argument('--from', dest='first', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--to', dest='last', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--out', required=True, help='week folder; facts.json is written there')
    parser.add_argument('--trim-mi', type=float, default=0.2, help='route distance hidden at each end (privacy)')
    args = parser.parse_args(argv)
    facts = collect(args.export, args.first, args.last, args.trim_mi)
    os.makedirs(args.out, exist_ok=True)
    target = os.path.join(args.out, 'facts.json')
    with open(target, 'w') as f:
        json.dump(facts, f, indent=2)
        f.write('\n')
    t = facts['totals']
    print(f"{target}: {t['runs']} runs, {t['distanceMi']} mi, pace {t['pace']}/mi", file=sys.stderr)


if __name__ == '__main__':
    main()
