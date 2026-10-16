# -*- coding: utf-8 -*-
"""校验 .fhla 扩展格式：格式层往返 + 主窗口真实读写时的属性维护。

覆盖点：
  A 格式层（不依赖界面）：写→读往返、自定义记录项目（other_item）、逐属性读写、
    加密落盘与加密状态、按扩展名分派（.fhla / .fhl）
  B 主窗口（真实调用链）：
      1) 打开 .fhla（属性随文件带进来）
      2) 「打开即自动保存」不算一次编辑——只刷「上次打开所用版本」，
         创建者与最后编辑时间不变
      3) 真改一条后再保存 → 最后编辑者/最后编辑时间被刷新，创建者仍是最初的人
      4) 加密保存 → 文件变密文、属性里 encrypted=True、无密钥读不出
      5) 「项目属性」窗口文案（QMessageBox 静态方法按 Qt 行为必须整体替换）
      6) .fhl 项目格式不变（仍是纯记录列表），属性窗口给出「保存为 .fhla 才落盘」提示

离屏运行；项目备份路径重定向到临时目录，不触碰 file/ 里的用户数据。
用法：python tests/__fhla_smoke.py
"""
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QTableWidget, QPushButton

from f_hamlog import backup
from f_hamlog import fhl_rw
# .fhla 的实现已内嵌进 project.py（原 fhla_rw.py 模块），这里用别名沿用旧名字，
# 测试正文不必逐行改。
from f_hamlog import project as fhla_rw

TMP = tempfile.mkdtemp(prefix='fhl_fhla_smoke_')
FHLA = os.path.join(TMP, 'demo.fhla')
FHLA_EXPORT = os.path.join(TMP, 'export.fhla')
FHL = os.path.join(TMP, 'demo.fhl')
# 记下「未被本测试改写前」的备份默认路径（F4 要断言它是数据目录下的绝对路径）
_DEFAULT_PROJECT_BACKUP = backup.PROJECT_BACKUP
_DEFAULT_BATCH_BACKUP = backup.BATCH_BACKUP
backup.PROJECT_BACKUP = os.path.join(TMP, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def pump(n=5):
    for _ in range(n):
        app.processEvents()


def _button(win, text):
    """按源码中文原文找按钮（英文界面下按 i18n.tr 后的文字再找一遍）。"""
    from f_hamlog import i18n as _i18n
    wanted = {text, _i18n.tr(text)}
    return next((b for b in win.findChildren(QPushButton) if b.text() in wanted), None)


def _table(win):
    return win.findChild(QTableWidget)


def _recs(n, note=''):
    out = []
    for i in range(n):
        out.append({
            'date': '2026-10-16', 'time': '%02d:00' % (20 + i), 'm_call': 'BI8SQL',
            'o_call': 'BG5ABC%d' % i, 'freq': '144.100', 'freq_rx': '145.100',
            'mode': 'FM', 'prop_mode': 'SAT', 'sat_name': 'SO-50',
            'm_rst': '59', 'o_rst': '59', 'm_qth': '杭州', 'o_qth': '北京',
            'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
            'notes': note,
            'wx': '晴',              # 自定义记录项目（FIELD_LABELS 之外的字段）
        })
    return out


def _cleanup():
    shutil.rmtree(TMP, ignore_errors=True)


import atexit
atexit.register(_cleanup)

# ==========================================================================
# A. 格式层
# ==========================================================================
print('--- A 格式层 ---', flush=True)
recs = _recs(3, 'A')
proj = fhla_rw.fhla_project({'xml': {}, 'project': recs})
proj.add_other_item('wx', '天气')
proj.mark_edited('BD0AAA')
fhla_rw.write_fhla_file(FHLA, proj, editor='BD0AAA')

back, back_key = fhla_rw.read_fhla_file(FHLA, ask_key=False)
ok('A1 记录原样往返（含自定义字段）', back.get_fhl() == recs)
ok('A2 自定义记录项目往返', back.get_other_item() == {'wx': '天气'}, str(back.get_other_item()))
ok('A3 创建者 / 创建时间已写入', back.creator == 'BD0AAA' and bool(back.created_time),
   f'{back.creator} / {back.created_time}')
ok('A4 last_version = 当前版本', back.last_version == fhla_rw.current_version(), back.last_version)
ok('A5 明文文件 encrypted=False 且探测一致',
   back.encrypted is False and fhla_rw.detect_encrypted(FHLA) is False)

# 自定义字段与标准标签并集
labels = fhla_rw.standard_field_labels()
ok('A6 标准标签取自 FIELD_LABELS', labels.get('o_call') == '对方呼号', str(labels.get('o_call')))
ok('A7 field_labels = 标准 + 自定义',
   proj.field_labels().get('o_call') == '对方呼号' and proj.field_labels().get('wx') == '天气')

# 逐属性读写
proj.write_meta('creator', 'X1')
ok('A8 write_meta 生效', proj.creator == 'X1')
proj.write_other_item({'rig': '电台'})
ok('A9 write_other_item 整体替换', proj.get_other_item() == {'rig': '电台'})
proj.remove_other_item('rig')
ok('A10 remove_other_item 生效', proj.get_other_item() == {})

# 加密
fhla_rw.write_fhla_file(FHLA_EXPORT, recs, key='pwd123', editor='BG5ABC')
ok('A11 加密落盘被识别为密文', fhla_rw.detect_encrypted(FHLA_EXPORT) is True)
enc_back, enc_key = fhla_rw.read_fhla_file(FHLA_EXPORT, key='pwd123')
ok('A12 有密钥可正常解密', enc_back is not None and enc_back.get_fhl() == recs)
ok('A13 属性里 encrypted=True', enc_back.encrypted is True)
ok('A14 无密钥读不出（返回 None）', fhla_rw.read_fhla_file(FHLA_EXPORT, ask_key=False)[0] is None)

# 分派
r_a, k_a, m_a = fhla_rw.read_project_file(FHLA)
ok('A15 read_project_file(.fhla) 给出记录 + 属性', r_a == recs and isinstance(m_a, dict))
fhla_rw.save_project_file(FHL, recs, editor='BD0AAA')
r_b, k_b, m_b = fhla_rw.read_project_file(FHL)
ok('A16 .fhl 仍是纯记录列表（meta=None，格式未变）', r_b == recs and m_b is None)
with open(FHL, 'r', encoding='utf-8') as f:
    raw = json.load(f)
ok('A17 .fhl 磁盘内容就是 list', isinstance(raw, list))
ok('A18 classify: is_fhla_path 大小写不敏感',
   fhla_rw.is_fhla_path('a.FHLA') and not fhla_rw.is_fhla_path('a.fhl'))
ok('A19 缺键的旧 fhla 能补默认值',
   fhla_rw.fhla_project({'project': []}).get_xml()['creator'] == '')
ok('A20 结构不对时明确报错', _raises(lambda: fhla_rw.fhla_project({'foo': 1})))


# ==========================================================================
# B. 主窗口（真实链路）
# ==========================================================================
print('--- B 主窗口 ---', flush=True)
from f_hamlog import project as pj

# 造一份「别人建好的」.fhla：创建者 BD0AAA、带自定义记录项目
proj = fhla_rw.fhla_project({'xml': {}, 'project': _recs(3, 'B')})
proj.add_other_item('wx', '天气')
fhla_rw.write_fhla_file(FHLA, proj, editor='BD0AAA')

data, key, meta = fhla_rw.read_project_file(FHLA)
ok('B1 打开 .fhla 读到属性块', isinstance(meta, dict) and meta.get('creator') == 'BD0AAA')

win = QtWidgets.QMainWindow()
pj.main(win, filee=data, save_path=FHLA, key_=key, fhla_meta=meta)
win.show()
pump(6)
api = win._perf_api
ok('B2 窗口持有属性块', (api['fhla_meta'].get('meta') or {}).get('creator') == 'BD0AAA')
editor = api['fhla_editor']()
ok('B3 编辑者取自设置呼号或系统用户名', bool(editor), editor)
ok('B4 未保存时无未保存标记的误报', api['_bk_is_dirty']() is False)

_, _, m1 = fhla_rw.read_project_file(FHLA)
ok('B5 「打开即自动保存」保住创建者', m1['creator'] == 'BD0AAA', m1['creator'])
ok('B6 「打开即自动保存」不算编辑（编辑时间未被刷）',
   m1['last_edit_time'] == m1['created_time'],
   f"{m1['created_time']} -> {m1['last_edit_time']}")
ok('B7 写回了「上次打开所用版本」', m1['last_version'] == fhla_rw.current_version(),
   m1['last_version'])

# —— 真改一条：追加记录（append_to_project 会直接落盘）——
time.sleep(1.05)          # 时间戳精度到秒，睡一下才能看出「被刷新」
before_edit = m1['last_edit_time']
api['append_to_project']([{
    'date': '2026-10-16', 'time': '23:59', 'm_call': 'BI8SQL', 'o_call': 'BG9ZZZ',
    'freq': '145.500', 'freq_rx': '145.500', 'mode': 'FM', 'prop_mode': 'E',
    'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
    'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
    'notes': 'B-edit', 'wx': '雨',
}])
pump(6)

recs2, _, m2 = fhla_rw.read_project_file(FHLA)
ok('B8 记录条数 +1', len(recs2) == 4, str(len(recs2)))
ok('B9 新记录的自定义字段保留', recs2[-1].get('wx') == '雨', str(recs2[-1].get('wx')))
ok('B10 编辑后 最后编辑者 = 当前操作者', m2['last_editor'] == editor,
   f"{m2['last_editor']} vs {editor}")
ok('B11 编辑后 最后编辑时间被刷新', m2['last_edit_time'] > before_edit,
   f"{before_edit} -> {m2['last_edit_time']}")
ok('B12 创建者仍是最初的人', m2['creator'] == 'BD0AAA', m2['creator'])
ok('B13 创建时间未被改', m2['created_time'] == m1['created_time'])
ok('B14 自定义记录项目仍在', m2['other_item'] == {'wx': '天气'}, str(m2['other_item']))

# —— 「项目属性」窗口（.fhla）——
captured = {}
_orig_info = QMessageBox.information


def _fake_info(parent, title, text, *a, **k):
    captured['title'] = title
    captured['text'] = text
    return QMessageBox.Ok


QMessageBox.information = _fake_info
try:
    # 注意：这些 QAction 的 QObject 父级是窗口（而非菜单），要按窗口递归找
    act = next((a for a in win.findChildren(QAction) if a.text() == '项目属性'), None)
    ok('B15 文件菜单里有「项目属性」', act is not None)
    if act is not None:
        act.trigger()
        pump(3)
finally:
    QMessageBox.information = _orig_info
text = captured.get('text', '')
ok('B16 属性窗口标题', captured.get('title') == '项目属性', str(captured.get('title')))
for frag in ('创建者（第一次编辑的人）：BD0AAA', '最后一次编辑的人：' + editor,
             '创建时间：', '最后一次编辑时间：', '上次打开所用版本：F HamLog',
             '加密状态：未加密', '自定义记录项目：wx（天气）', 'fhla v1'):
    ok(f'B17 属性文案含「{frag}」', frag in text, text.replace('\n', ' | ')[:160])

# —— 应用内加密保存 ——
pj.key = 'pwd123'
api['save']()
pump(4)
ok('B18 加密保存后文件是密文', fhla_rw.detect_encrypted(FHLA) is True)
enc = fhla_rw.read_fhla_file(FHLA, key='pwd123')[0]
ok('B19 加密后属性 encrypted=True', enc is not None and enc.encrypted is True)
ok('B20 加密后记录与属性完整',
   enc is not None and len(enc.get_fhl()) == 4 and enc.creator == 'BD0AAA'
   and enc.get_other_item() == {'wx': '天气'})
ok('B21 无密钥读不出', fhla_rw.read_fhla_file(FHLA, ask_key=False)[0] is None)

QMessageBox.information = _fake_info
try:
    captured.clear()
    act.trigger()
    pump(3)
finally:
    QMessageBox.information = _orig_info
ok('B22 加密状态在属性窗口显示为「已加密」',
   '加密状态：已加密' in captured.get('text', ''))
pj.key = None

# —— .fhl 项目：格式不变 + 属性窗口给提示 ——
win2 = QtWidgets.QMainWindow()
pj.main(win2, filee=_recs(2, 'C'), save_path=FHL)
win2.show()
pump(6)
ok('B23 .fhl 仍是纯记录列表（老读法 fhl_rw 仍可用）',
   isinstance(fhl_rw.read_fhl_file(FHL)[0], list)
   and isinstance(json.load(open(FHL, encoding='utf-8')), list))
QMessageBox.information = _fake_info
try:
    captured.clear()
    act2 = next((a for a in win2.findChildren(QAction) if a.text() == '项目属性'), None)
    ok('B24 第二个窗口也有「项目属性」', act2 is not None)
    if act2 is not None:
        act2.trigger()
        pump(3)
finally:
    QMessageBox.information = _orig_info
ok('B25 .fhl 下「项目属性」提示不支持的格式',
   '不支持的格式' in captured.get('text', '') and '.fhla' in captured.get('text', ''),
   captured.get('text', '').replace('\n', ' | ')[:200])

# ==========================================================================
# C. 另存为 .fhla（.fhl 项目转存：新建属性块，创建者 = 本次操作者）
# ==========================================================================
print('--- C 另存为 .fhla ---', flush=True)
from PySide6.QtWidgets import QFileDialog

FHLA2 = os.path.join(TMP, 'from_fhl.fhla')
_orig_save = QFileDialog.getSaveFileName
# 原生静态对话框自带模态循环，替换 QDialog.exec 拦不住 → 必须替换静态方法本身
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (FHLA2, ''))
try:
    act3 = next((a for a in win2.findChildren(QAction) if a.text() == '另存为'), None)
    ok('C1 找到「另存为」', act3 is not None)
    if act3 is not None:
        act3.trigger()
        pump(5)
finally:
    QFileDialog.getSaveFileName = _orig_save
ok('C2 另存为 .fhla 后文件存在', os.path.exists(FHLA2))
if os.path.exists(FHLA2):
    c_recs, c_key, c_meta = fhla_rw.read_project_file(FHLA2)
    ok('C3 .fhl 项目转存后记录完整', len(c_recs) == 2, str(len(c_recs)))
    ok('C4 新 .fhla 的创建者 = 本次操作者', c_meta['creator'] == editor, str(c_meta['creator']))
    ok('C5 新 .fhla 记下版本', c_meta['last_version'] == fhla_rw.current_version())
    ok('C6 明文（未加密项目另存仍为明文）', fhla_rw.detect_encrypted(FHLA2) is False)

# ==========================================================================
# D. 直接把 .fhla 整块内容交给主窗口（扩展名不对时的兜底：不能当空项目覆盖）
# ==========================================================================
print('--- D 整块内容直传 ---', flush=True)
FHLA3 = os.path.join(TMP, 'direct.fhla')
proj3 = fhla_rw.fhla_project({'xml': {}, 'project': _recs(4, 'D')})
proj3.add_other_item('wx', '天气')
proj3.mark_edited('BD0AAA')
payload = proj3.output_fhla_project()

win3 = QtWidgets.QMainWindow()
pj.main(win3, payload, save_path=FHLA3)
win3.show()
pump(6)
api3 = win3._perf_api
ok('D1 记录被接收（没被当成空项目）', api3['get_table']().rowCount() == 4,
   str(api3['get_table']().rowCount()))
ok('D2 属性块被一并接住',
   (api3['fhla_meta'].get('meta') or {}).get('creator') == 'BD0AAA')
d_recs, _, d_meta = fhla_rw.read_project_file(FHLA3)
ok('D3 落盘后记录仍是 4 条（无数据丢失）', len(d_recs) == 4, str(len(d_recs)))
ok('D4 自定义记录项目随属性保留', d_meta.get('other_item') == {'wx': '天气'})

# ==========================================================================
# E. 保存时由用户选格式（.fhl / .fhla 各一条过滤器）+ 扩展名补全
# ==========================================================================
print('--- E 保存格式自选 ---', flush=True)

filters = fhla_rw.project_save_filters()
parts = filters.split(';;')
ok('E1 保存过滤器是两条（.fhl / .fhla 各一条）',
   len(parts) == 2 and '*.fhl' in parts[0] and '*.fhla' in parts[1], filters)

# 扩展名补全矩阵（Qt 静态保存对话框不会替用户补后缀）
ok('E2 选 .fhla 过滤器 + 无扩展名 → 补 .fhla',
   fhla_rw.complete_project_suffix('123', parts[1]) == '123.fhla')
ok('E3 选 .fhl 过滤器 + 无扩展名 → 补 .fhl',
   fhla_rw.complete_project_suffix('123', parts[0]) == '123.fhl')
ok('E4 没拿到所选过滤器时默认补 .fhl',
   fhla_rw.complete_project_suffix('123', '') == '123.fhl')
ok('E5 已有扩展名不重复补（大小写不敏感）',
   fhla_rw.complete_project_suffix('123.FHLA', parts[0]) == '123.FHLA'
   and fhla_rw.complete_project_suffix('123.fhl', parts[1]) == '123.fhl')

# 走一遍真实链路：把所选过滤器 + 不带扩展名的文件名交给「另存为」
def _strip_ext(p):
    low = p.lower()
    for ext in ('.fhla', '.fhl'):
        if low.endswith(ext):
            return p[:-len(ext)]
    return p


BARE = os.path.join(TMP, 'bare')
for tag, sel, want in (('E6 真实另存为：选 .fhla', parts[1], BARE + '.fhla'),
                       ('E7 真实另存为：选 .fhl', parts[0], BARE + '.fhl')):
    # 模拟用户在对话框里「选了某条过滤器 + 只输入不带扩展名的文件名」
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, _w=want, _s=sel, **k: (_strip_ext(_w), _s))
    try:
        act4 = next((a for a in win2.findChildren(QAction) if a.text() == '另存为'), None)
        if act4 is not None:
            act4.trigger()
            pump(5)
    finally:
        QFileDialog.getSaveFileName = _orig_save
    ok(tag + ' → 按所选格式落盘 ' + os.path.basename(want), os.path.exists(want))
    if os.path.exists(want):
        # .fhl 落盘 = 纯 list；.fhla 落盘 = 带 xml 属性块
        raw = json.load(open(want, encoding='utf-8'))
        ok(tag + ' → 磁盘结构与该格式一致',
           (isinstance(raw, list) if want.endswith('.fhl')
            else isinstance(raw, dict) and 'xml' in raw and 'project' in raw),
           type(raw).__name__)

# 英文界面下两条过滤器都要翻到（调用处翻译，过滤器不走控件树）
# 直接改 i18n._lang 而不调 set_language：后者会把语言写进 file/m_xml.txt（用户的真实设置）
from f_hamlog import i18n as _i18n

_zh_filters = fhla_rw.project_save_filters()
_saved_lang = _i18n._lang
try:
    _i18n._lang = _i18n.LANG_EN
    _en_filters = fhla_rw.project_save_filters()
finally:
    _i18n._lang = _saved_lang
ok('E8 英文界面下过滤器已翻译（无中文残留）',
   not any('\u4e00' <= c <= '\u9fff' for c in _en_filters) and _en_filters.count(';;') == 1,
   _en_filters)
ok('E9 中文界面下过滤器就是源码原文',
   _zh_filters == fhla_rw.SAVE_FILTER_FHL + ';;' + fhla_rw.SAVE_FILTER_FHLA, _zh_filters)

# ==========================================================================
# H. Alt+Enter 打开属性 + 自定义日志字段（.fhla 属性块 other_item）
# ==========================================================================
print('--- H 属性快捷键 / 自定义日志字段 ---', flush=True)

HF = os.path.join(TMP, 'custom.fhla')
projH = fhla_rw.fhla_project({'xml': {}, 'project': _recs(2, 'H')})
projH.add_other_item('wx', '天气')
fhla_rw.write_fhla_file(HF, projH, editor='BD0AAA')
h_recs, h_key, h_meta = fhla_rw.read_project_file(HF)

win6 = QtWidgets.QMainWindow()
pj.main(win6, filee=h_recs, save_path=HF, key_=h_key, fhla_meta=h_meta)
win6.show()
pump(6)
api6 = win6._perf_api

# —— H1 快捷键：Alt+Enter（Return 与 Enter 两个键都收下）——
act_props = next((a for a in win6.findChildren(QAction) if a.text() == '项目属性'), None)
ok('H1 找不到「项目属性」菜单项', act_props is not None)
if act_props is not None:
    seqs = {s.toString() for s in act_props.shortcuts()}
    ok('H2 「项目属性」快捷键 = Alt+Enter（Return / Enter 都认）',
       seqs == {'Alt+Return', 'Alt+Enter'}, str(sorted(seqs)))
    ok('H3 不再占用 Ctrl+I（留给反选）', 'Ctrl+I' not in seqs)
    ok('H4 两个键各自都能精确匹配（Return 与 Enter 互不等价，所以两个都要挂）',
       all(any(s.matches(QKeySequence(k)) == QKeySequence.ExactMatch
               for s in act_props.shortcuts())
           for k in ('Alt+Return', 'Alt+Enter'))
       and QKeySequence('Alt+Return') != QKeySequence('Alt+Enter'))

# 真按一次键（离屏也能走通快捷键链路）：Alt+Enter → 属性窗口
_orig_info_h = QMessageBox.information
captured.clear()
QMessageBox.information = _fake_info
try:
    win6.activateWindow()
    pump(2)
    QTest.keyClick(win6, Qt.Key_Return, Qt.AltModifier)
    pump(3)
finally:
    QMessageBox.information = _orig_info_h
ok('H4b Alt+Enter 真按键能打开属性窗口',
   '创建者（第一次编辑的人）' in captured.get('text', ''),
   captured.get('text', '').replace('\n', ' | ')[:80])

# —— H5 管理窗口：列出现有字段 → 添加一个 → 保存即落盘 ——
act_cf = next((a for a in win6.findChildren(QAction) if a.text() == '自定义日志字段'), None)
ok('H5 文件菜单里有「自定义日志字段」', act_cf is not None)

# H 段内一律把 QMessageBox.warning 换成捕获版：校验失败时既不阻塞模态循环，
# 又能把提示文案取出来断言（H 段结束处恢复）。
warn_cap = {}
_orig_warning = QMessageBox.warning


def _fake_warning(parent, title, text, *a, **k):
    warn_cap['text'] = text
    return QMessageBox.Ok


QMessageBox.warning = _fake_warning

if act_cf is not None:
    act_cf.trigger()
    pump(3)
mw = api6['custom_fields_window']()
ok('H6 管理窗口已打开', mw is not None and mw.isVisible())
mtbl = _table(mw)
ok('H7 列出现有自定义字段 wx / 天气',
   mtbl.rowCount() == 1 and mtbl.item(0, 0).text() == 'wx'
   and mtbl.item(0, 1).text() == '天气',
   '%d 行' % mtbl.rowCount())

_button(mw, '添加字段').click()
pump(2)
row = mtbl.rowCount() - 1
mtbl.item(row, 0).setText('rx_pwr')
mtbl.item(row, 1).setText('接收功率')
_button(mw, '保存更改').click()
pump(4)
ok('H8 属性块记下新字段', api6['custom_fields']() == {'wx': '天气', 'rx_pwr': '接收功率'},
   str(api6['custom_fields']()))
_, _, mH = fhla_rw.read_project_file(HF)
ok('H9 .fhla 里立即落盘（不用再手动保存）',
   mH['other_item'] == {'wx': '天气', 'rx_pwr': '接收功率'}, str(mH['other_item']))
ok('H10 改字段定义也算一次编辑（编辑者/时间已刷）',
   mH['last_edit_time'] >= mH['created_time'] and mH['last_editor'] == editor,
   f"{mH['created_time']} -> {mH['last_edit_time']} by {mH['last_editor']}")

# 校验：标准字段键 / 非法键 / 缺显示名 一律拒绝，且不写盘
for tag, key, label, frag in (
        ('H11 标准字段键被拒绝', 'freq', '频率2', '标准字段'),
        ('H12 非法字段键被拒绝', '1abc', '随便', '字母、数字、下划线'),
        ('H13 缺显示名称被拒绝', 'extra', '', '缺少显示名称')):
    if act_cf is not None:
        act_cf.trigger()
        pump(3)
    mw = api6['custom_fields_window']()
    mtbl = _table(mw)
    _button(mw, '添加字段').click()
    pump(1)
    row = mtbl.rowCount() - 1
    mtbl.item(row, 0).setText(key)
    mtbl.item(row, 1).setText(label)
    warn_cap.clear()
    _button(mw, '保存更改').click()
    pump(2)
    ok(tag, frag in warn_cap.get('text', ''), str(warn_cap.get('text')))
    ok(tag + '（窗口没关、字段没变）',
       api6['custom_fields']() == {'wx': '天气', 'rx_pwr': '接收功率'})
    mw.close()
    pump(1)

# —— H14 「新建日志」：自定义字段排在标准 20 行之后，填了值就带上 ——
api6['new']()
pump(3)
nw = pj.project_others_window
ntbl = _table(nw)
ok('H14 「新建日志」行数 = 20 标准 + 2 自定义', ntbl.rowCount() == 22,
   '%d 行' % ntbl.rowCount())
ok('H15 标准行号未被顶掉（行 2 = 己方呼号，仍挂大写委托）',
   ntbl.item(2, 0).text() == '己方呼号'
   and ntbl.itemDelegateForRow(2) is not None)
ok('H16 自定义字段追加在末尾（天气 / 接收功率）',
   ntbl.item(20, 0).text() == '天气' and ntbl.item(21, 0).text() == '接收功率',
   f'{ntbl.item(20, 0).text()} / {ntbl.item(21, 0).text()}')

# 必填字段（m_call / o_call / freq / mode）先补齐，否则保存会被校验拦下
ntbl.item(2, 1).setText('BI8SQL')
ntbl.item(3, 1).setText('BG9ZZZ')
ntbl.item(4, 1).setText('145.500')
ntbl.item(8, 1).setText('FM')
ntbl.item(20, 1).setText('晴')
ntbl.item(21, 1).setText('5W')
warn_cap.clear()
_button(nw, '新建日志').click()
pump(5)
ok('H17 新建时没有触发校验提示', warn_cap.get('text') is None, str(warn_cap.get('text')))
new_rec = pj.file[-1]
ok('H18 新日志带上自定义字段值',
   new_rec.get('wx') == '晴' and new_rec.get('rx_pwr') == '5W',
   f"wx={new_rec.get('wx')} rx_pwr={new_rec.get('rx_pwr')}")
h_new = fhla_rw.read_project_file(HF)[0][-1]
ok('H19 自定义值也落到磁盘', h_new.get('wx') == '晴' and h_new.get('rx_pwr') == '5W',
   str(h_new.get('wx')))

# —— H20 「更多信息」：显示自定义值，改后写回；留空则移除该键 ——
idx = len(pj.file) - 1
api6['project_others'](idx)
pump(3)
ow = pj.project_others_window
otbl = _table(ow)
ok('H20 「更多信息」显示自定义字段值',
   otbl.rowCount() == 22 and otbl.item(20, 0).text() == '天气'
   and otbl.item(20, 1).text() == '晴',
   otbl.item(20, 1).text() if otbl.rowCount() > 20 else '')
otbl.item(20, 1).setText('阴')
_button(ow, '保存更改').click()
pump(4)
ok('H21 改后写回记录', pj.file[idx].get('wx') == '阴', str(pj.file[idx].get('wx')))

api6['project_others'](idx)
pump(3)
ow = pj.project_others_window
otbl = _table(ow)
otbl.item(21, 1).setText('')
_button(ow, '保存更改').click()
pump(4)
ok('H22 自定义字段留空 → 记录里移除该键（不塞空字段）',
   'rx_pwr' not in pj.file[idx] and 'rx_pwr' not in fhla_rw.read_project_file(HF)[0][idx])

# —— H23 英文界面：新窗口的固定文案要翻到，自定义字段名（用户数据）保持原样 ——
_saved_lang = _i18n._lang
try:
    _i18n._lang = _i18n.LANG_EN
    api6['new']()
    pump(3)
    nw = pj.project_others_window
    ntbl = _table(nw)
    ok('H23 英文界面下标准字段名已翻译',
       ntbl.item(2, 0).text() == _i18n.tr('己方呼号')
       and not any('\u4e00' <= c <= '\u9fff' for c in ntbl.item(2, 0).text()),
       ntbl.item(2, 0).text())
    ok('H24 自定义字段名原样显示（用户数据不参与翻译）',
       ntbl.item(20, 0).text() == '天气' and ntbl.item(21, 0).text() == '接收功率',
       f'{ntbl.item(20, 0).text()} / {ntbl.item(21, 0).text()}')
    api6['manage_custom_fields']()
    pump(3)
    mw = api6['custom_fields_window']()
    # 真应用里由 i18n.install(app) 的 Show 事件过滤器自动翻一遍；本脚本没装过滤器，
    # 就显式调一次（同一个函数），断言的是「窗口文案确实可被翻译」。
    _i18n.translate_tree(mw)
    pump(2)
    btns = {b.text() for b in mw.findChildren(QPushButton)}
    ok('H25 管理窗口按钮已翻译（无中文残留）',
       btns == {'Add field', 'Delete selected', 'Save changes'}, str(sorted(btns)))
    ok('H26 管理窗口表头已翻译',
       {_table(mw).horizontalHeaderItem(i).text() for i in (0, 1)}
       == {'Field key', 'Display name'},
       str([_table(mw).horizontalHeaderItem(i).text() for i in (0, 1)]))
    mw.close()
    pump(1)
finally:
    _i18n._lang = _saved_lang

QMessageBox.warning = _orig_warning

# —— H27 .fhl 属不受支持的格式：自定义字段一律不给（拒绝打开管理窗口 + 录入窗口只显示标准行）——
FHL_CF = os.path.join(TMP, 'custom.fhl')
win7 = QtWidgets.QMainWindow()
# 故意连属性块一起塞进去：光靠「meta 为空」不算通过，必须是格式把关把字段挡在外面
pj.main(win7, filee=_recs(1, 'H2'), save_path=FHL_CF,
        fhla_meta={'other_item': {'wx': '天气', 'rx_pwr': '接收功率'}})
win7.show()
pump(6)
api7 = win7._perf_api
pj.custom_fields_window = None      # 清掉 H 段前面留下的引用，否则分辨不出「这次到底建没建」
QMessageBox.information = _fake_info
try:
    captured.clear()
    api7['manage_custom_fields']()
    pump(3)
finally:
    QMessageBox.information = _orig_info
ok('H27 .fhl 下「自定义日志字段」拒绝打开（窗口没建出来）',
   api7['custom_fields_window']() is None,
   str(api7['custom_fields_window']()))
ok('H28 .fhl 下提示不支持的格式（多段文案已翻）',
   '不支持的格式' in captured.get('text', '') and '.fhla' in captured.get('text', ''),
   captured.get('text', '').replace('\n', ' | ')[:200])
ok('H29 .fhl 下自定义字段取不到（即使内存里有属性块）',
   api7['custom_fields']() == {}, str(api7['custom_fields']()))

api7['new']()
pump(3)
nw7 = pj.project_others_window
ntbl7 = _table(nw7)
ok('H30 .fhl 下「新建日志」只有标准 20 行（不为无归宿的字段留位置）',
   ntbl7.rowCount() == 20, '%d 行' % ntbl7.rowCount())
nw7.close()
pump(1)

api7['project_others'](0)
pump(3)
ow7 = pj.project_others_window
ok('H31 .fhl 下「更多信息」同样只有标准 20 行', _table(ow7).rowCount() == 20,
   '%d 行' % _table(ow7).rowCount())
ow7.close()
pump(1)
ok('H32 .fhl 仍是纯记录列表', isinstance(json.load(open(FHL_CF, encoding='utf-8')), list))


# ==========================================================================
# F. 数据目录解析不被「cwd 下误建的空 file/」劫持
#    （2026-10-16 崩溃复盘：backup.py 用 cwd 相对路径写 file/project_backup.fhl，
#      在仓库根跑一次就造出假的 <仓库根>/file/，此后 main.fhl / pack_list.txt 全找不到）
# ==========================================================================
print('--- F 数据目录解析 ---', flush=True)

from f_hamlog import paths as _paths
from f_hamlog.paths import app_path as _app_path

REAL_DATA_DIR = os.path.join(PROJECT_DIR, 'src', 'f_hamlog')


def _data_dir_in(cwd):
    """子进程里（cwd 指定）导入 f_hamlog.paths，回显它解析出的 DATA_DIR。"""
    env = dict(os.environ)
    env['PYTHONPATH'] = os.path.join(PROJECT_DIR, 'src')
    env.pop('F_HAMLOG_DATA_DIR', None)
    env['QT_QPA_PLATFORM'] = 'offscreen'
    r = subprocess.run(
        [sys.executable, '-c',
         'from f_hamlog import paths; print(paths.DATA_DIR)'],
        cwd=cwd, env=env, capture_output=True, text=True)
    out = [ln for ln in (r.stdout or '').splitlines() if ln.strip()]
    return out[-1].strip() if out else ('<err> ' + (r.stderr or '').strip()[-200:])


# 现实中招的那个位置：仓库根（那里确实躺着一个假 file/）
ok('F1 从仓库根启动也解析到真正的数据目录',
   os.path.normcase(_data_dir_in(PROJECT_DIR)) == os.path.normcase(REAL_DATA_DIR),
   _data_dir_in(PROJECT_DIR))

# 合成一个「空的假 file/」：旧逻辑会认它（有 file/ 就用 cwd），新逻辑必须拒绝
STRAY = os.path.join(TMP, 'stray_cwd')
os.makedirs(os.path.join(STRAY, 'file'), exist_ok=True)
open(os.path.join(STRAY, 'file', 'project_backup.fhl'), 'w', encoding='utf-8').close()
ok('F2 假 file/（只有 project_backup.fhl）不被认作数据目录',
   os.path.isdir(os.path.join(STRAY, 'file'))
   and not _paths._looks_like_data_dir(STRAY))
ok('F3 在假 file/ 所在目录启动也不被劫持',
   os.path.normcase(_data_dir_in(STRAY)) == os.path.normcase(REAL_DATA_DIR),
   _data_dir_in(STRAY))

# 备份路径必须是数据目录下的绝对路径（这才是造出假 file/ 的源头）
ok('F4 备份默认路径是绝对路径且落在数据目录里',
   os.path.isabs(_DEFAULT_PROJECT_BACKUP) and os.path.isabs(_DEFAULT_BATCH_BACKUP)
   and os.path.dirname(_DEFAULT_PROJECT_BACKUP) == os.path.join(REAL_DATA_DIR, 'file'),
   _DEFAULT_PROJECT_BACKUP)
ok('F5 主窗依赖的数据文件都能解析到（main.fhl / pack_list.txt）',
   os.path.exists(_app_path('file/main.fhl')) and os.path.exists(_app_path('file/pack_list.txt')),
   _app_path('file/pack_list.txt'))

# 标记文件本身不可靠：假 file/ 里也会长出标记（跑一个「按相对路径写 file/」的遗留测试就会），
# 所以真正的保险是**解析顺序**——应用自己的目录（exe 旁 / 包目录）优先于 cwd。
STRAY_MARKED = os.path.join(TMP, 'stray_marked')
os.makedirs(os.path.join(STRAY_MARKED, 'file'), exist_ok=True)
with open(os.path.join(STRAY_MARKED, 'file', 'm_xml.txt'), 'w', encoding='utf-8') as f:
    f.write("{'m_call': 'BA1ABC'}")
with open(os.path.join(STRAY_MARKED, 'file', 'amateur.tle'), 'w', encoding='utf-8') as f:
    f.write('MOCK')
ok('F6 带数据标记的假 file/ 也不劫持（应用自身目录优先于 cwd）',
   os.path.normcase(_data_dir_in(STRAY_MARKED)) == os.path.normcase(REAL_DATA_DIR),
   _data_dir_in(STRAY_MARKED))

# ==========================================================================
# G. 缺文件容错：main.fhl / pack_list.txt 不在时也不能让窗口打不开
#    （2026-10-16 用户实际报的两个 FileNotFoundError）
# ==========================================================================
print('--- G 缺文件容错 ---', flush=True)
from f_hamlog import main as m

G_TMP = os.path.join(TMP, 'g')
os.makedirs(G_TMP, exist_ok=True)

# G1：「通联日志」的数据入口——文件不存在时按空项目处理（旧版这里抛 FileNotFoundError）
_missing_main = os.path.join(G_TMP, 'file', 'main.fhl')
ok('G1 缺 file/main.fhl 时按空项目处理（不再 FileNotFoundError）',
   m.load_quick_project_data(_missing_main) == ([], None), _missing_main)
_existing_main = os.path.join(G_TMP, 'has_main.fhl')
fhla_rw.save_project_file(_existing_main, _recs(2, 'G'))
ok('G2 有 main.fhl 时照常读回记录',
   len(m.load_quick_project_data(_existing_main)[0]) == 2)

_orig_pj_app_path = pj.app_path
pj.app_path = (lambda rel: os.path.join(G_TMP, 'missing_pack_list.txt')
               if rel.endswith('pack_list.txt') else _orig_pj_app_path(rel))
try:
    win5 = QtWidgets.QMainWindow()
    err2 = ''
    try:
        pj.main(win5, filee=_recs(1, 'G'), save_path=os.path.join(G_TMP, 'g.fhl'))
    except Exception as e:
        err2 = '%s: %s' % (type(e).__name__, e)
    pump(4)
finally:
    pj.app_path = _orig_pj_app_path
ok('G3 缺 pack_list.txt 时主窗仍能打开（按「无插件」处理）', err2 == '', err2)

QMessageBox.information = _orig_info
print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)
_cleanup()
atexit.unregister(_cleanup)
sys.exit(0 if all(PASS) else 1)
