# -*- coding: utf-8 -*-
"""校验插件接口对 .fhla 的支持：双输入（input.fhl / input.fhla）+ 双输出（.fhla 优先）。

覆盖点：
  P1 插件目录里同时有 input.fhl 与 input.fhla；input.fhla 与 .fhla 同构、encrypted=false、
     记录数一致（加密项目也照样给明文）
  P2 同时产出 output.fhl 与 output.fhla 时**优先 .fhla**（记录与属性块一起生效，
     自定义字段定义写回项目并出现在主表列里）
  P3 只有 output.fhl 时只替换记录，属性块保持原样（老插件行为不变）
  P4 只有 output.fhla 时同样生效
  P5 output.fhla 坏掉时不回退到 output.fhl（不静默丢属性改动），内容保持原样
  P6 把 {"xml":…, "project":…} 写进 output.fhl（结构错）→ 报「不是记录列表」，内容不变
  P7 运行结束后 input.* / output.* 全被清理；上一轮残留的 output 不会干扰本轮

离屏运行；数据目录与备份路径都重定向到临时目录，不碰 file/ 里的用户数据。
用法：python tests/__pack_fhla_smoke.py
"""
import json
import os
import shutil
import sys
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtWidgets import QTableWidget

from f_hamlog import backup
from f_hamlog import project as pj

TMP = tempfile.mkdtemp(prefix='fhl_pack_fhla_smoke_')
backup.PROJECT_BACKUP = os.path.join(TMP, 'project_backup.fhl')

DATA = os.path.join(TMP, 'data')          # 模拟数据目录（app_path 的根）
PACK = os.path.join(DATA, 'file', 'pypack', 'pk')
os.makedirs(PACK, exist_ok=True)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def pump(n=5):
    for _ in range(n):
        app.processEvents()


def recs(n=3):
    return [{
        'date': '2026-10-24', 'time': '20:0%d' % i, 'm_call': 'BI8SQL',
        'o_call': 'BG5ABC%d' % i, 'freq': '144.100', 'freq_rx': '145.100',
        'mode': 'FM', 'prop_mode': 'SAT', 'sat_name': 'SO-50',
        'm_rst': '59', 'o_rst': '59', 'm_qth': '杭州', 'o_qth': '北京',
        'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
        'notes': 'base%d' % i, 'wx': '晴',
    } for i in range(n)]


# 插件脚本：按 mode 产出不同的输出文件；同时把读到的输入整理成 probe.json 供断言
PLUGIN_TPL = r'''
import json, os

d = os.path.dirname(os.path.abspath(__file__))
mode = %(mode)r

def dump(name, obj):
    with open(os.path.join(d, name), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def raw(name, text):
    with open(os.path.join(d, name), 'w', encoding='utf-8') as f:
        f.write(text)

probe = {}
with open(os.path.join(d, 'input.fhl'), encoding='utf-8') as f:
    probe['fhl_type'] = type(json.load(f)).__name__
with open(os.path.join(d, 'input.fhla'), encoding='utf-8') as f:
    full = json.load(f)
probe['fhla_keys'] = sorted(full.keys())
probe['fhla_encrypted'] = full['xml'].get('encrypted')
probe['fhla_other_item'] = full['xml'].get('other_item')
probe['fhla_records'] = len(full['project'])
probe['inputs'] = sorted(n for n in os.listdir(d) if n.startswith('input.'))
dump('probe.json', probe)

recs = [dict(r) for r in full['project']]

if mode in ('both', 'fhl_only'):
    r1 = [dict(r) for r in recs]
    r1[0]['notes'] = 'from_fhl'
    dump('output.fhl', r1)

if mode in ('both', 'fhla_only'):
    full['project'][0]['notes'] = 'from_fhla'
    full['xml']['other_item'] = {'wx': '天气', 'my_field': '我的字段'}
    order = [k for k in (full['xml'].get('field_order') or []) if k != 'my_field']
    full['xml']['field_order'] = order + ['my_field']
    full['xml']['field_meta'] = {'my_field': {'required': False, 'main': True}}
    dump('output.fhla', full)

if mode == 'drop_field':
    full['project'][0]['notes'] = 'drop_field'
    full['xml']['other_item'] = {'wx': '天气'}
    full['xml'].pop('field_order', None)
    full['xml'].pop('field_meta', None)
    dump('output.fhla', full)

if mode == 'no_project':
    # 结构缺 project：必须报错，不能被当成「空项目」把整份日志清空
    raw('output.fhla', '{"xml": {}}')
    dump('output.fhl', [{'notes': 'should_not_be_used'}])

if mode == 'bad_fhla':
    raw('output.fhla', '{ this is not json')

if mode == 'dict_fhl':
    dump('output.fhl', {'xml': {}, 'project': recs})
'''


def write_plugin(mode):
    with open(os.path.join(PACK, 'main.py'), 'w', encoding='utf-8') as f:
        f.write(PLUGIN_TPL % {'mode': mode})


def probe():
    with open(os.path.join(PACK, 'probe.json'), encoding='utf-8') as f:
        return json.load(f)


def leftover():
    return sorted(n for n in os.listdir(PACK)
                  if n.startswith('input.') or n.startswith('output.'))


# ---------------- 环境替身：子进程 / 消息框 / 数据目录 ----------------
import subprocess as _sp
import types


class _Sub:
    """用当前解释器跑插件（源码里写的是 'python'，测试里不该依赖 PATH）。"""

    @staticmethod
    def run(args, **kw):
        return _sp.run([sys.executable] + list(args[1:]), **kw)


class _Box:
    warnings = []
    infos = []

    @staticmethod
    def warning(parent, title, text, *a, **k):
        _Box.warnings.append(text)
        return 0

    @staticmethod
    def information(*a, **k):
        _Box.infos.append(a)
        return 0

    @staticmethod
    def question(*a, **k):
        return 0


_orig = {'app_path': pj.app_path, 'subprocess': pj.subprocess, 'QMessageBox': pj.QMessageBox}
pj.app_path = lambda rel: os.path.join(DATA, rel)
pj.subprocess = types.SimpleNamespace(run=_Sub.run)
pj.QMessageBox = _Box

with open(os.path.join(DATA, 'file', 'pack_list.txt'), 'w', encoding='utf-8') as f:
    f.write(str(['pk']))
# 主窗读设置（list_time / save / 操作者呼号）用的键很多，从真实设置复制一份再改；
# 自动排序关掉，避免改变记录顺序影响断言
_cfg_src = os.path.join(PROJECT_DIR, 'src', 'f_hamlog', 'file', 'm_xml.txt')
try:
    with open(_cfg_src, 'r', encoding='utf-8-sig') as f:
        _cfg = eval(f.read())
except Exception:
    _cfg = {'aouto_save': True, 'm_call': 'BI8SQL'}
_cfg['aouto_list'] = False
with open(os.path.join(DATA, 'file', 'm_xml.txt'), 'w', encoding='utf-8') as f:
    f.write(str(_cfg))

# ---------------- 打开一个 .fhla 项目 ----------------
SAVE = os.path.join(TMP, 'proj.fhla')
meta0 = pj.empty_meta()
meta0['other_item'] = {'wx': '天气'}
base = recs(3)
pj.write_fhla_file(SAVE, base, meta=meta0, editor='BI8SQL')

win = QtWidgets.QMainWindow()
try:
    pj.main(win, filee=base, save_path=SAVE, fhla_meta=meta0)
    pump(6)


    def find_action():
        for m in win.menuBar().actions():
            menu = m.menu()
            if menu is None:
                continue
            for a in menu.actions():
                if a.text() == 'pk':
                    return a
        return None


    def run(mode):
        write_plugin(mode)
        _Box.warnings = []
        act = find_action()
        assert act is not None, '插件菜单里没有找到 pk'
        act.trigger()
        pump(8)


    def notes0():
        return pj.file[0].get('notes') if pj.file else None


    def saved_meta():
        _r, _k, mm = pj.read_project_file(SAVE)
        return mm


    def header_texts():
        # 重建后旧表只是 deleteLater（processEvents 不处理 DeferredDelete），
        # win.findChild 可能拿到旧表；以布局里当前挂着的那个为准。
        cw = win.centralWidget()
        lay = cw.layout() if cw is not None else None
        tables = []
        if lay is not None:
            for i in range(lay.count()):
                w = lay.itemAt(i).widget()
                if isinstance(w, QTableWidget):
                    tables.append(w)
        table = tables[-1] if tables else win.findChild(QTableWidget)
        head = table.horizontalHeaderItem
        return [head(i).text() for i in range(table.columnCount())] if table else []


    # ---- P1 + P2：双输入、双输出，.fhla 优先 ----
    run('both')
    pr = probe()
    ok('P1a 插件目录里同时有 input.fhl 与 input.fhla',
       pr['inputs'] == ['input.fhl', 'input.fhla'], str(pr['inputs']))
    ok('P1b input.fhl 是记录列表', pr['fhl_type'] == 'list', pr['fhl_type'])
    ok('P1c input.fhla 结构与磁盘 .fhla 一致（xml + project）、记录数一致、encrypted=false',
       pr['fhla_keys'] == ['project', 'xml'] and pr['fhla_records'] == 3
       and pr['fhla_encrypted'] is False, str(pr))
    ok('P1d input.fhla 带着项目属性（自定义字段 other_item）',
       pr['fhla_other_item'] == {'wx': '天气'}, str(pr['fhla_other_item']))
    ok('P2a 同时有 output.fhl / output.fhla 时优先 .fhla',
       notes0() == 'from_fhla', str(notes0()))
    m = saved_meta() or {}
    ok('P2b output.fhla 的属性块写回项目（自定义字段定义生效）',
       (m.get('other_item') or {}).get('my_field') == '我的字段', str(m.get('other_item')))
    ok('P2c 新自定义字段作为一列出现在主表', '我的字段' in header_texts(), str(header_texts()))
    ok('P2d 运行结束后 input.* / output.* 都被清理', leftover() == [], str(leftover()))

    # ---- P3：只有 output.fhl → 只换记录，属性块不动 ----
    run('fhl_only')
    ok('P3a 只有 output.fhl 时记录被替换', notes0() == 'from_fhl', str(notes0()))
    m = saved_meta() or {}
    ok('P3b 属性块保持原样（老插件不碰属性）',
       (m.get('other_item') or {}).get('my_field') == '我的字段', str(m.get('other_item')))
    ok('P3c 输入仍含 input.fhla', probe()['inputs'] == ['input.fhl', 'input.fhla'])

    # ---- P4：只有 output.fhla ----
    run('fhla_only')
    ok('P4 只有 output.fhla 时记录与属性一起生效',
       notes0() == 'from_fhla' and '我的字段' in header_texts(), str(notes0()))

    # ---- P4b：属性块是整体替换，不是合并 ----
    run('drop_field')
    ok('P4b 插件删掉的自定义字段真的消失（属性块整体替换）',
       '我的字段' not in header_texts() and notes0() == 'drop_field',
       str(header_texts()))

    # ---- P5b：output.fhla 缺 project → 报错，不清空项目、不回退 ----
    before = notes0()
    run('no_project')
    ok('P5a output.fhla 缺 project 时报错，项目不被清空（也不回退 output.fhl）',
       notes0() == before and len(pj.file) == 3
       and any('output.fhla' in w for w in _Box.warnings), str(_Box.warnings))

    # ---- P5：output.fhla 坏掉 → 不回退 output.fhl ----
    before = notes0()
    run('bad_fhla')
    ok('P5b output.fhla 无法解析时报警（不回退 output.fhl）',
       notes0() == before and any('output.fhla' in w for w in _Box.warnings),
       str(_Box.warnings))
    ok('P5c 失败后临时文件仍被清理', leftover() == [], str(leftover()))

    # ---- P6：output.fhl 里写了 .fhla 结构 ----
    before = notes0()
    run('dict_fhl')
    ok('P6 output.fhl 不是记录列表时报错且内容不变',
       notes0() == before and any('不是记录列表' in w for w in _Box.warnings),
       str(_Box.warnings))

    # ---- P7：上一轮残留的 output 不应被当成本轮结果 ----
    with open(os.path.join(PACK, 'output.fhla'), 'w', encoding='utf-8') as f:
        json.dump({'xml': {}, 'project': [{'notes': 'stale'}]}, f, ensure_ascii=False)
    run('nothing')
    ok('P7 残留的旧 output 不会被误当成本次结果',
       notes0() == before and any('未正确生成输出文件' in w for w in _Box.warnings),
       str(_Box.warnings))

    # ---- 加密项目：input.fhla 仍是明文 ----
    ENC = os.path.join(TMP, 'enc.fhla')
    pj.write_fhla_file(ENC, recs(2), meta=pj.empty_meta(), key='pwd', editor='BI8SQL')
    win2 = QtWidgets.QMainWindow()
    try:
        _r, _k, mm = pj.read_project_file(ENC, key='pwd')
        pj.main(win2, filee=_r, save_path=ENC, key_='pwd', fhla_meta=mm)
        pump(6)
        write_plugin('both')
        acts = [a for m in win2.menuBar().actions() if m.menu() is not None
                for a in m.menu().actions() if a.text() == 'pk']
        if acts:
            acts[0].trigger()
            pump(8)
        pr = probe()
        ok('P8 加密项目的 input.fhla 也是明文（encrypted=false）',
           pr['fhla_encrypted'] is False and pr['fhla_records'] == 2, str(pr))
        ok('P8b 插件改完仍按加密落盘（内存 encrypted 不被明文读回覆盖）',
           pj.detect_encrypted(ENC) is True, ENC)
    finally:
        # 不用 close()：关闭守卫会按「未保存更改」弹真模态框（离屏下会挂住），
        # 本测试只关心插件接口，隐藏即可。
        win2.hide()
        pump(3)
finally:
    win.hide()
    pump(3)
    pj.app_path = _orig['app_path']
    pj.subprocess = _orig['subprocess']
    pj.QMessageBox = _orig['QMessageBox']

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if all(PASS) else 1)
