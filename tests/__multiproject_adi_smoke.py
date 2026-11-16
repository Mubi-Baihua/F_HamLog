# -*- coding: utf-8 -*-
"""多项目并存 / 批量记录「自动保存到日志文件」/ 直接打开 .adi —— 离屏冒烟。

覆盖点：
  M 多项目：两个项目窗口各持一份记录列表，互不覆盖（旧版模块全局 file/key 会让
            后打开的窗口把前一个窗口的数据顶掉 → 不同日志串在一起）
  B 批量记录：从项目窗口启动默认勾选「自动保存到日志文件」并写回**启动它的那个日志**；
            从主页启动默认不勾选，手动勾上后走「完成」页选择保存到的日志
  D .adi：直接打开 / 编辑 / 保存（读走 input_adi 的解析，写走 export_adi 的生成）

离屏运行；项目 / 批量备份路径重定向到临时目录，不触碰 file/ 里的用户数据。
用法：python tests/__multiproject_adi_smoke.py
"""
import os
import sys
import shutil
import tempfile
import atexit

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem)

from f_hamlog import backup
from f_hamlog import project
from f_hamlog import batch_project
from f_hamlog import export_adi

TMP = tempfile.mkdtemp(prefix='fhl_mp_adi_smoke_')


def _cleanup():
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# 备份重定向：所有备份（含按项目分开的）都落在临时目录里
backup.PROJECT_BACKUP = os.path.join(TMP, 'project_backup.fhl')
backup.BATCH_BACKUP = os.path.join(TMP, 'batch_backup.fhl')

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def pump(n=5):
    for _ in range(n):
        app.processEvents()


# ---- 模态弹窗全部静默（离屏不能真的弹） ----
POPUPS = []
_real_info = QMessageBox.information
_real_warn = QMessageBox.warning


def _fake_info(parent=None, title='', text='', *a, **k):
    POPUPS.append(('info', title, text))
    return QMessageBox.Ok


def _fake_warn(parent=None, title='', text='', *a, **k):
    POPUPS.append(('warn', title, text))
    return QMessageBox.Ok


QMessageBox.information = _fake_info
QMessageBox.warning = _fake_warn
QMessageBox.question = lambda *a, **k: QMessageBox.No

# 「完成」页是 QDialog.exec()：只记录里面出现了哪些文字，然后当作「取消」返回
DIALOG_TEXTS = []
_real_exec = QDialog.exec


def _fake_exec(self):
    for lb in self.findChildren(QtWidgets.QLabel):
        DIALOG_TEXTS.append(lb.text())
    for rb in self.findChildren(QtWidgets.QRadioButton):
        DIALOG_TEXTS.append('OPT:' + rb.text())
    DIALOG_TEXTS.append('BTN:' + '|'.join(b.text() for b in self.findChildren(QPushButton)))
    return QDialog.Rejected


QDialog.exec = _fake_exec


def _button(widget, text):
    from f_hamlog import i18n as _i18n
    wanted = {text, _i18n.tr(text)}
    return next((b for b in widget.findChildren(QPushButton) if b.text() in wanted), None)


def _rec(o_call, date='2026-11-15', time='20:00', notes=''):
    return {
        'date': date, 'time': time, 'm_call': 'BI8SQL', 'o_call': o_call,
        'freq': '144.100', 'freq_rx': '', 'mode': 'FM', 'prop_mode': '',
        'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
        'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
        'notes': notes,
    }


def _calls(records):
    return [r.get('o_call') for r in (records or [])]


def _read(path):
    data, _k, _m = project.read_project_file(path)
    return data or []


def _fill_log_col(tbl, keys, vals):
    """在表格末尾插一条日志列并填入给定字段（等价于 Ctrl+N 后逐格输入）。"""
    col = tbl.columnCount()
    tbl.insertColumn(col)
    for r, k in enumerate(keys):
        tbl.setItem(r, col, QTableWidgetItem(vals.get(k, '')))
    return col


# ==========================================================================
# M. 多项目并存：各窗口的数据互不覆盖
# ==========================================================================
print('--- M 多项目并存 ---', flush=True)
A = os.path.join(TMP, 'a.fhla')
B = os.path.join(TMP, 'b.fhla')
recs_a = [_rec('BG1A1'), _rec('BG1A2')]
recs_b = [_rec('BG2B1'), _rec('BG2B2'), _rec('BG2B3')]
project.save_project_file(A, recs_a)
project.save_project_file(B, recs_b)

win_a = QtWidgets.QMainWindow()
project.main(win_a, recs_a, A)
pump()
win_b = QtWidgets.QMainWindow()
project.main(win_b, recs_b, B)
pump()

api_a = win_a._perf_api
api_b = win_b._perf_api
ok('M0 打开第二个项目后第一个窗口仍然存活', bool(win_a.windowTitle()), win_a.windowTitle())
ok('M1 两个窗口各持一份记录列表（不是同一个 list）',
   api_a['get_file']() is not api_b['get_file']())
ok('M2 A 窗口内容仍是 A 的', _calls(api_a['get_file']()) == ['BG1A1', 'BG1A2'],
   str(_calls(api_a['get_file']())))
ok('M3 B 窗口内容仍是 B 的', _calls(api_b['get_file']()) == ['BG2B1', 'BG2B2', 'BG2B3'],
   str(_calls(api_b['get_file']())))
ok('M4 模块级 file 只是镜像（不再是两个窗口共用的那一份）',
   project.file is api_b['get_file'](),
   'mirror=%s' % (id(project.file),))

# 在 A 里追加一条：只能进 A
api_a['append_to_project']([_rec('BG1A3')])
pump(3)
ok('M5 追加只进 A 的内存', _calls(api_a['get_file']()) == ['BG1A1', 'BG1A2', 'BG1A3'],
   str(_calls(api_a['get_file']())))
ok('M6 B 的内存没被污染',
   _calls(api_b['get_file']()) == ['BG2B1', 'BG2B2', 'BG2B3'],
   str(_calls(api_b['get_file']())))
ok('M7 A 文件已落盘 3 条', _calls(_read(A)) == ['BG1A1', 'BG1A2', 'BG1A3'],
   str(_calls(_read(A))))
ok('M8 B 文件一条都没变', _calls(_read(B)) == ['BG2B1', 'BG2B2', 'BG2B3'],
   str(_calls(_read(B))))

# 同一个文件被两个窗口打开（主页点两次「通联日志」就会这样）：一个窗口写盘后，
# 另一个窗口的内存必须跟上；否则它下一次自动保存会拿旧内容把新记录整份覆盖，
# 表现成「批量记录的自动保存没生效」。
S = os.path.join(TMP, 'same.fhla')
project.save_project_file(S, [_rec('BG5S1')])
win_s1 = QtWidgets.QMainWindow()
project.main(win_s1, [_rec('BG5S1')], S)
pump()
win_s2 = QtWidgets.QMainWindow()
project.main(win_s2, [_rec('BG5S1')], S)
pump()
api_s1 = win_s1._perf_api
api_s2 = win_s2._perf_api
api_s1['append_to_project']([_rec('BG5S2')])
pump(3)
ok('M9 同一文件的两个窗口：一个追加后，另一个的内存自动跟上',
   _calls(api_s2['get_file']()) == ['BG5S1', 'BG5S2'],
   str(_calls(api_s2['get_file']())))
api_s2['save']()
pump(3)
ok('M10 另一个窗口的保存不会把刚追加的记录覆盖掉',
   _calls(_read(S)) == ['BG5S1', 'BG5S2'], str(_calls(_read(S))))

# 磁盘被外部（别的进程 / 编辑器）改过、本窗口没动过内容 → 静默保存应改读磁盘
project.save_project_file(S, [_rec('BG5S1'), _rec('BG5S3')])
api_s2['table_update']()
pump(3)
ok('M11 磁盘被外部改过时，静默保存以磁盘为准（不写回旧内容）',
   _calls(_read(S)) == ['BG5S1', 'BG5S3']
   and _calls(api_s2['get_file']()) == ['BG5S1', 'BG5S3'],
   'disk=%s mem=%s' % (_calls(_read(S)), _calls(api_s2['get_file']())))

# 另一个窗口正在编辑（内存有未保存改动）时，别人的写入不能把它吞掉
api_s2['get_file']().append(_rec('BG9EDIT'))
api_s1['append_to_project']([_rec('BG5S4')])
pump(3)
ok('M12 有未保存改动的窗口不会被别人的写入整份重载（编辑不丢）',
   'BG9EDIT' in _calls(api_s2['get_file']())
   and 'BG9EDIT' not in _calls(_read(S)),
   'mem=%s disk=%s' % (_calls(api_s2['get_file']()), _calls(_read(S))))

# ==========================================================================
# B. 批量记录：自动保存到「启动它的那个日志」
# ==========================================================================
print('--- B 批量记录自动保存 ---', flush=True)
# 从 A 窗口启动（模拟卫星「记录」/ 菜单「批量记录」），此时 B 窗口已经开着
bw = QtWidgets.QMainWindow()
batch_project.main(bw, preset=None, on_saved=api_a['append_to_project'],
                   auto_target=os.path.basename(A))
pump(3)

cbs = [c for c in bw.findChildren(QCheckBox)
       if c.text().startswith('自动保存到日志文件')]
ok('B1 批量记录里有「自动保存到日志文件」复选框', len(cbs) == 1,
   str([c.text() for c in bw.findChildren(QCheckBox)]))
ok('B2 从项目窗口启动 → 默认勾选', len(cbs) == 1 and cbs[0].isChecked())
ok('B3 复选框上显示目标日志名', len(cbs) == 1 and os.path.basename(A) in cbs[0].text(),
   cbs[0].text() if cbs else '')

tbl = bw.findChild(QTableWidget)
_fill_log_col(tbl, batch_project.KEYS,
              {'date': '2026-11-15', 'time': '21:00', 'm_call': 'BI8SQL',
               'o_call': 'BG9ZZZ', 'freq': '144.100', 'mode': 'FM',
               'm_rst': '59', 'o_rst': '59'})
POPUPS.clear()
btn_done = _button(bw, '完成 (Ctrl+S)')
ok('B4 有「完成」按钮', btn_done is not None)
btn_done.click()
pump(5)
ok('B5 自动写回 A（启动它的那个日志）', _calls(_read(A)) == ['BG1A1', 'BG1A2', 'BG1A3', 'BG9ZZZ'],
   str(_calls(_read(A))))
ok('B6 没有串到后打开的 B', _calls(_read(B)) == ['BG2B1', 'BG2B2', 'BG2B3'],
   str(_calls(_read(B))))
ok('B7 提示文案是「已添加 1 条记录到当前项目。」',
   any('已添加 1 条记录到当前项目' in t for _k, _ti, t in POPUPS),
   str([t for _k, _ti, t in POPUPS]))
ok('B8 没有弹「完成」页（不让人再选一次）', not DIALOG_TEXTS, str(DIALOG_TEXTS))

# 从主页启动：没有「当前日志」→ 默认不勾选；勾上就立刻问「存到哪个日志」，
# 选好之后点「完成」直接写过去，不再问第二次。
bw2 = QtWidgets.QMainWindow()
batch_project.main(bw2)
pump(3)
cbs2 = [c for c in bw2.findChildren(QCheckBox)
        if c.text().startswith('自动保存到日志文件')]
ok('B9 从主页启动默认不勾选', len(cbs2) == 1 and not cbs2[0].isChecked())
ok('B10 主页启动时复选框不带日志名',
   len(cbs2) == 1 and cbs2[0].text() == '自动保存到日志文件',
   cbs2[0].text() if cbs2 else '')

# 勾上 → 立刻弹选择页；在页上取消 → 勾自动去掉（不能留下「勾着却没有目标」的状态）
DIALOG_TEXTS.clear()
cbs2[0].setChecked(True)
pump(3)
ok('B11 勾选时立刻弹出「保存到哪里」选择页',
   any('已录入的记录要保存到哪里？' in t for t in DIALOG_TEXTS), str(DIALOG_TEXTS[:2]))
ok('B12 选择页给出四个去处（都叫「日志文件」，不出现 F HamLog 项目）',
   all(any(k in t for t in DIALOG_TEXTS) for k in
       ('OPT:添加到日志文件', 'OPT:另存为日志文件',
        'OPT:添加到默认通联日志', 'OPT:添加到多人日志'))
   and not any('F HamLog 项目' in t for t in DIALOG_TEXTS),
   str(DIALOG_TEXTS))
ok('B12b 选择页没有灰色说明文字（只有标题一个 QLabel）',
   len([t for t in DIALOG_TEXTS if not t.startswith(('OPT:', 'BTN:'))]) == 1,
   str(DIALOG_TEXTS))
ok('B13 取消选择 → 复选框回到未勾选',
   not cbs2[0].isChecked() and cbs2[0].text() == '自动保存到日志文件', cbs2[0].text())

# 选「默认通联日志」（目标文件用临时目录，别碰真实 main.fhla）
HOME_LOG = os.path.join(TMP, 'home_log.fhla')
_real_choose = batch_project.choose_save_target
batch_project.choose_save_target = lambda parent, heading: ('default', HOME_LOG)
cbs2[0].setChecked(True)
pump(3)
batch_project.choose_save_target = _real_choose
ok('B14 选「默认通联日志」后复选框**不带**文件名（定稿：默认去处不挂 main.fhla）',
   cbs2[0].text() == '自动保存到日志文件', cbs2[0].text())

tbl2 = bw2.findChild(QTableWidget)
_fill_log_col(tbl2, batch_project.KEYS,
              {'date': '2026-11-15', 'time': '21:30', 'm_call': 'BI8SQL',
               'o_call': 'BG8YYY', 'freq': '144.200', 'mode': 'FM',
               'm_rst': '59', 'o_rst': '59'})
DIALOG_TEXTS.clear()
POPUPS.clear()
btn_done2 = _button(bw2, '完成 (Ctrl+S)')
btn_done2.click()
pump(5)
ok('B15 完成时直接写到选定的日志', _calls(_read(HOME_LOG)) == ['BG8YYY'],
   str(_calls(_read(HOME_LOG))))
ok('B16 不再弹选择页（目标已在勾选时定好）', not DIALOG_TEXTS, str(DIALOG_TEXTS[:2]))
ok('B17 没有偷偷写到别的日志',
   'BG8YYY' not in _calls(_read(A)) and 'BG8YYY' not in _calls(_read(B)),
   str(_calls(_read(A))))

# 只有「选具体文件」才在复选框上挂日志名（默认通联日志是固定去处，不挂）
APP_LOG = os.path.join(TMP, 'app_log.fhla')
project.save_project_file(APP_LOG, [])
bw4 = QtWidgets.QMainWindow()
batch_project.main(bw4)
pump(3)
cb4 = [c for c in bw4.findChildren(QCheckBox)
       if c.text().startswith('自动保存到日志文件')][0]
batch_project.choose_save_target = lambda parent, heading: ('append', APP_LOG)
cb4.setChecked(True)
pump(3)
batch_project.choose_save_target = _real_choose
ok('B17b 选具体日志文件时复选框显示日志名',
   os.path.basename(APP_LOG) in cb4.text(), cb4.text())

# 不勾「自动保存」时点「完成」→ 同一个选择页（标题换成「已成功录入 N 条记录」）
bw3 = QtWidgets.QMainWindow()
batch_project.main(bw3)
pump(3)
tbl3 = bw3.findChild(QTableWidget)
_fill_log_col(tbl3, batch_project.KEYS,
              {'date': '2026-11-15', 'time': '21:40', 'm_call': 'BI8SQL',
               'o_call': 'BG8XXX', 'freq': '144.300', 'mode': 'FM',
               'm_rst': '59', 'o_rst': '59'})
DIALOG_TEXTS.clear()
_button(bw3, '完成 (Ctrl+S)').click()
pump(5)
ok('B18 未勾自动保存时，完成页就是同一套选择页',
   any('已成功录入 1 条记录' in t for t in DIALOG_TEXTS)
   and any(t.startswith('OPT:添加到日志文件') for t in DIALOG_TEXTS),
   str(DIALOG_TEXTS[:3]))
ok('B19 选择页上有确定 / 取消两个按钮',
   any('BTN:' in t and '确定' in t and '取消' in t for t in DIALOG_TEXTS),
   str([t for t in DIALOG_TEXTS if t.startswith('BTN:')]))
ok('B20 取消不会落盘', 'BG8XXX' not in _calls(_read(HOME_LOG)),
   str(_calls(_read(HOME_LOG))))

# ==========================================================================
# D. 直接打开 / 编辑 / 保存 .adi
# ==========================================================================
print('--- D .adi 直接打开编辑保存 ---', flush=True)
ADI = os.path.join(TMP, 'test.adi')
adi_recs = [_rec('BG3C1', time='22:00'), _rec('BG3C2', time='22:10')]
with open(ADI, 'w', encoding='utf-8') as f:
    f.write(export_adi.records_to_adif(adi_recs))

data, key, meta = project.read_project_file(ADI)
ok('D1 直接读取 .adi 得到记录', _calls(data) == ['BG3C1', 'BG3C2'], str(_calls(data)))
ok('D2 .adi 没有密钥 / 属性块', key is None and meta is None)
ok('D3 时间按本地时间读回（UTC↔本地往返不失真）',
   (data[0]['date'], data[0]['time']) == ('2026-11-15', '22:00'),
   f"{data[0]['date']} {data[0]['time']}")

win_c = QtWidgets.QMainWindow()
with open(ADI, 'rb') as _f:
    adi_before_open = _f.read()
project.main(win_c, data, ADI)
pump(3)
api_c = win_c._perf_api
with open(ADI, 'rb') as _f:
    adi_after_open = _f.read()
ok('D4 标题显示 .adi 文件名', 'test.adi' in win_c.windowTitle(), win_c.windowTitle())
ok('D4b 打开后没改动就不重写 .adi（不丢未映射的 ADIF 标签）',
   adi_after_open == adi_before_open)
ok('D5 .adi 不给「加密此项目」菜单（明文交换格式）', win_c._aes_action is None)

api_c['append_to_project']([_rec('BG3C3', time='22:20')])
pump(3)
ok('D6 编辑后保存回 .adi',
   _calls(project.read_project_file(ADI)[0]) == ['BG3C1', 'BG3C2', 'BG3C3'],
   str(_calls(project.read_project_file(ADI)[0])))
with open(ADI, 'r', encoding='utf-8') as f:
    adi_text = f.read()
ok('D7 文件内容确实是 ADIF（不是 JSON）',
   adi_text.startswith('<ADIF_VER') and '<EOR>' in adi_text, adi_text[:40])
ok('D8 写回用的是 ADIF 标签', '<CALL:5>BG3C3' in adi_text,
   adi_text.splitlines()[-1][:80])

_open_f = project.project_open_filters()
_concat = _open_f.replace(';;', ' ')
ok('D9 打开过滤器三条：所有支持的文件 / F HamLog 项目文件 / ADI 文件',
   len(_open_f.split(';;')) == 3
   and '所有支持的文件 (*.fhla *.fhl *.adi)' in _open_f
   and 'F HamLog 项目文件 (*.fhla *.fhl)' in _open_f
   and _open_f.split(';;')[-1] == 'ADI 文件 (*.adi)',
   _open_f)
ok('D9b 三条过滤器都带后缀模式（Qt 才认）',
   _concat.count('(*.fhla *.fhl *.adi)') == 1 and '(*.fhla *.fhl)' in _concat
   and '(*.adi)' in _concat, _concat)
ok('D10 另存为过滤器里有 ADI 一条', '*.adi' in project.project_save_filters())
ok('D11 补后缀：选了 ADI 那条就补 .adi',
   project.complete_project_suffix(os.path.join(TMP, 'x'), project.SAVE_FILTER_ADI).endswith('.adi'))
ok('D12 已有 .adi 后缀不再重复追加',
   project.complete_project_suffix(ADI, '') == ADI)
ok('D13 is_adi_path 认得 .adi / .adif 且不误判 .fhl',
   project.is_adi_path('a.ADI') and project.is_adi_path('b.adif')
   and not project.is_adi_path('c.fhl'))

# 批量记录的选择页也能落到 .adi：追加到已有 .adi / 另存为新的 .adi
batch_project.apply_save_target(('append', ADI), [_rec('BG3C9', time='22:30')])
_adi_after = _calls(_read(ADI))
with open(ADI, 'r', encoding='utf-8') as f:
    _adi_txt = f.read()
ok('D13b 追加到已有 .adi（记录变多且仍写 ADIF）',
   _adi_after == ['BG3C1', 'BG3C2', 'BG3C3', 'BG3C9'] and '<CALL:5>BG3C9' in _adi_txt,
   str(_adi_after))
NEW_ADI = os.path.join(TMP, 'batch_out.adi')
batch_project.apply_save_target(('new', NEW_ADI), [_rec('BG7X1', time='22:40')])
with open(NEW_ADI, 'r', encoding='utf-8') as f:
    _new_txt = f.read()
ok('D13c 另存为新的 .adi（就是 ADIF 文本）',
   _calls(_read(NEW_ADI)) == ['BG7X1'] and _new_txt.startswith('<ADIF_VER'),
   _new_txt[:40])

POPUPS.clear()
api_c['show_project_props']()
pump(2)
ok('D14 .adi 的项目属性提示不支持的格式（提到 ADI）',
   any('ADI' in t for _k, _ti, t in POPUPS),
   str([t.splitlines()[2] for _k, _ti, t in POPUPS if t.count('\n') >= 2]))

# 关闭窗口（脏标记已清；万一弹保存也已被静默/取消）
for w in (bw2, win_c, win_b, win_a):
    try:
        w.close()
    except Exception:
        pass
pump(3)

QMessageBox.information = _real_info
QMessageBox.warning = _real_warn
QDialog.exec = _real_exec

print(f"\n通过 {sum(PASS)} / {len(PASS)}", flush=True)
print('RESULT=' + ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)
sys.exit(0 if all(PASS) else 1)
