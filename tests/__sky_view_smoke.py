# -*- coding: utf-8 -*-
"""过境视图（极坐标天空图）冒烟测试。

覆盖：
  1. satellite_pred.sky_track 的采样数量 / 数值范围 / 首尾落在地平线附近；
  2. satellite_pred.sun_altaz 的合理性（正午高、午夜低）；
  3. 单站 SkyWindow：构造、渲染出图（非空白）、读数 / 状态文字、滑块与「实时」；
  4. 双站 SkyWindow：两个天空图、各自独立的距离读数；
  5. 深色调色板下重绘、语言切换到英文后标题/状态重译。

运行：QT_QPA_PLATFORM=offscreen python tests/__sky_view_smoke.py
"""

import datetime
import os
import sys
import traceback

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from f_hamlog import i18n, satellite_pred as sp
from f_hamlog import satellite_sky_window as sk
from f_hamlog import theme

TLE = """ISS (ZARYA)
1 25544U 98067A   26101.50000000  .00016717  00000-0  10270-3 0  9991
2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000
"""

OBS_A = (30.0, 114.0, 50.0)     # 武汉
OBS_B = (39.9, 116.4, 50.0)     # 北京

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('[PASS] ' if ok else '[FAIL] ') + name + ('  ' + detail if detail else ''))


def non_bg_pixels(pixmap, bg):
    """统计与背景色不同的像素数，用来确认画布真的画了东西。"""
    img = pixmap.toImage()
    n = 0
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            c = img.pixelColor(x, y)
            if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + \
                    abs(c.blue() - bg.blue()) > 12:
                n += 1
    return n


def main():
    app = QApplication([])
    i18n.install(app)

    sats = sp.parse_tle_text(TLE)
    check('解析 TLE', len(sats) == 1, 'sats=%d' % len(sats))
    name, sat = sats[0]

    start = datetime.datetime(2026, 10, 18, 0, 0, tzinfo=datetime.timezone.utc)
    passes = sp.predict_passes(sat, OBS_A, start, duration_hours=24,
                               min_elevation_deg=0.0, step_sec=60)
    check('24h 内有可见过境', len(passes) > 0, 'passes=%d' % len(passes))
    p = passes[0]
    aos, los = p['aos'], p['los']

    # ---- 1. sky_track ----
    track = sp.sky_track(sat, OBS_A, aos, los, samples=240)
    check('sky_track 采样数量', len(track) == 240, 'len=%d' % len(track))
    els = [t['elevation'] for t in track]
    azs = [t['azimuth'] for t in track]
    alts = [t['alt_km'] for t in track]
    rngs = [t['range_km'] for t in track]
    check('轨迹首尾贴地平线', abs(els[0]) < 1.5 and abs(els[-1]) < 1.5,
          'el0=%.2f el-1=%.2f' % (els[0], els[-1]))
    check('仰角不超过 90°', max(els) <= 90.5 and max(els) > 1.0,
          'max=%.2f' % max(els))
    check('方位角在 [0,360)', min(azs) >= -0.01 and max(azs) < 360.01,
          'az %.1f~%.1f' % (min(azs), max(azs)))
    check('高度合理（近地轨道）', 350.0 < min(alts) and max(alts) < 600.0,
          'alt %.0f~%.0f' % (min(alts), max(alts)))
    check('斜距合理（>= 高度）', min(rngs) > min(alts) - 50,
          'range %.0f~%.0f' % (min(rngs), max(rngs)))
    check('采样时间单调', all(track[i]['jd'] < track[i + 1]['jd']
                              for i in range(len(track) - 1)))

    # ---- 2. sun_altaz ----
    noon = datetime.datetime(2026, 10, 18, 4, 0, tzinfo=datetime.timezone.utc)
    night = datetime.datetime(2026, 10, 18, 16, 0, tzinfo=datetime.timezone.utc)
    az_n, el_n = sp.sun_altaz(OBS_A[0], OBS_A[1], noon)
    az_m, el_m = sp.sun_altaz(OBS_A[0], OBS_A[1], night)
    check('正午太阳在地平线上', el_n > 30.0, 'el=%.1f az=%.1f' % (el_n, az_n))
    check('午夜太阳在地平线下', el_m < 0.0, 'el=%.1f az=%.1f' % (el_m, az_m))
    check('正午太阳大致偏南', 120.0 < az_n < 240.0, 'az=%.1f' % az_n)

    # ---- 2b. moon_ecliptic / moon_altaz ----
    # Meeus《天文算法》例 47.a：JD 2448724.5（1992-04-12 0h TD）
    lam_m, beta_m = sp.moon_ecliptic(2448724.5)
    check('月亮黄经对 Meeus 47.a', abs(lam_m - 133.162655) < 0.05,
          '%.4f vs 133.162655' % lam_m)
    check('月亮黄纬对 Meeus 47.a', abs(beta_m - (-3.229126)) < 0.05,
          '%.4f vs -3.229126' % beta_m)

    maz_n, mel_n = sp.moon_altaz(OBS_A[0], OBS_A[1], noon)
    check('月亮仰角在 [-90, 90]', -90.0 <= mel_n <= 90.0, 'el=%.1f' % mel_n)
    check('月亮方位在 [0, 360)', 0.0 <= maz_n < 360.0, 'az=%.1f' % maz_n)

    # 24 小时里月亮方位应基本绕天一圈（周日视运动），仰角不超过 90°
    samples = [sp.moon_altaz(OBS_A[0], OBS_A[1],
                             start + datetime.timedelta(minutes=30 * i))
               for i in range(48)]
    ms = sorted(a for a, _e in samples)
    gaps = [(ms[(i + 1) % len(ms)] - ms[i]) % 360.0 for i in range(len(ms))]
    check('24h 内月亮绕天一圈', max(gaps) < 60.0,
          'max gap=%.1f°' % max(gaps))
    check('月亮仰角范围合理', max(e for _a, e in samples) <= 90.0 and
          min(e for _a, e in samples) >= -90.0,
          'el %.1f~%.1f' % (min(e for _a, e in samples),
                            max(e for _a, e in samples)))

    # ---- 3. 单站窗口 ----
    w1 = sk.SkyWindow(None, name, sat, [('本站', OBS_A)], aos, los,
                      info='最大仰角 %.1f°' % p['max_elevation'])
    w1.resize(520, 620)
    w1.show()
    app.processEvents()
    check('单站窗口只有一张天空图', len(w1._plots) == 1)
    pm = w1.grab()
    bg = w1._plots[0]._c['bg']          # 卡片底色 = 系统 Base（旧版是窗口底色）
    npx = non_bg_pixels(pm, bg)
    check('单站窗口绘出了内容', npx > 500, 'non-bg=%d' % npx)
    check('时间标签格式', len(w1._time_lbl.text()) == 19,
          w1._time_lbl.text())
    check('状态文字非空', w1._state_lbl.text() in ('未开始', '进行中', '已结束'),
          w1._state_lbl.text())
    check('标题含卫星名', name in w1.windowTitle(), w1.windowTitle())

    # 读数面板：四项都填上了数值（不是占位符「—」）
    rows = w1._readouts[0]
    vals = [rows[k].text() for k in ('方位角', '仰角', '距离', '高度')]
    check('读数面板四项都有数值', all(v and v != '—' for v in vals),
          ' '.join(vals))
    check('读数面板在图右侧',
          w1._panel.width() == sk.PANEL_W and
          w1._panel.x() > w1._plots[0].x() + w1._plots[0].width() - 1,
          'panel x=%d plot x=%d' % (w1._panel.x(), w1._plots[0].x()))
    check('面板标题是「过境数据」',
          '过境数据' in [lbl.text() for lbl, _src in w1._texts],
          ' '.join(lbl.text() for lbl, _src in w1._texts)[:40])
    # 素色：不铺渐变、不打光晕、不描边卡片、不做圆角
    check('天空图没有渐变 / 卡片底色',
          'sky' not in w1._plots[0]._c and
          'card_edge' not in w1._plots[0]._c,
          ' / '.join(sorted(w1._plots[0]._c)))
    check('面板与状态无圆角、无底色',
          'border-radius' not in w1._panel.styleSheet() and
          'border-radius' not in w1._state_lbl.styleSheet(),
          w1._state_lbl.styleSheet())

    # 滑块：拖动即退出实时
    w1._slider.setValue(600)
    app.processEvents()
    check('拖动滑块退出实时', w1._follow is False and not w1._live_btn.isChecked())
    check('进度条跟随滑块', abs(w1._meter._value - 0.6) < 0.02,
          'meter=%.3f' % w1._meter._value)
    check('进度文案含百分比', '60%' in w1._prog_lbl.text(), w1._prog_lbl.text())
    t1 = w1._time_lbl.text()
    w1._slider.setValue(200)
    app.processEvents()
    check('滑块换时刻后时间跟随', w1._time_lbl.text() != t1,
          '%s -> %s' % (t1, w1._time_lbl.text()))

    # 「实时」恢复
    w1._live_btn.setChecked(True)
    app.processEvents()
    check('恢复实时后跟随', w1._follow is True)

    # 手动时刻的读数应已填入
    plot = w1._plots[0]
    check('天空图有当前读数', plot.now is not None and
          -1.0 <= plot.now['elevation'] <= 90.0,
          'el=%.1f' % (plot.now['elevation'] if plot.now else -999))
    check('天空图有太阳位置', plot.sun is not None,
          'sun=%s' % (plot.sun,))
    check('天空图有月亮位置', plot.moon is not None and
          -90.0 <= plot.moon[1] <= 90.0,
          'moon=%s' % (plot.moon,))
    check('图例列出月亮', '月亮' in sk._Legend.KEYS and
          sk._Legend.ROWS == len(sk._Legend.KEYS),
          ' / '.join(sk._Legend.KEYS))

    # 深色调色板重绘（不写盘，只改控件调色板）
    light_bg = plot._c['bg'].name()
    plot.setPalette(theme.dark_palette())
    plot.apply_theme()
    app.processEvents()
    check('深色下底色跟随系统调色板', plot._c['bg'].name() != light_bg,
          '%s -> %s' % (light_bg, plot._c['bg'].name()))
    pm_dark = w1.grab()
    check('深色下仍绘出内容', non_bg_pixels(pm_dark, plot._c['bg']) > 500)
    plot.setPalette(theme.light_palette())
    plot.apply_theme()
    app.processEvents()

    # ---- 3b. 观测站坐标 0° 也能画（赤道 / 本初子午线是合法位置）----
    w0 = sk.SkyWindow(None, name, sat, [('本站', (0.0, 0.0, 0.0))], aos, los)
    w0.resize(760, 520)
    w0.show()
    app.processEvents()
    ok0 = w0._plots[0].now is not None and w0._plots[0].track
    check('经纬度 0° 的站也能绘制', ok0,
          'el=%.1f pts=%d' % (w0._plots[0].now['elevation'] if ok0 else -999,
                              len(w0._plots[0].track)))
    check('0° 站仍绘出内容',
          non_bg_pixels(w0.grab(), w0._plots[0]._c['bg']) > 400)
    w0.close()

    # ---- 4. 双站窗口 ----
    w2 = sk.SkyWindow(None, name, sat,
                      [('台站 A（本站）', OBS_A), ('台站 B（对方）', OBS_B)],
                      aos, los, info='A 最大仰角 %.1f° ｜ B 最大仰角 %.1f°'
                                     % (p['max_elevation'], p['max_elevation']))
    w2.resize(940, 560)
    w2.show()
    app.processEvents()
    check('双站窗口有两张天空图', len(w2._plots) == 2)
    pa, pb = w2._plots[0].now, w2._plots[1].now
    check('两站斜距不同（各自独立计算）',
          pa is not None and pb is not None and
          abs(pa['range_km'] - pb['range_km']) > 1.0,
          'A=%.0f km B=%.0f km' % (pa['range_km'], pb['range_km']))
    pm2 = w2.grab()
    check('双站窗口绘出了内容',
          non_bg_pixels(pm2, w2._plots[0]._c['bg']) > 800)
    check('双站读数面板两站各一组', len(w2._readouts) == 2 and
          w2._readouts[1]['距离'].text() != w2._readouts[0]['距离'].text(),
          '%s vs %s' % (w2._readouts[0]['距离'].text(),
                        w2._readouts[1]['距离'].text()))

    # ---- 5. 语言切换 ----
    i18n.set_language('en')   # 只切内存语言，不落盘（避免改用户设置）
    app.processEvents()
    check('英文下标题重译', 'Pass view' in w1.windowTitle(), w1.windowTitle())
    check('英文下状态重译',
          w1._state_lbl.text() in ('Not started', 'In progress', 'Finished'),
          w1._state_lbl.text())
    pm_en = w1.grab()
    check('英文下仍绘出内容',
          non_bg_pixels(pm_en, w1._plots[0]._c['bg']) > 500)
    check('英文下读数面板重译',
          'Azimuth' in [lbl.text() for lbl, _src in w1._texts],
          ' '.join(lbl.text() for lbl, _src in w1._texts)[:60])

    i18n.set_language('zh')
    app.processEvents()
    check('切回中文标题', '过境视图' in w1.windowTitle(), w1.windowTitle())

    w1.close()
    w2.close()
    app.processEvents()
    check('关闭后从 _OPEN 移除', w1 not in sk._OPEN and w2 not in sk._OPEN)

    failed = [r for r in results if not r[1]]
    print('\n=== %d / %d PASS ===' % (len(results) - len(failed), len(results)))
    return 0 if not failed else 1


if __name__ == '__main__':
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    print('EXIT', code)
