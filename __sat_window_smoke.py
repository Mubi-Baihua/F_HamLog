# -*- coding: utf-8 -*-
"""卫星过境窗口「导入星历」端到端 offscreen 烟测。

真实构建 satellite_window.main() 并点击「导入星历数据」按钮，验证：
  1. 导入按 NORAD 编号增量更新：同编号替换、新编号追加、其余保留；
  2. 导入**不自动勾选**卫星（不再出现「仅默认选择前 N 颗」）；
  3. 导入结果写回星历缓存 file/amateur.tle。

会临时改写 file/m_xml.txt 与 file/amateur.tle，**先备份字节、结束时还原**。
"""

import os
import shutil
import sys
import tempfile
import time

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QDialog, QMessageBox, QPushButton, QFileDialog)

import satellite_pred as sp  # noqa: E402
import satellite_window as sw  # noqa: E402

RESULT = []


def ok(name, cond, extra=''):
    RESULT.append(('PASS' if cond else 'FAIL', name, extra))
    print(('PASS' if cond else 'FAIL'), '-', name, extra)


def by_key(text):
    """解析 TLE 文本 → {NORAD key: (name, Satrec)}。"""
    out = {}
    for name, sat in sp.parse_tle_text(text):
        out.setdefault(sp.sat_key(sat, name), (name, sat))
    return out


TLE_CACHE = os.path.join(PROJECT_DIR, 'file', 'amateur.tle')
SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
backups = []
for path in (TLE_CACHE, SETTINGS):
    if os.path.exists(path):
        bak = path + '.satw_bak'
        shutil.copyfile(path, bak)
        backups.append((path, bak))

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

info_msgs = []
_real_info = QMessageBox.information
_real_warn = QMessageBox.warning
_real_getfile = QFileDialog.getOpenFileName
_real_obs = sw.ObserverDialog.exec
_real_sel = sw.SatelliteSelectDialog.exec
QMessageBox.information = staticmethod(
    lambda parent, title, text, *a, **k: info_msgs.append((title, text)))
QMessageBox.warning = staticmethod(
    lambda parent, title, text, *a, **k: info_msgs.append((title, text)))
# 模态对话框：不真正 exec，直接当作取消
sw.ObserverDialog.exec = lambda self: QDialog.Rejected
sw.SatelliteSelectDialog.exec = lambda self: QDialog.Rejected

try:
    sw.main(None)
    win = sw._open_windows[-1]
    for _ in range(300):
        app.processEvents()
        time.sleep(0.01)
        if getattr(win, '_tle_worker', None) is None:
            break
    app.processEvents()

    buttons = {b.text(): b for b in win.findChildren(QPushButton)}
    ok('窗口构建成功且含「导入星历数据」按钮', '导入星历数据' in buttons,
       str(sorted(buttons)[:8]))
    tip = buttons['刷新TLE'].toolTip()
    ok('「刷新TLE」提示列出数据源（读设置生效）',
       sp.DEFAULT_TLE_SOURCES[0] in tip, tip.splitlines()[0])
    ok('提示说明只按编号更新、不删除已有卫星',
       '不会因为数据源里暂时没有而被删除' in tip)

    cache_before = open(TLE_CACHE, encoding='utf-8', errors='replace').read()
    before = by_key(cache_before)
    ok('本地星历缓存已载入（验证保留语义的基线）', len(before) > 1,
       '%d 颗' % len(before))

    # --- 造导入文件：① 一颗已存在（只改历元） ② 一颗全新 ---
    exist_id = sorted(k[1] for k in before if k[0] == 'num'
                      and k[1].isdigit())[10]
    exist_name = next(n for k, (n, _) in before.items() if k == ('num', exist_id))

    def _mktle(name, num_field, epoch):
        return ('%s\n1 %sU 98067A   %s  .00010000  00000-0  20000-3 0  9990\n'
                '2 %s  %7.4f 170.0000 0006000  70.0000 290.0000 15.50000000 10009\n'
                % (name, num_field, epoch, num_field, 51.6))

    imp_text = (_mktle(exist_name, '%05d' % int(exist_id), '26999.50000000') +
                _mktle('BRAND-NEW-SAT', '99901', '26999.60000000'))
    tmpdir = tempfile.mkdtemp(prefix='fhl_import_')
    imp_path = os.path.join(tmpdir, 'import.tle')
    with open(imp_path, 'w', encoding='utf-8') as f:
        f.write(imp_text)

    info_msgs.clear()
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (imp_path, ''))
    try:
        buttons['导入星历数据'].click()
    finally:
        QFileDialog.getOpenFileName = _real_getfile
    app.processEvents()

    ok('导入后弹「导入完成」', any(t == '导入完成' for t, _ in info_msgs),
       str([t for t, _ in info_msgs]))
    text = '\n'.join(t for _, t in info_msgs)
    ok('报告按编号增量结果（更新 1 / 新增 1）',
       ('更新 1 颗' in text and '新增 1 颗' in text), text.replace('\n', ' | '))
    ok('不自动勾选：文案已说明', '导入不会自动勾选' in text)
    ok('不再出现「仅默认选择前 N 颗」', '仅默认选择' not in text, text)

    after = by_key(open(TLE_CACHE, encoding='utf-8', errors='replace').read())
    ok('导入结果写回缓存：新编号已追加', ('num', '99901') in after)
    ok('缓存里原有卫星全部保留（未删除）',
       set(before).issubset(set(after)),
       '%d → %d' % (len(before), len(after)))
    ok('同编号被新数据替换（历元已更新）',
       '26999.50000000' in after[('num', exist_id)][1].line1,
       after[('num', exist_id)][1].line1)
    ok('缓存总量 = 原有 + 1', len(after) == len(before) + 1,
       '%d vs %d' % (len(after), len(before)))

    # --- 二次导入同一文件：只更新，不新增 ---
    info_msgs.clear()
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (imp_path, ''))
    try:
        buttons['导入星历数据'].click()
    finally:
        QFileDialog.getOpenFileName = _real_getfile
    app.processEvents()
    text2 = '\n'.join(t for _, t in info_msgs)
    ok('重复导入只更新不新增（更新 2 / 新增 0）',
       '更新 2 颗、新增 0 颗' in text2, text2.replace('\n', ' | '))
    after2 = open(TLE_CACHE, encoding='utf-8', errors='replace').read()
    ok('重复导入后缓存颗数不变',
       len(by_key(after2)) == len(after))

    # --- 非法文件：提示且不改动缓存 ---
    bad = os.path.join(tmpdir, 'bad.txt')
    with open(bad, 'w', encoding='utf-8') as f:
        f.write('这不是 TLE 数据\n随便写点什么\n')
    info_msgs.clear()
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (bad, ''))
    try:
        buttons['导入星历数据'].click()
    finally:
        QFileDialog.getOpenFileName = _real_getfile
    app.processEvents()
    ok('非法文件给出「导入失败」', any(t == '导入失败' for t, _ in info_msgs),
       str([t for t, _ in info_msgs]))
    ok('非法导入不改动缓存',
       open(TLE_CACHE, encoding='utf-8', errors='replace').read() == after2)

    # --- 取消文件对话框：什么都不做 ---
    info_msgs.clear()
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))
    try:
        buttons['导入星历数据'].click()
    finally:
        QFileDialog.getOpenFileName = _real_getfile
    ok('取消选择文件不弹任何提示', not info_msgs, str(info_msgs))

    win.close()
    app.processEvents()
finally:
    QMessageBox.information = _real_info
    QMessageBox.warning = _real_warn
    QFileDialog.getOpenFileName = _real_getfile
    sw.ObserverDialog.exec = _real_obs
    sw.SatelliteSelectDialog.exec = _real_sel
    for path, bak in backups:
        shutil.copyfile(bak, path)
        os.remove(bak)

print()
failed = [r for r in RESULT if r[0] == 'FAIL']
print('总计 %d 项，失败 %d 项' % (len(RESULT), len(failed)))
for r in failed:
    print('  FAIL:', r[1], r[2])
print('RESULT:', 'ALL PASS' if not failed else 'HAS FAILURES')
sys.exit(1 if failed else 0)
