from sgp4.api import Satrec, jday

l1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9991"
l2 = "2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000"
sat = Satrec.twoline2rv(l1, l2)
print("satnum", sat.satnum)
print("jdsatepoch", sat.jdsatepoch)
print("has sgp4", hasattr(sat, "sgp4"))
try:
    sat.name = "ISS (ZARYA)"
    print("set name OK ->", sat.name)
except Exception as e:
    print("set name FAIL ->", repr(e))
jd, fr = jday(2024, 1, 16, 0, 0, 0)
err, r, v = sat.sgp4(jd, fr)
print("err", err, "r km", [round(x, 1) for x in r])
jd2, fr2 = jday(2024, 1, 16, 1, 0, 0)
e2, r2, v2 = sat.sgp4(jd2, fr2)
print("err2", e2, "r2 km", [round(x, 1) for x in r2])
