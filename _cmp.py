import satellite_pred as sp
from skyfield.api import load, Topos
from skyfield.sgp4lib import EarthSatellite
from datetime import datetime, timezone

l1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991"
l2 = "2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000"

sat = sp.twoline2rv(l1, l2, name="ISS (ZARYA)")
observer = (30.0, 114.0, 50.0)
ts = load.timescale(builtin=True)
sf_sat = EarthSatellite(l1, l2, "ISS", ts)
sf_obs = Topos(30.0, 114.0, elevation_m=50.0)

for hh, mm, ss in [(0, 30, 0), (0, 33, 0), (0, 36, 52), (0, 45, 0), (1, 0, 0), (2, 0, 0)]:
    dt = datetime(2024, 1, 16, hh, mm, ss, tzinfo=timezone.utc)
    jd = sp.datetime_to_jd(dt)
    o = sp.observe(sat, jd, observer)
    t = ts.utc(dt)
    alt = (sf_sat - sf_obs).at(t).altaz()[0]
    print("t=%02d:%02d:%02d  mine el=%.2f az=%.1f dist=%.0f | sky el=%.2f" % (
        hh, mm, ss, o['elevation'], o['azimuth'], o['range_km'], alt.degrees))
