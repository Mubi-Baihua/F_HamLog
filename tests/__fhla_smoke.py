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
# E. 保存时由用户选格式（默认 .fhla）+ 扩展名补全
# ==========================================================================
print('--- E 保存格式自选 ---', flush=True)

filters = fhla_rw.project_save_filters()
parts = filters.split(';;')
ok('E1 保存过滤器是两条，且默认（第一条）是 .fhla',
   len(parts) == 2 and '*.fhla' in parts[0] and '*.fhl' in parts[1], filters)
ok('E1b .fhla 的中文名是「F HamLog 项目」',
   parts[0].startswith('F HamLog 项目'), parts[0])
ok('E1c .fhl 的中文名是「F HamLog 兼容项目」',
   parts[1].startswith('F HamLog 兼容项目'), parts[1])

# 扩展名补全矩阵（Qt 静态保存对话框不会替用户补后缀）
ok('E2 选 .fhla 过滤器 + 无扩展名 → 补 .fhla',
   fhla_rw.complete_project_suffix('123', parts[0]) == '123.fhla')
ok('E3 选 .fhl 过滤器 + 无扩展名 → 补 .fhl',
   fhla_rw.complete_project_suffix('123', parts[1]) == '123.fhl')
ok('E4 没拿到所选过滤器时默认补 .fhla',
   fhla_rw.complete_project_suffix('123', '') == '123.fhla')
ok('E5 已有扩展名不重复补（大小写不敏感）',
   fhla_rw.complete_project_suffix('123.FHLA', parts[1]) == '123.FHLA'
   and fhla_rw.complete_project_suffix('123.fhl', parts[0]) == '123.fhl')

# 走一遍真实链路：把所选过滤器 + 不带扩展名的文件名交给「另存为」
def _strip_ext(p):
    low = p.lower()
    for ext in ('.fhla', '.fhl'):
        if low.endswith(ext):
            return p[:-len(ext)]
    return p


BARE = os.path.join(TMP, 'bare')
for tag, sel, want in (('E6 真实另存为：选 .fhla', parts[0], BARE + '.fhla'),
                       ('E7 真实另存为：选 .fhl', parts[1], BARE + '.fhl')):
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
ok('E9 中文界面下过滤器就是源码原文（.fhla 在前）',
   _zh_filters == fhla_rw.SAVE_FILTER_FHLA + ';;' + fhla_rw.SAVE_FILTER_FHL, _zh_filters)

# —— E10 操作者身份：填了呼号就用呼号，没填才用系统用户名 ——
_real_settings = pj.load_settings
try:
    pj.load_settings = lambda: {'m_call': ' bg5xyz '}
    ok('E10 填了呼号 → 操作者 = 大写呼号',
       pj.current_editor() == 'BG5XYZ', pj.current_editor())
    pj.load_settings = lambda: {'m_call': ''}
    _user = __import__('getpass').getuser().strip()
    ok('E11 没填呼号 → 退回系统用户名',
       pj.current_editor() == _user, pj.current_editor())
    pj.load_settings = lambda: {}
    ok('E12 设置里连键都没有 → 退回系统用户名', pj.current_editor() == _user)
    pj.load_settings = lambda: {'m_call': None}
    ok('E13 m_call 为 None 不会崩，也退回系统用户名', pj.current_editor() == _user)
    pj.load_settings = lambda: {}
    ok('E14 读不到设置（空 dict）时 my_call 为空串', pj.my_call() == '')
finally:
    pj.load_settings = _real_settings

# 真实设置文件里「填了呼号」的链路：临时设置文件（utf-8 BOM，最容易被读坏的那种）
_BOM_DIR = os.path.join(TMP, 'bom')
os.makedirs(os.path.join(_BOM_DIR, 'file'), exist_ok=True)
with open(os.path.join(_BOM_DIR, 'file', 'm_xml.txt'), 'w', encoding='utf-8-sig') as f:
    f.write("{'m_call': 'bh1abc', 'aouto_save': True}")
_real_app_path = pj.app_path
try:
    pj.app_path = lambda rel: os.path.join(_BOM_DIR, rel)
    ok('E15 带 BOM 的设置文件也能读出呼号', pj.current_editor() == 'BH1ABC',
       pj.current_editor())
finally:
    pj.app_path = _real_app_path

# —— E16 新建项目：对话框默认过滤器就是 .fhla ——
_new_cap = {}
_orig_save2 = QFileDialog.getSaveFileName


def _fake_new_save(parent, title, start, filt, *a, **k):
    _new_cap['filter'] = filt
    _new_cap['title'] = title
    return (os.path.join(TMP, 'new_default.fhla'), filt.split(';;')[0])


QFileDialog.getSaveFileName = staticmethod(_fake_new_save)
try:
    winN = QtWidgets.QMainWindow()
    pj.main(winN, filee=[], save_path='')
    winN.show()
    pump(4)
finally:
    QFileDialog.getSaveFileName = _orig_save2
ok('E16 新建项目时默认格式是 .fhla（第一条过滤器）',
   _new_cap.get('filter', '').split(';;')[0].startswith('F HamLog 项目'),
   _new_cap.get('filter', ''))

# ==========================================================================
# H. Alt+I 打开属性 + 自定义日志字段（.fhla 属性块 other_item）
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

# —— H1 快捷键：Alt+I ——
act_props = next((a for a in win6.findChildren(QAction) if a.text() == '项目属性'), None)
ok('H1 找不到「项目属性」菜单项', act_props is not None)
if act_props is not None:
    seqs = {s.toString() for s in act_props.shortcuts()}
    ok('H2 「项目属性」快捷键 = Alt+I', seqs == {'Alt+I'}, str(sorted(seqs)))
    ok('H3 不再占用 Ctrl+I（留给反选）', 'Ctrl+I' not in seqs)
    ok('H4 Alt+I 能精确匹配',
       any(s.matches(QKeySequence('Alt+I')) == QKeySequence.ExactMatch
           for s in act_props.shortcuts()))

# 真按一次键（离屏也能走通快捷键链路）：Alt+I → 属性窗口
_orig_info_h = QMessageBox.information
captured.clear()
QMessageBox.information = _fake_info
try:
    win6.activateWindow()
    pump(2)
    QTest.keyClick(win6, Qt.Key_I, Qt.AltModifier)
    pump(3)
finally:
    QMessageBox.information = _orig_info_h
ok('H4b Alt+I 真按键能打开属性窗口',
   '创建者（第一次编辑的人）' in captured.get('text', ''),
   captured.get('text', '').replace('\n', ' | ')[:80])

# —— H5 管理窗口（界面照「编辑卫星转发器」）：标准行 + 自定义行同表，只填名称 ——
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


def _open_cf():
    """重新打开管理窗口（保存会关窗）→ (窗口, 表格)。"""
    if act_cf is not None:
        act_cf.trigger()
        pump(3)
    win = api6['custom_fields_window']()
    return win, _table(win)


def _row_of(t, key):
    """按字段键找行号（行上记着 Qt.UserRole = 键）。"""
    for r in range(t.rowCount()):
        it = t.item(r, 0)
        if it is not None and it.data(Qt.UserRole) == key:
            return r
    return -1


def _flags_named(item):
    """标准行的名称单元格：不可编辑才算「只读」。"""
    return bool(item.flags() & Qt.ItemIsEditable)


mw, mtbl = _open_cf()
ok('H6 管理窗口已打开', mw is not None and mw.isVisible())
ok('H7 表头 = 字段名称 / 必填 / 在主页显示',
   [mtbl.horizontalHeaderItem(i).text() for i in range(3)]
   == ['字段名称', '必填', '在主页显示'],
   str([mtbl.horizontalHeaderItem(i).text() for i in range(3)]))
ok('H7b 行数 = 20 标准 + 1 自定义', mtbl.rowCount() == 21, '%d 行' % mtbl.rowCount())
ok('H7c 标准字段名不可编辑、自定义字段名可编辑',
   not _flags_named(mtbl.item(0, 0)) and _flags_named(mtbl.item(20, 0)))
ok('H7d 现有自定义字段在末尾，名称=天气 / 键=wx',
   mtbl.item(20, 0).text() == '天气' and mtbl.item(20, 0).data(Qt.UserRole) == 'wx',
   mtbl.item(20, 0).text())
_row_mcall = _row_of(mtbl, 'm_call')
ok('H7e 标准字段的「必填」= 历史必填项（己方呼号勾、备注不勾）',
   mtbl.item(_row_mcall, 1).checkState() == Qt.Checked
   and mtbl.item(_row_of(mtbl, 'notes'), 1).checkState() == Qt.Unchecked)
ok('H7f 标准字段的「在主页显示」已勾，且和自定义字段一样可点（不再是灰死状态）',
   mtbl.item(_row_mcall, 2).checkState() == Qt.Checked
   and bool(mtbl.item(_row_mcall, 2).flags() & Qt.ItemIsEnabled)
   and bool(mtbl.item(_row_of(mtbl, 'notes'), 2).flags() & Qt.ItemIsEnabled))
ok('H7g 标准字段的「必填」也可点（备注默认不勾）',
   bool(mtbl.item(_row_of(mtbl, 'notes'), 1).flags() & Qt.ItemIsEnabled))

# —— H8 添加字段：只填名称，键按名称自动生成 ——
_button(mw, '添加字段').click()
pump(1)
new_row = mtbl.rowCount() - 1
mtbl.item(new_row, 0).setText('接收功率')
_button(mw, '保存更改').click()
pump(4)
ok('H8 只填名称即可（键 = 名称，自动生成）',
   api6['custom_fields']() == {'wx': '天气', '接收功率': '接收功率'},
   str(api6['custom_fields']()))
_, _, mH = fhla_rw.read_project_file(HF)
ok('H9 .fhla 里立即落盘（不用再手动保存）',
   mH['other_item'] == {'wx': '天气', '接收功率': '接收功率'}, str(mH['other_item']))
ok('H10 改字段定义也算一次编辑（编辑者/时间已刷）',
   mH['last_edit_time'] >= mH['created_time'] and mH['last_editor'] == editor,
   f"{mH['created_time']} -> {mH['last_edit_time']} by {mH['last_editor']}")

# —— H11~H14 校验：重名 / 删标准行 / 空行 ——
for tag, name, frag in (
        ('H11 与标准字段重名被拒绝', '频率', '不能与标准字段重名'),
        ('H12 自定义字段重名被拒绝', '天气', '字段名称重复')):
    mw, mtbl = _open_cf()
    _button(mw, '添加字段').click()
    pump(1)
    mtbl.item(mtbl.rowCount() - 1, 0).setText(name)
    warn_cap.clear()
    _button(mw, '保存更改').click()
    pump(3)
    ok(tag, frag in warn_cap.get('text', ''), str(warn_cap.get('text')))
    ok(tag + '（字段没变）',
       api6['custom_fields']() == {'wx': '天气', '接收功率': '接收功率'})
    mw.close()
    pump(1)

mw, mtbl = _open_cf()
mtbl.selectRow(0)                       # 第 0 行是标准字段「日期」
warn_cap.clear()
_button(mw, '删除选中').click()
pump(2)
ok('H13 标准字段不能删除（提示且行还在）',
   '标准字段不能删除' in warn_cap.get('text', '') and mtbl.rowCount() == 22,
   str(warn_cap.get('text')))
mw.close()
pump(1)

mw, mtbl = _open_cf()
_button(mw, '添加字段').click()          # 留空行 → 保存时忽略
pump(1)
warn_cap.clear()
_button(mw, '保存更改').click()
pump(3)
ok('H14 空名称行被忽略（不报错、不新增字段）',
   warn_cap.get('text') is None
   and api6['custom_fields']() == {'wx': '天气', '接收功率': '接收功率'},
   str(warn_cap.get('text')))

# —— H15~H16 顺序：上移把新字段排到 wx 之前，落盘且对录入窗口生效 ——
mw, mtbl = _open_cf()
mtbl.setCurrentCell(_row_of(mtbl, '接收功率'), 0)
_button(mw, '上移').click()
pump(1)
_button(mw, '保存更改').click()
pump(4)
_order = [e[0] for e in api6['field_entries']()]
ok('H15 上移生效（field_order 里自定义字段换位）',
   _order[-2:] == ['接收功率', 'wx'], str(_order[-2:]))
_mH = fhla_rw.read_project_file(HF)[2]
ok('H16 field_order 已落盘', _mH.get('field_order', [])[-2:] == ['接收功率', 'wx'],
   str(_mH.get('field_order', [])[-2:]))

# —— H17 「新建日志」：行序跟着 field_order，自定义字段在末尾 ——
api6['new']()
pump(3)
nw = pj.project_others_window
ntbl = _table(nw)
ok('H17 「新建日志」行数 = 20 标准 + 2 自定义', ntbl.rowCount() == 22,
   '%d 行' % ntbl.rowCount())
_mcall_row = ntbl.rowCount() and next(
    (r for r in range(ntbl.rowCount()) if ntbl.item(r, 0).text() == '己方呼号'), -1)
ok('H18 呼号大写委托按 key 找到行（不是写死行 2）',
   _mcall_row >= 0 and ntbl.itemDelegateForRow(_mcall_row) is not None, str(_mcall_row))
ok('H19 自定义字段按新顺序排在末尾（接收功率 / 天气）',
   ntbl.item(20, 0).text() == '接收功率' and ntbl.item(21, 0).text() == '天气',
   f'{ntbl.item(20, 0).text()} / {ntbl.item(21, 0).text()}')

# —— H20 必填：勾上后新建日志必须填，留空被拦下 ——
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, '接收功率'), 1).setCheckState(Qt.Checked)
_button(mw, '保存更改').click()
pump(4)
ok('H20 「必填」标记已落盘',
   (fhla_rw.read_project_file(HF)[2].get('field_meta') or {})
   .get('接收功率', {}).get('required') is True,
   str(fhla_rw.read_project_file(HF)[2].get('field_meta')))

api6['new']()
pump(3)
nw = pj.project_others_window
ntbl = _table(nw)
_keys = [e[0] for e in api6['field_entries']()]
_pos = {k: i for i, k in enumerate(_keys)}
ntbl.item(_pos['m_call'], 1).setText('BI8SQL')
ntbl.item(_pos['o_call'], 1).setText('BG9ZZZ')
ntbl.item(_pos['freq'], 1).setText('145.500')
ntbl.item(_pos['mode'], 1).setText('FM')
ntbl.item(_pos['wx'], 1).setText('晴')
ntbl.item(_pos['接收功率'], 1).setText('')     # 必填但留空
warn_cap.clear()
_button(nw, '新建日志').click()
pump(4)
ok('H21 必填的自定义字段留空 → 被拦下',
   '接收功率' in (warn_cap.get('text') or ''), str(warn_cap.get('text')))
ntbl.item(_pos['接收功率'], 1).setText('5W')
warn_cap.clear()
_button(nw, '新建日志').click()
pump(5)
ok('H22 填上后正常新建', warn_cap.get('text') is None, str(warn_cap.get('text')))
new_rec = pj.file[-1]
ok('H23 新日志带上自定义字段值',
   new_rec.get('wx') == '晴' and new_rec.get('接收功率') == '5W',
   str({k: new_rec.get(k) for k in ('wx', '接收功率')}))

# —— H24~H26 「在主页显示」：勾上后主页多一列，取消后回到 14 列 ——
_cols_before = api6['main_table']().columnCount()
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, '接收功率'), 2).setCheckState(Qt.Checked)
_button(mw, '保存更改').click()
pump(5)
_mt = api6['main_table']()
_hdrs = [_mt.horizontalHeaderItem(i).text() for i in range(_mt.columnCount())]
ok('H24 勾选后主页多出「接收功率」列（在「更多」之前）',
   _mt.columnCount() == _cols_before + 1
   and _hdrs[-2] == '接收功率' and _hdrs[-1] == '更多',
   '%d 列：%s' % (_mt.columnCount(), _hdrs[-3:]))
_val_col = _hdrs.index('接收功率')
ok('H25 新列显示记录里的值',
   _mt.item(len(pj.file) - 1, _val_col).text() == '5W',
   _mt.item(len(pj.file) - 1, _val_col).text())

mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, '接收功率'), 2).setCheckState(Qt.Unchecked)
_button(mw, '保存更改').click()
pump(5)
ok('H26 取消勾选后主页回到 14 列', api6['main_table']().columnCount() == _cols_before,
   '%d 列' % api6['main_table']().columnCount())

# —— H26a~H26b 主页列序 =「字段定义」的顺序（即「更多信息」的行序），两处不再各记一套 ——
def _expected_main_headers():
    out = []
    for _k, _lb, _r, _m, _c in api6['field_entries']():
        if not _m:
            continue
        # 主表表头历史上把 prop_mode 叫「传播模式」（录入窗口叫「传播方式」）
        out.append('传播模式' if _k == 'prop_mode' and not _c else _lb)
    return out


_mt = api6['main_table']()
_hdrs = [_mt.horizontalHeaderItem(i).text() for i in range(_mt.columnCount())]
ok('H26a 主页数据列序与字段定义顺序一致', _hdrs[1:-1] == _expected_main_headers(),
   '%s vs %s' % (_hdrs[1:-1], _expected_main_headers()))
ok('H26b 首列仍是「选择」、末列仍是「更多」',
   _hdrs[0] == '选择' and _hdrs[-1] == '更多', str(_hdrs[:1] + _hdrs[-1:]))

# —— H26c 标准字段也能取消「在主页显示」：少一列，勾回来恢复 ——
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, 'o_qth'), 2).setCheckState(Qt.Unchecked)
_button(mw, '保存更改').click()
pump(5)
_mt = api6['main_table']()
_hdrs = [_mt.horizontalHeaderItem(i).text() for i in range(_mt.columnCount())]
ok('H26c 取消标准字段的「在主页显示」→ 主页少一列',
   _mt.columnCount() == _cols_before - 1 and '对方QTH' not in _hdrs,
   '%d 列：%s' % (_mt.columnCount(), _hdrs))
_mH = fhla_rw.read_project_file(HF)[2]
ok('H26d 标准字段的覆盖项已落盘（field_meta 记 main=False）',
   (_mH.get('field_meta') or {}).get('o_qth', {}).get('main') is False,
   str(_mH.get('field_meta')))
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, 'o_qth'), 2).setCheckState(Qt.Checked)
_button(mw, '保存更改').click()
pump(5)
ok('H26e 勾回来 → 恢复 14 列',
   api6['main_table']().columnCount() == _cols_before,
   '%d 列' % api6['main_table']().columnCount())
_mH = fhla_rw.read_project_file(HF)[2]
ok('H26f 改回默认值就不再写覆盖项（文件不堆冗余键）',
   'o_qth' not in (_mH.get('field_meta') or {}), str(_mH.get('field_meta')))

# —— H26g 标准字段也能取消「必填」：校验放行空值，勾回来后恢复 ——
ok('H26g 校验函数按「必填」开关判定（勾着拦、取消放行）',
   fhla_rw.validate_field_text('o_rst', '对方接收信号', '', True) is not None
   and fhla_rw.validate_field_text('o_rst', '对方接收信号', '', False) is None)
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, 'o_rst'), 1).setCheckState(Qt.Unchecked)
_button(mw, '保存更改').click()
pump(5)
_req_now = {e[0]: e[2] for e in api6['field_entries']()}
ok('H26h 取消「必填」后 field_entries 里该项为 False', _req_now.get('o_rst') is False,
   str(_req_now.get('o_rst')))
_mH = fhla_rw.read_project_file(HF)[2]
ok('H26i 落盘为 required=False',
   (_mH.get('field_meta') or {}).get('o_rst', {}).get('required') is False,
   str(_mH.get('field_meta')))
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, 'o_rst'), 1).setCheckState(Qt.Checked)
_button(mw, '保存更改').click()
pump(5)
ok('H26j 勾回必填 → 恢复，且覆盖项被清掉',
   {e[0]: e[2] for e in api6['field_entries']()}['o_rst'] is True
   and 'o_rst' not in (fhla_rw.read_project_file(HF)[2].get('field_meta') or {}),
   str(fhla_rw.read_project_file(HF)[2].get('field_meta')))

# —— H26k 调整顺序后主页列跟着走（自定义列按同一次排序） ——
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, 'wx'), 2).setCheckState(Qt.Checked)          # 天气 上主页
mtbl.item(_row_of(mtbl, '接收功率'), 2).setCheckState(Qt.Checked)     # 接收功率 上主页
_button(mw, '保存更改').click()
pump(5)
_mt = api6['main_table']()
_prev_tail = [_mt.horizontalHeaderItem(i).text() for i in range(_mt.columnCount())][-3:-1]
mw, mtbl = _open_cf()
mtbl.setCurrentCell(_row_of(mtbl, 'wx'), 0)
_button(mw, '上移').click()
_button(mw, '保存更改').click()
pump(5)
_mt = api6['main_table']()
_tail = [_mt.horizontalHeaderItem(i).text() for i in range(_mt.columnCount())][-3:-1]
ok('H26k 上移后主页这两列的顺序也跟着变',
   _prev_tail == ['接收功率', '天气'] and _tail == ['天气', '接收功率'],
   '%s -> %s' % (_prev_tail, _tail))
# 还原：wx 下移一位，两列都取消主页显示
mw, mtbl = _open_cf()
mtbl.setCurrentCell(_row_of(mtbl, 'wx'), 0)
_button(mw, '下移').click()
mtbl.item(_row_of(mtbl, 'wx'), 2).setCheckState(Qt.Unchecked)
mtbl.item(_row_of(mtbl, '接收功率'), 2).setCheckState(Qt.Unchecked)
_button(mw, '保存更改').click()
pump(5)
ok('H26l 还原后主页回到 14 列',
   api6['main_table']().columnCount() == _cols_before,
   '%d 列' % api6['main_table']().columnCount())

# —— H27~H28 「更多信息」：显示自定义值，改后写回；留空则移除该键 ——
idx = len(pj.file) - 1
api6['project_others'](idx)
pump(3)
ow = pj.project_others_window
otbl = _table(ow)
_rx = _pos['接收功率']
ok('H27 「更多信息」显示自定义字段值',
   otbl.rowCount() == 22 and otbl.item(_rx, 0).text() == '接收功率'
   and otbl.item(_rx, 1).text() == '5W',
   otbl.item(_rx, 1).text() if otbl.rowCount() > _rx else '')
otbl.item(_pos['wx'], 1).setText('阴')
_button(ow, '保存更改').click()
pump(4)
ok('H28 改后写回记录', pj.file[idx].get('wx') == '阴', str(pj.file[idx].get('wx')))

# 「必填」会拦住清空（这正是 H21 验证的行为）→ 先在管理窗口把它取消
mw, mtbl = _open_cf()
mtbl.item(_row_of(mtbl, '接收功率'), 1).setCheckState(Qt.Unchecked)
_button(mw, '保存更改').click()
pump(4)

api6['project_others'](idx)
pump(3)
ow = pj.project_others_window
otbl = _table(ow)
otbl.item(_rx, 1).setText('')
_button(ow, '保存更改').click()
pump(4)
ok('H29 自定义字段留空 → 记录里移除该键（不塞空字段）',
   '接收功率' not in pj.file[idx]
   and '接收功率' not in fhla_rw.read_project_file(HF)[0][idx],
   'mem=%s disk=%s' % (pj.file[idx].get('接收功率', '<无>'),
                       fhla_rw.read_project_file(HF)[0][idx].get('接收功率', '<无>')))

# —— H30~H31 英文界面：新窗口的固定文案要翻到，自定义字段名（用户数据）保持原样 ——
_saved_lang = _i18n._lang
try:
    _i18n._lang = _i18n.LANG_EN
    api6['new']()
    pump(3)
    nw = pj.project_others_window
    ntbl = _table(nw)
    ok('H30 英文界面下标准字段名已翻译',
       ntbl.item(_pos['m_call'], 0).text() == _i18n.tr('己方呼号')
       and not any('\u4e00' <= c <= '\u9fff' for c in ntbl.item(_pos['m_call'], 0).text()),
       ntbl.item(_pos['m_call'], 0).text())
    ok('H31 自定义字段名原样显示（用户数据不参与翻译）',
       ntbl.item(_pos['wx'], 0).text() == '天气'
       and ntbl.item(_pos['接收功率'], 0).text() == '接收功率',
       f"{ntbl.item(_pos['wx'], 0).text()} / {ntbl.item(_pos['接收功率'], 0).text()}")
    api6['manage_custom_fields']()
    pump(3)
    mw = api6['custom_fields_window']()
    # 真应用里由 i18n.install(app) 的 Show 事件过滤器自动翻一遍；本脚本没装过滤器，
    # 就显式调一次（同一个函数），断言的是「窗口文案确实可被翻译」。
    _i18n.translate_tree(mw)
    pump(2)
    btns = {b.text() for b in mw.findChildren(QPushButton)}
    ok('H32 管理窗口按钮已翻译（无中文残留）',
       btns == {'Add field', 'Delete selected', 'Move up', 'Move down',
                'Restore defaults', 'Save changes', 'Close'}, str(sorted(btns)))
    ok('H33 管理窗口表头已翻译',
       [ _table(mw).horizontalHeaderItem(i).text() for i in range(3)]
       == ['Field name', 'Required', 'Show on main page'],
       str([_table(mw).horizontalHeaderItem(i).text() for i in range(3)]))
    mw.close()
    pump(1)
finally:
    _i18n._lang = _saved_lang

# —— H34~H40 「恢复默认」：表格回出厂 → 不落盘 → 保存后文件干净 ——
mw, mtbl = _open_cf()
ok('H34 管理窗口有「恢复默认」按钮', _button(mw, '恢复默认') is not None)
ok('H35 恢复前表格里有自定义字段（前提成立）', mtbl.rowCount() == 22,
   '%d 行' % mtbl.rowCount())
_meta_before = fhla_rw.read_project_file(HF)[2]
_button(mw, '恢复默认').click()
pump(2)
ok('H36 点后表格立刻回出厂：20 行、无自定义字段',
   mtbl.rowCount() == 20
   and all(mtbl.item(r, 0).data(Qt.UserRole) in fhla_rw.FIELD_LABELS
           for r in range(mtbl.rowCount())),
   '%d 行' % mtbl.rowCount())
ok('H37 顺序 / 必填 / 主页显示都回到历史默认',
   [mtbl.item(r, 0).data(Qt.UserRole) for r in range(mtbl.rowCount())]
   == fhla_rw.standard_field_keys()
   and mtbl.item(_row_of(mtbl, 'm_call'), 1).checkState() == Qt.Checked
   and mtbl.item(_row_of(mtbl, 'notes'), 1).checkState() == Qt.Unchecked
   and mtbl.item(_row_of(mtbl, 'notes'), 2).checkState() == Qt.Unchecked
   and mtbl.item(_row_of(mtbl, 'mode'), 2).checkState() == Qt.Checked)
ok('H38 只重置表格、没写盘（文件里自定义字段还在）',
   fhla_rw.read_project_file(HF)[2]['other_item'] == _meta_before['other_item'],
   str(fhla_rw.read_project_file(HF)[2]['other_item']))
_button(mw, '保存更改').click()
pump(5)
_meta_reset = fhla_rw.read_project_file(HF)[2]
ok('H39 保存后字段定义回到出厂（other_item 空、field_order / field_meta 都不写）',
   _meta_reset.get('other_item') == {} and 'field_order' not in _meta_reset
   and 'field_meta' not in _meta_reset,
   str({k: _meta_reset.get(k) for k in ('other_item', 'field_order', 'field_meta')}))
ok('H40 主页表格回到 14 列（自定义列全部撤掉）',
   api6['main_table']().columnCount() == _cols_before,
   '%d 列' % api6['main_table']().columnCount())

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
   m.load_quick_project_data(_missing_main) == ([], None, None), _missing_main)
_existing_main = os.path.join(G_TMP, 'has_main.fhl')
fhla_rw.save_project_file(_existing_main, _recs(2, 'G'))
ok('G2 有 main.fhl 时照常读回记录',
   len(m.load_quick_project_data(_existing_main)[0]) == 2
   and m.load_quick_project_data(_existing_main)[2] is None)

# G2b 默认日志路径：有 main.fhla 时优先它（迁移会删掉 main.fhl，下次启动必须能找到新文件）
_real_app_path_m = m.app_path
m.app_path = lambda rel: os.path.join(G_TMP, rel)
try:
    os.makedirs(os.path.join(G_TMP, 'file'), exist_ok=True)
    _q_fhl = os.path.join(G_TMP, 'file', 'main.fhl')
    _q_fhla = os.path.join(G_TMP, 'file', 'main.fhla')
    for _q in (_q_fhl, _q_fhla):
        if os.path.exists(_q):
            os.remove(_q)
    ok('G2b 两者都不存在时默认给 .fhla（全新安装走新格式）',
       os.path.normcase(m.default_quick_project_path()) == os.path.normcase(_q_fhla),
       m.default_quick_project_path())
    fhla_rw.save_project_file(_q_fhl, _recs(1, 'Q'))
    ok('G2c 只有 main.fhl 时用 main.fhl',
       os.path.normcase(m.default_quick_project_path()) == os.path.normcase(_q_fhl),
       m.default_quick_project_path())
    fhla_rw.save_project_file(_q_fhla, _recs(2, 'Q'))
    ok('G2d 存在 main.fhla 时优先 main.fhla',
       os.path.normcase(m.default_quick_project_path()) == os.path.normcase(_q_fhla),
       m.default_quick_project_path())
finally:
    m.app_path = _real_app_path_m

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

# ==========================================================================
# I. 打开 .fhl 时的迁移提示（每次都问；迁移 = 另存同名 .fhla，原件保留）
# ==========================================================================
print('--- I .fhl → .fhla 迁移 ---', flush=True)

_p = fhla_rw.fhla_sibling_path(os.path.join(TMP, 'x.FHL'))
ok('I1 同名 .fhla 路径推导（大小写不敏感）',
   os.path.normcase(_p) == os.path.normcase(os.path.join(TMP, 'x.fhla')), _p)
ok('I2 传入的已是 .fhla 则原样返回',
   fhla_rw.fhla_sibling_path(FHLA) == FHLA)

MIG = os.path.join(TMP, 'mig.fhl')
fhla_rw.save_project_file(MIG, _recs(3, 'I'), editor='BD0AAA')
_orig_bytes = open(MIG, 'rb').read()
TGT = fhla_rw.fhla_sibling_path(MIG)
_orig_ask = pj.ask_migrate_fhl

# —— I3/I4 选「暂不迁移」：路径不变、不生成 .fhla、原文件不动 ——
pj.ask_migrate_fhl = lambda parent=None, file_path='': False
try:
    p_keep, meta_keep = pj.offer_migration(None, MIG, fhla_rw.read_project_file(MIG)[0])
finally:
    pj.ask_migrate_fhl = _orig_ask
ok('I3 选「暂不迁移」→ 仍打开原 .fhl，且不生成 .fhla',
   p_keep == MIG and meta_keep is None and not os.path.exists(TGT), p_keep)
ok('I4 原 .fhl 字节一个都没变', open(MIG, 'rb').read() == _orig_bytes)

# —— I5~I9 选「迁移」：打开同名 .fhla、属性就位、记录完整、**原 .fhl 被删除** ——
recs_i, key_i, meta_i = fhla_rw.read_project_file(MIG)
pj.ask_migrate_fhl = lambda parent=None, file_path='': True
try:
    p_new, meta_new = pj.offer_migration(None, MIG, recs_i, key=key_i, meta=meta_i)
finally:
    pj.ask_migrate_fhl = _orig_ask
ok('I5 迁移后返回同名 .fhla 且文件已落盘',
   p_new == TGT and os.path.exists(TGT), p_new)
recs_t, key_t, meta_t = fhla_rw.read_project_file(TGT)
_who = pj.current_editor()          # 迁移时的操作者（.fhl 里没有创建者，从迁移这一刻开始记）
ok('I6 记录一条不少（顺序也一致）',
   [r['time'] for r in recs_t] == [r['time'] for r in recs_i] and len(recs_t) == 3,
   '%d 条' % len(recs_t))
ok('I7 属性块就位（创建者 / 创建时间 / 版本 / 加密状态）',
   meta_t['creator'] == _who and bool(meta_t['created_time'])
   and meta_t['last_version'] == fhla_rw.current_version()
   and meta_t['encrypted'] is False, str(meta_t))
ok('I8 迁移成功后原 .fhl 已被删除（自动删源文件）', not os.path.exists(MIG))
ok('I9 新属性块一并返回给打开流程',
   isinstance(meta_new, dict) and meta_new.get('creator') == _who, str(meta_new))

# —— I10 已是 .fhla 就不再问（一次都不能弹）——
def _boom_ask(*a, **k):
    raise AssertionError('打开 .fhla 不该问迁移')


pj.ask_migrate_fhl = _boom_ask
try:
    p_same, meta_same = pj.offer_migration(None, TGT, recs_t)
    _asked = False
except AssertionError:
    _asked = True
finally:
    pj.ask_migrate_fhl = _orig_ask
ok('I10 打开 .fhla 时不提示迁移', (not _asked) and p_same == TGT and meta_same is None)

# —— I11 加密的 .fhl 迁移后仍是加密的 .fhla（同一密钥可读回）——
MIG_ENC = os.path.join(TMP, 'mig_enc.fhl')
fhla_rw.save_project_file(MIG_ENC, _recs(2, 'IE'), key='pwd456', editor='BD0AAA')
# 注意必须显式给 key：加密文件不给密钥会弹「输入加密密钥」模态框，离屏下直接挂住
recs_e, key_e, _me = fhla_rw.read_project_file(MIG_ENC, key='pwd456')
pj.ask_migrate_fhl = lambda parent=None, file_path='': True
try:
    p_enc, _menc = pj.offer_migration(None, MIG_ENC, recs_e, key=key_e, meta=_me)
finally:
    pj.ask_migrate_fhl = _orig_ask
ok('I11 加密 .fhl 迁移后仍是密文，且用同一密钥能读回',
   fhla_rw.detect_encrypted(p_enc) is True
   and len(fhla_rw.read_project_file(p_enc, key='pwd456')[0] or []) == 2,
   p_enc)

# —— I12 真对话框：两个按钮 + 点「迁移」返回 True（不弹真模态）——
_orig_exec = QMessageBox.exec


def _fake_exec_box(self):
    """模拟用户点按钮：默认点「迁移」；文本里同时断言两个按钮都在。"""
    labels = [b.text() for b in self.buttons()]
    _fake_exec_box.labels = labels
    target = '迁移' if '迁移' in labels else (_i18n.tr('迁移') if _i18n.tr('迁移') in labels else None)
    for b in self.buttons():
        if b.text() == target:
            b.click()
            return 0
    return 0


QMessageBox.exec = _fake_exec_box
try:
    _choice = pj.ask_migrate_fhl(None, MIG)
finally:
    QMessageBox.exec = _orig_exec
ok('I12 迁移对话框有「迁移 / 暂不迁移」两个按钮',
   set(getattr(_fake_exec_box, 'labels', [])) == {'迁移', '暂不迁移'},
   str(getattr(_fake_exec_box, 'labels', [])))
ok('I13 点「迁移」→ ask_migrate_fhl 返回 True', _choice is True)

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)
_cleanup()
atexit.unregister(_cleanup)
sys.exit(0 if all(PASS) else 1)
