import datetime
import os
import tempfile

import satellite_map_window as smw
import satellite_pred as sp


def test_tle_source_contains_all_active_satellites():
    assert 'GROUP=active' in sp.CELESTRAK_ALL_URL
    assert 'GROUP=amateur' not in sp.CELESTRAK_ALL_URL


def test_default_tle_sources_is_ordered_and_nonempty():
    assert isinstance(sp.DEFAULT_TLE_SOURCES, tuple)
    assert sp.DEFAULT_TLE_SOURCES[0] == sp.CELESTRAK_ACTIVE_URL
    assert sp.normalize_tle_sources(None) == list(sp.DEFAULT_TLE_SOURCES)
    assert sp.normalize_tle_sources([]) == list(sp.DEFAULT_TLE_SOURCES)


def test_marker_roundtrip_load_save():
    data = [
        {'name': '北京', 'lat': 39.9, 'lon': 116.4, 'color': '#ff6600'},
        {'name': '东京', 'lat': 35.7, 'lon': 139.7, 'color': '#00aa88'},
    ]
    # 关键：改写到临时文件，绝不碰用户真实数据 file/sat_map_markers.txt
    real_path = smw.MARKERS_PATH
    tmpdir = tempfile.mkdtemp(prefix='fhl_markers_')
    try:
        smw.MARKERS_PATH = os.path.join(tmpdir, 'sat_map_markers.txt')
        smw.save_map_markers(data)
        loaded = smw.load_map_markers()
    finally:
        smw.MARKERS_PATH = real_path
    assert loaded == data


def test_twilight_points_are_generated_for_now():
    now = datetime.datetime.now(datetime.timezone.utc)
    pts = smw.compute_twilight_points(now)
    assert len(pts) >= 2
    assert all(len(p) == 2 for p in pts)
