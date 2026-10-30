import datetime as dt
import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import health_export  # noqa: E402

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (Record*,Workout*)>
]>
<HealthData locale="en_US">
 <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" startDate="2026-10-13 07:01:00 -0400" endDate="2026-10-13 07:01:00 -0400" value="150"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="18.5" durationUnit="min" sourceName="Watch" startDate="2026-10-13 07:00:00 -0400" endDate="2026-10-13 07:18:30 -0400">
  <MetadataEntry key="HKIndoorWorkout" value="0"/>
  <MetadataEntry key="HKElevationAscended" value="1524 cm"/>
  <MetadataEntry key="HKWeatherTemperature" value="55 degF"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" startDate="2026-10-13 07:00:00 -0400" endDate="2026-10-13 07:18:30 -0400" sum="1.52" unit="mi"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="2026-10-13 07:00:00 -0400" endDate="2026-10-13 07:18:30 -0400" average="151.4" minimum="98" maximum="172" unit="count/min"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" startDate="2026-10-13 07:00:00 -0400" endDate="2026-10-13 07:18:30 -0400" sum="240.6" unit="kcal"/>
  <WorkoutRoute sourceName="Watch" startDate="2026-10-13 07:00:00 -0400" endDate="2026-10-13 07:18:30 -0400">
   <FileReference path="/workout-routes/route_2026-10-13_7.00am.gpx"/>
  </WorkoutRoute>
 </Workout>
 <Workout workoutActivityType="HKWorkoutActivityTypeWalking" duration="30" durationUnit="min" sourceName="Watch" startDate="2026-10-14 18:00:00 -0400" endDate="2026-10-14 18:30:00 -0400"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="20" durationUnit="min" sourceName="Watch" startDate="2026-10-20 07:00:00 -0400" endDate="2026-10-20 07:20:00 -0400"/>
</HealthData>
"""


def gpx(miles=1.5, seconds=1110, n=200):
    # Due north from the equator: 1 degree of latitude ~ 69.09 mi on the haversine sphere.
    lat_total = miles * health_export.MI_M / (6371008.8 * 3.141592653589793 / 180)
    start = dt.datetime(2026, 10, 13, 11, 0, 0)
    points = []
    for i in range(n + 1):
        t = start + dt.timedelta(seconds=seconds * i / n)
        points.append(f'<trkpt lon="0.0" lat="{lat_total * i / n:.7f}"><ele>{10 + (i % 2)}</ele>'
                      f'<time>{t.strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>')
    return ('<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"><trk><trkseg>'
            + ''.join(points) + '</trkseg></trk></gpx>')


class HealthExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.zip = os.path.join(self.tmp.name, 'export.zip')
        with zipfile.ZipFile(self.zip, 'w') as z:
            z.writestr('apple_health_export/export.xml', XML)
            z.writestr('apple_health_export/workout-routes/route_2026-10-13_7.00am.gpx', gpx())

    def tearDown(self):
        self.tmp.cleanup()

    def week(self, path=None):
        return health_export.collect(path or self.zip, dt.date(2026, 10, 12), dt.date(2026, 10, 18))

    def test_running_workouts_in_range_only(self):
        facts = self.week()
        self.assertEqual(len(facts['runs']), 1)
        self.assertEqual(facts['otherWorkouts'], {'Walking': 1})
        run = facts['runs'][0]
        self.assertEqual(run['date'], '2026-10-13')
        self.assertEqual(run['distanceMi'], 1.52)
        self.assertEqual(run['durationSec'], 1110)
        self.assertEqual(run['pace'], '12:10')
        self.assertEqual((run['avgHr'], run['minHr'], run['maxHr']), (151, 98, 172))
        self.assertEqual(run['activeKcal'], 241)
        self.assertEqual(run['elevationGainFt'], 50)
        self.assertFalse(run['indoor'])
        self.assertEqual(facts['totals']['runs'], 1)

    def test_splits_and_trimmed_route(self):
        run = self.week()['runs'][0]
        self.assertAlmostEqual(run['gpsDistanceMi'], 1.5, places=2)
        self.assertEqual(run['splits'][0]['mile'], 1)
        self.assertAlmostEqual(run['splits'][0]['seconds'], 740, delta=2)
        self.assertTrue(run['splits'][1]['partial'])
        self.assertAlmostEqual(run['splits'][1]['mile'], 1.5, places=2)
        route = run['routeTrimmed']
        lat_of = lambda mi: mi * health_export.MI_M / (6371008.8 * 3.141592653589793 / 180)  # noqa: E731
        self.assertGreaterEqual(route[0][0], round(lat_of(0.2), 5) - 1e-5)
        self.assertLessEqual(route[-1][0], round(lat_of(1.3), 5) + 1e-5)

    def test_unzipped_folder_and_cli(self):
        folder = os.path.join(self.tmp.name, 'unzipped')
        with zipfile.ZipFile(self.zip) as z:
            z.extractall(folder)
        export_dir = os.path.join(folder, 'apple_health_export')
        self.assertEqual(self.week(export_dir)['runs'][0]['splits'], self.week()['runs'][0]['splits'])
        out = os.path.join(self.tmp.name, 'weeks', '2026-W42')
        health_export.main([self.zip, '--from', '2026-10-12', '--to', '2026-10-18', '--out', out])
        with open(os.path.join(out, 'facts.json')) as f:
            self.assertEqual(json.load(f)['totals']['distanceMi'], 1.52)


if __name__ == '__main__':
    unittest.main()
