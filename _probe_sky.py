# -*- coding: utf-8 -*-
import datetime
from skyfield.api import load, wgs84, EarthSatellite

ts = load.timescale(builtin=True)
print("timescale ok, leap_seconds:", ts.leap_dates.shape)

l1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991"
l2 = "2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000"
es = EarthSatellite(l1, l2, "ISS (ZARYA)")
print("satnum:", es.model.satnum, "name:", es.name)

topos = wgs84.latlon(30.0, 114.0, 50.0)  # 武汉
t0 = ts.utc(2024, 1, 16, 0, 0, 0)
t1 = ts.utc(2024, 1, 17, 0, 0, 0)
times, events = es.find_events(topos, t0, t1, altitude_degrees=10.0)
print("num events:", len(events))

diff = es - topos
count = 0
for i in range(0, len(events) - 2, 3):
    if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
        aos, mx, los = times[i], times[i + 1], times[i + 2]
        alt, az, d = diff.at(aos).altaz()
        alt2, az2, d2 = diff.at(los).altaz()
        altm, azm, d3 = diff.at(mx).altaz()
        dur = float(los - aos) * 86400.0
        print("AOS", aos.utc_datetime(), "LOS", los.utc_datetime(),
              "dur_min", round(dur / 60.0, 2),
              "maxel", round(altm.degrees, 1),
              "azA", round(az.degrees, 1), "azL", round(az2.degrees, 1))
        count += 1
print("complete passes:", count)
