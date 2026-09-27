# -*- coding: utf-8 -*-
"""端到端探针：真实「卫星过境预测」窗口里，自选卫星是否以**编号**落盘、
旧版（名称）设置是否能被正确读回并在对话框里回显。

做法：把星历与设置文件都临时指向副本（跑完还原），真实源码、真实窗口：
  1. 星历副本只放 3 颗真实卫星（61781 / 27607 / 25544），避免全量解析过慢；
  2. 设置副本里写一份「旧版」sat_sats（卫星名）；
  3. 打开窗口 → 点「选择卫星…」（自动确定）→ 检查落盘的是编号；
  4. 检查对话框按编号回填勾选、按名称/编号都能搜。
全程不改动真实 file/m_xml.txt 与 file/amateur.tle。
"""
import os
import shutil
import sys
import tempfile
import time

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
os.chdir(D)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import (QApplication, QDialog, QMessageBox, QPushButton,
                               QTableWidget)

app = QApplication.instance() or QApplication(sys.argv)

import satellite_pred as sp
import satellite_window as sw

FAILS, OKS = [], [0]


def check(cond, msg):
    OKS[0] += 1
    if not cond:
        FAILS.append(msg)
        print('  [FAIL] ' + msg, flush=True)


REAL_SETTINGS = os.path.join(D, 'file', 'm_xml.txt')
REAL_TLE = os.path.join(D, 'file', 'amateur.tle')
bak = REAL_SETTINGS + '.satnum_probe_bak'
shutil.copyfile(REAL_SETTINGS, bak)

TMP = tempfile.mkdtemp(prefix='fhl_probe_')
FAKE_SETTINGS = os.path.join(TMP, 'm_xml.txt')
FAKE_TLE = os.path.join(TMP, 'amateur.tle')

# 从真实星历里摘出 3 颗星的原始 TLE（保证 SGP4 可用）
WANT = ('61781', '27607', '25544')
blocks = []
for norad_id, name, l1, l2 in sp.iter_tle_records(sp._read_text(REAL_TLE)):
    if norad_id in WANT:
        blocks.append('%s\n%s\n%s' % (name, l1, l2))
check(len(blocks) == 3, '从真实星历摘出 3 颗卫星的 TLE（实际 %d）' % len(blocks))
with open(FAKE_TLE, 'w', encoding='utf-8') as f:
    f.write('\n'.join(blocks) + '\n')

# 旧版格式：sat_sats 存卫星名；观测站设在成都附近（保证有可见过境）
LEGACY_NAMES = ['ASRTU-1 (RS64S/BJ2CR)', 'SO-50', 'ISS (ZARYA)']
with open(FAKE_SETTINGS, 'w', encoding='utf-8') as f:
    f.write(str({'m_call': 'BI8SQL', 'sat_el': 0, 'sat_dur': 24,
                 'sat_sats': LEGACY_NAMES,
                 'm_lat': 30.0, 'm_lon': 104.0, 'm_alt': 500.0}))

sp.TLE_CACHE = FAKE_TLE
sw.TLE_CACHE = FAKE_TLE
sw.SETTINGS_PATH = FAKE_SETTINGS
sp._sat_index_cache['key'] = None

_orig_info, _orig_warn = QMessageBox.information, QMessageBox.warning
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)

CAPTURED = {}
_orig_exec = sw.SatelliteSelectDialog.exec


def _patched_exec(self):
    CAPTURED['dlg'] = self
    return QDialog.Accepted


sw.SatelliteSelectDialog.exec = _patched_exec


def pump(cond, limit=400):
    """跑事件循环直到 cond() 成立或到达次数上限。"""
    for i in range(limit):
        app.processEvents()
        time.sleep(0.01)
        if cond():
            return i
    return -1


def wait_worker(win, limit=1500):
    """等后台预测线程出现并跑完（出现前不等，避免误判「已结束」）。"""
    for _ in range(limit):
        app.processEvents()
        time.sleep(0.01)
        w = getattr(win, '_worker', None)
        if w is not None and not w.isRunning():
            return True
    return False


try:
    sw.main(None)
    win = sw._open_windows[-1]

    pump(lambda: getattr(win, '_tle_worker', None) is None, 800)
    print('1) 旧版（名称）sat_sats 能否读回', flush=True)
    wait_worker(win)
    pump(lambda: False, 100)     # 多跑一会事件循环，确保 done 回调已执行
    tables = win.findChildren(QTableWidget)
    check(len(tables) == 1, '窗口内有且仅有一个结果表：%d 个' % len(tables))
    n_rows = tables[0].rowCount() if tables else 0
    check(n_rows > 0, '旧版名称设置被识别 → 预测表有 %d 行' % n_rows)

    btn = None
    for b in win.findChildren(QPushButton):
        if b.text() == '选择卫星…':
            btn = b
            break
    check(btn is not None, '找到「选择卫星…」按钮')
    btn.click()
    app.processEvents()
    dlg = CAPTURED.get('dlg')
    check(dlg is not None, '选择对话框已打开')
    if dlg is not None:
        checked = sorted(n for n in dlg._row_names
                         if dlg.items[n].checkState().name == 'Checked')
        # 对话框的行来自「当前星历」，所以旧短名 SO-50 会显示成
        # 星历里的全名 SAUDISAT-1C (SO-50)
        expect = sorted(sp.sat_display_name(n) for n in LEGACY_NAMES)
        check(checked == expect,
              '旧版名称设置被正确回填勾选：%r（期望 %r）' % (checked, expect))
        check(dlg.get_selected() == {'61781', '27607', '25544'},
              '对话框返回的是编号：%r' % (sorted(dlg.get_selected()),))

    print('2) 落盘是否为编号', flush=True)
    wait_worker(win)
    saved = eval(open(FAKE_SETTINGS, encoding='utf-8').read())
    check(sorted(saved.get('sat_sats', [])) == ['25544', '27607', '61781'],
          'sat_sats 已按编号落盘：%r' % (saved.get('sat_sats'),))
    check(saved.get('m_call') == 'BI8SQL' and saved.get('m_lat') == 30.0,
          '其它设置项原样保留')

    print('3) 编号 ⇄ 当前星历名称', flush=True)
    names_new = sorted(sp.sat_display_name(n) for n in ('61781', '27607', '25544'))
    check(names_new == sorted(['ASRTU-1 (RS64S/BJ2CR)', 'SAUDISAT-1C (SO-50)',
                               'ISS (ZARYA)']),
          '编号能还原成当前星历里的名称：%r' % (names_new,))
    check(sp.normalize_sat_keys(['ASRTU-1 (RS64S/BJ2CR)', '61781']) == ['61781'],
          '同一颗星的两种写法去重成一个编号')
    check(sp.normalize_sat_keys(['SO-50']) == ['27607'],
          '旧版短名 SO-50 也能升级成编号')

    win.close()
finally:
    sw.SatelliteSelectDialog.exec = _orig_exec
    QMessageBox.information = _orig_info
    QMessageBox.warning = _orig_warn
    shutil.copyfile(bak, REAL_SETTINGS)
    os.remove(bak)
    sp._sat_index_cache['key'] = None
    shutil.rmtree(TMP, ignore_errors=True)
    print('设置已还原', flush=True)

print('---')
print('通过 %d 项，失败 %d 项' % (OKS[0], len(FAILS)))
print('RESULT:', 'ALL_OK' if not FAILS else 'FAIL')
sys.exit(1 if FAILS else 0)
