from skyfield.api import load, Topos
from skyfield.sgp4lib import EarthSatellite
from datetime import datetime, timezone

l1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991"
l2 = "2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000"

ts = load.timescale(builtin=True)
sat = EarthSatellite(l1, l2, "ISS (ZARYA)", ts)
observer = Topos(30.0, 114.0, elevation_m=50.0)

t0 = ts.utc(2024, 1, 16, 0, 0, 0)
t1 = ts.utc(2024, 1, 17, 0, 0, 0)

times, events = sat.find_events(observer, t0, t1, altitude_degrees=10.0)
print("skyfield find_events 事件数:", len(events))
aos = None
for ti, ev in zip(times, events):
    if ev == 0:
        aos = ti
    elif ev == 2 and aos is not None:
        los = ti
        dur = (los.utc_datetime() - aos.utc_datetime()).total_seconds()
        print("  AOS=%s  LOS=%s  dur_min=%.2f" % (
            aos.utc_datetime(), los.utc_datetime(), dur / 60.0))
        aos = None
