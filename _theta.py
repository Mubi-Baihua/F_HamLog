import math
import satellite_pred as sp
from skyfield.api import load, Topos
from skyfield.sgp4lib import EarthSatellite
from datetime import datetime, timezone

l1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991"
l2 = "2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000"

sat = sp.twoline2rv(l1, l2, name="ISS")
ts = load.timescale(builtin=True)
sf = EarthSatellite(l1, l2, "ISS", ts)
sf_obs = Topos(30.0, 114.0, elevation_m=50.0)
lat, lon, alt = 30.0, 114.0, 50.0


def sez_el(ox, oy, oz):
    obs = sp._geodetic_to_ecef(lat, lon, alt)
    rho = (ox - obs[0], oy - obs[1], oz - obs[2])
    latr = lat * math.pi / 180.0
    lonr = lon * math.pi / 180.0
    slat, clat = math.sin(latr), math.cos(latr)
    slon, clon = math.sin(lonr), math.cos(lonr)
    rs = -clat * slon * rho[0] - clat * clon * rho[1] + slat * rho[2]
    re = -slon * rho[0] + clon * rho[1]
    rz = slat * slon * rho[0] + slat * clon * rho[1] + clat * rho[2]
    rng = math.sqrt(rs * rs + re * re + rz * rz)
    return math.degrees(math.asin(rz / rng)) if rng > 0 else -90.0


for hh, mm in [(0, 30), (0, 33), (0, 36, 52), (0, 45)]:
    dt = datetime(2024, 1, 16, hh, mm, 0, tzinfo=timezone.utc)
    jd = sp.datetime_to_jd(dt)
    r, v = sp.propagate(sat, jd)
    rx, ry, rz = r

    # 我的 gstime
    my_theta = sp.gstime(jd)
    cT, sT = math.cos(my_theta), math.sin(my_theta)
    ox1 = cT * rx - sT * ry
    oy1 = sT * rx + cT * ry
    el_mine = sez_el(ox1, oy1, rz)

    # skyfield 的 gmst（若可用）
    t = ts.utc(dt)
    sky_theta = getattr(t, 'gmst', None)
    if sky_theta is not None:
        cT2, sT2 = math.cos(sky_theta), math.sin(sky_theta)
        ox2 = cT2 * rx - sT2 * ry
        oy2 = sT2 * rx + cT2 * ry
        el_skytheta = sez_el(ox2, oy2, rz)
    else:
        el_skytheta = None

    sky_el = (sf - sf_obs).at(t).altaz()[0].degrees
    print("t=%02d:%02d  my_gstime el=%.1f | sky_gmst el=%s | skyfield el=%.1f | gstime diff(deg)=%s" % (
        hh, mm, el_mine,
        ("%.1f" % el_skytheta) if el_skytheta is not None else "n/a",
        sky_el,
        ("%.3f" % ((my_theta - sky_theta) * 180 / math.pi)) if sky_theta is not None else "n/a"))
