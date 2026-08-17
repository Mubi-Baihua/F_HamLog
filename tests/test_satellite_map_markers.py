import datetime

import satellite_map_window as smw


def test_marker_roundtrip_load_save():
    data = [
        {'name': '北京', 'lat': 39.9, 'lon': 116.4, 'color': '#ff6600'},
        {'name': '东京', 'lat': 35.7, 'lon': 139.7, 'color': '#00aa88'},
    ]
    smw.save_map_markers(data)
    loaded = smw.load_map_markers()
    assert loaded == data


def test_twilight_points_are_generated_for_now():
    now = datetime.datetime.now(datetime.timezone.utc)
    pts = smw.compute_twilight_points(now)
    assert len(pts) >= 2
    assert all(len(p) == 2 for p in pts)
