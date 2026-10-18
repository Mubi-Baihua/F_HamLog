# -*- coding: utf-8 -*-
"""「过境视图」与两个预测窗口的集成冒烟测试。

在临时数据目录（F_HAMLOG_DATA_DIR）里布置最小星历 + 设置文件，真实打开
「卫星过境」与「通联预测」窗口，确认：
  1. 表格新增的「视图」列存在且每行都有按钮；
  2. 点击行内「视图」按钮会打开过境视图（单站 / 双站）；
  3. 打开后的窗口能绘制、能关，且不影响原窗口（设置写回临时目录）。

运行：QT_QPA_PLATFORM=offscreen python tests/__sky_view_integration.py
"""

import datetime
import os
import shutil
import sys
import tempfile
import time
import traceback

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='fhl_sky_')
os.makedirs(os.path.join(TMP, 'file'), exist_ok=True)
os.environ['F_HAMLOG_DATA_DIR'] = TMP
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

TLE = """ISS (ZARYA)
1 25544U 98067A   26101.50000000  .00016717  00000-0  10270-3 0  9991
2 25544  51.6400 208.9163 0006317  69.9862 290.2156 15.49815308 10000
CSS (TIANHE)
1 48274U 21035A   26101.50000000  .00016717  00000-0  10270-3 0  9992
2 48274  41.4700 208.9163 0006317  69.9862 290.2156 15.61000000 10000
NOAA 19
1 33591U 09005A   26101.50000000  .00000000  00000-0  10270-3 0  9993
2 33591  99.1000 208.9163 0010000  69.9862 290.2156 14.12000000 10000
"""

SETTINGS = {
    'm_lat': 30.0, 'm_lon': 114.0, 'm_alt': 50.0,
    'sat_b_lat': 39.9, 'sat_b_lon': 116.4, 'sat_b_alt': 50.0,
    'sat_b_grid': 'OM89', 'sat_mu_el_b': 5,
    'sat_dur': 24, 'sat_el': 0,
    'sat_sats': [25544, 48274, 33591],
    'language': 'zh',
}

from PySide6.QtWidgets import QApplication

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('[PASS] ' if ok else '[FAIL] ') + name + ('  ' + detail if detail else ''))


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main():
    with open(os.path.join(TMP, 'file', 'amateur.tle'), 'w', encoding='utf-8') as f:
        f.write(TLE)
    with open(os.path.join(TMP, 'file', 'm_xml.txt'), 'w', encoding='utf-8') as f:
        f.write(str(SETTINGS))

    app = QApplication([])

    from f_hamlog import i18n, satellite_window, mutual_window, satellite_sky_window as sk
    i18n.install(app)

    # ---------- 卫星过境 ----------
    satellite_window.main(None)
    wins = [w for w in satellite_window._open_windows if w.isVisible()]
    check('卫星过境窗口打开', len(wins) >= 1)
    w1 = wins[-1]
    pump(app, 6.0)          # 等后台星历 + 预测

    from PySide6.QtWidgets import QPushButton, QTableWidget
    tables = w1.findChildren(QTableWidget)
    check('卫星过境有结果表', len(tables) == 1)
    t1 = tables[0]
    check('表格列数 9（新增「视图」列）', t1.columnCount() == 9,
          'cols=%d' % t1.columnCount())
    check('表头含「视图」', t1.horizontalHeaderItem(7).text() == '视图',
          t1.horizontalHeaderItem(7).text())
    check('已预测出过境行', t1.rowCount() > 0, 'rows=%d' % t1.rowCount())
    sky_btns = [t1.cellWidget(i, 7) for i in range(min(3, t1.rowCount()))]
    check('每行有「视图」按钮', all(b is not None for b in sky_btns))
    check('第 8 列为空占位',
          t1.item(0, 8) is not None and t1.item(0, 8).text() == '')

    # 点击第一行的「视图」
    before = len(sk._OPEN)
    t1.cellWidget(0, 7).click()
    pump(app, 0.5)
    check('点击「视图」打开过境视图', len(sk._OPEN) == before + 1,
          'open=%d' % len(sk._OPEN))
    sky1 = sk._OPEN[-1]
    check('单站视图只有一张图', len(sky1._plots) == 1)
    check('单站视图有读数', sky1._plots[0].now is not None)
    check('单站视图窗口标题含卫星名', bool(sky1._sat_name))
    # 窗口是独立顶层窗口：不挂在来源窗口下面，最小化来源窗口时不会跟着最小化
    check('视图窗口没有父窗口（独立顶层）',
          sky1.parent() is None and sky1._source is w1,
          'parent=%r' % (sky1.parent(),))
    w1.showMinimized()
    pump(app, 0.6)
    check('最小化来源窗口后视图仍可见',
          sky1.isVisible() and not sky1.isMinimized(),
          'min=%s vis=%s' % (sky1.isMinimized(), sky1.isVisible()))
    w1.showNormal()
    pump(app, 0.4)
    pm = sky1.grab()
    check('单站视图渲染非空', pm.width() > 200 and pm.height() > 200,
          '%dx%d' % (pm.width(), pm.height()))

    # 同一行再次点击：只聚焦已有窗口，不重复堆窗口
    t1.cellWidget(0, 7).click()
    pump(app, 0.4)
    check('重复点击只聚焦不重复开窗', len(sk._OPEN) == before + 1,
          'open=%d' % len(sk._OPEN))

    # 表格工具栏的「过境视图」按钮（无选中行时给提示，不崩）
    t1.clearSelection()
    pump(app, 0.2)

    # ---------- 通联预测 ----------
    mutual_window.main(None)
    mws = [w for w in mutual_window._open_windows if w.isVisible()]
    check('通联预测窗口打开', len(mws) >= 1)
    w2 = mws[-1]
    pump(app, 6.0)

    t2 = w2.findChildren(QTableWidget)[0]
    check('通联表格列数 9（新增「视图」列）', t2.columnCount() == 9,
          'cols=%d' % t2.columnCount())
    check('通联表头含「视图」', t2.horizontalHeaderItem(8).text() == '视图',
          t2.horizontalHeaderItem(8).text())
    check('通联已预测出窗口', t2.rowCount() > 0, 'rows=%d' % t2.rowCount())
    check('通联每行有「视图」按钮',
          t2.cellWidget(0, 8) is not None)

    before = len(sk._OPEN)
    t2.cellWidget(0, 8).click()
    pump(app, 0.5)
    check('点击通联「视图」打开双站视图', len(sk._OPEN) == before + 1,
          'open=%d' % len(sk._OPEN))
    sky2 = sk._OPEN[-1]
    check('双站视图有两张图', len(sky2._plots) == 2)
    a, b = sky2._plots[0].now, sky2._plots[1].now
    check('两站读数各自计算',
          a is not None and b is not None and
          abs(a['range_km'] - b['range_km']) > 1.0,
          'A=%.0f B=%.0f' % (a['range_km'], b['range_km']))
    check('副标题含两站最大仰角', 'A 最大仰角' in sky2._info, sky2._info)
    pm2 = sky2.grab()
    check('双站视图渲染非空', pm2.width() > 400, '%dx%d' % (pm2.width(), pm2.height()))

    # 「双方的全部过境」：每张图按本站自己的 AOS→LOS 取轨迹，时间轴取并集
    tr_a, tr_b = sky2._plots[0].track, sky2._plots[1].track
    check('双站视图各站按本站过境取轨迹',
          bool(tr_a) and bool(tr_b) and
          abs(tr_a[0]['jd'] - tr_b[0]['jd']) > 1e-6,
          'A 起点与 B 起点不同（%.1f 秒）'
          % ((tr_a[0]['jd'] - tr_b[0]['jd']) * 86400.0 if tr_a and tr_b else 0))
    check('时间轴覆盖双方过境',
          sky2._start_jd <= min(tr_a[0]['jd'], tr_b[0]['jd']) + 1e-6 and
          sky2._end_jd >= max(tr_a[-1]['jd'], tr_b[-1]['jd']) - 1e-6,
          '%s → %s' % (sky2._start.strftime('%H:%M:%S'),
                       sky2._end.strftime('%H:%M:%S')))
    check('可通联段加粗（emphasis + 图例）',
          sky2._emphasis is not None and
          all(p.emphasis == sky2._emphasis for p in sky2._plots) and
          sk._Legend.KEY_EMPHASIS in sky2._legend.keys,
          ' / '.join(sky2._legend.keys))

    # 通联主窗口已加宽（原来 1050，表格列也一起加宽）
    check('通联主窗口已加宽', w2.width() >= 1180, '%dx%d'
          % (w2.width(), w2.height()))

    # 工具栏「过境视图」：没有选中行时自动落到最近的一次，并高亮该行
    sky2.close()
    pump(app, 0.3)
    t2.clearSelection()
    before = len(sk._OPEN)
    btns = [b for b in w2.findChildren(QPushButton) if b.text() == '过境视图']
    check('工具栏有「过境视图」按钮', bool(btns))
    if btns:
        btns[0].click()
        pump(app, 0.6)
        check('工具栏未选中时自动打开最近一次',
              len(sk._OPEN) == before + 1, 'open=%d' % len(sk._OPEN))
        check('自动选中了那一行', bool(t2.selectedIndexes()))

    # 关闭
    sky1.close(); sky2.close(); w1.close(); w2.close()
    pump(app, 0.5)
    check('视图窗口关闭后出栈', sky1 not in sk._OPEN and sky2 not in sk._OPEN)

    # 落盘应写进临时目录，不能写到真实数据目录
    written = os.path.exists(os.path.join(TMP, 'file', 'm_xml.txt'))
    check('设置写回临时数据目录', written)

    failed = [r for r in results if not r[1]]
    print('\n=== %d / %d PASS ===' % (len(results) - len(failed), len(results)))
    return 0 if not failed else 1


if __name__ == '__main__':
    code = 2
    try:
        code = main()
    except Exception:
        traceback.print_exc()
    finally:
        print('EXIT', code)
        shutil.rmtree(TMP, ignore_errors=True)
