# -*- coding: utf-8 -*-
"""恢复项目（recovered）时的保存行为烟测。

背景 bug：恢复项目文件时保存了两遍 ——
  project.main(..., recovered=True) 构建表格时 table_update() → save(message=False)，
  用户开着「自动保存」时该静默保存因无路径走进了交互分支，自己弹出「保存恢复的文件」并
  落盘一次（第 1 遍）；随后初始化块又把状态置为恒脏（哨兵）+ 回写备份，用户关闭窗口时
  再次被要求保存，于是又落盘一次（第 2 遍）。

本烟测覆盖：
  1) 打开恢复窗口：不弹保存对话框、不写项目文件、备份文件保持原样；
  2) 关闭恢复窗口（点「保存」）：只落盘一次，且能选到「保存恢复的文件」路径；
  3) 恢复后主动点保存：弹一次「保存恢复的文件」→ 写一次 → 关闭时不再提示、不再写；
  4) 恢复后编辑再保存：落盘内容含编辑结果，关闭时不再提示；
  5) 恢复窗口关闭时选「不保存」：内容留在备份中（下次仍可恢复）；
  6) 「保存并退出」在恢复场景不再以空路径写文件（不抛异常）。

跑法：.venv/Scripts/python.exe test_recover_save_smoke.py
结果同时写入 __recover_save_smoke_out.txt。
测完还原 file/m_xml.txt 与 file/project_backup.fhl（本机数据不是 playground）。
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MX = os.path.join(HERE, 'file', 'm_xml.txt')
BK = os.path.join(HERE, 'file', 'project_backup.fhl')
TMP = tempfile.mkdtemp(prefix='recover_save_smoke_')
OUT = open(os.path.join(HERE, '__recover_save_smoke_out.txt'), 'w', encoding='utf-8')

PASS = []
FAIL = []


def log(msg):
    print(msg)
    OUT.write(str(msg) + '\n')
    OUT.flush()


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    log(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


# ---------- 备份本机真实数据 ----------
_orig_mx = open(MX, 'rb').read()
_orig_bk = open(BK, 'rb').read() if os.path.exists(BK) else None

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PySide6.QtGui import QAction

import fhl_rw
import backup

REC = {
    'date': '2026-09-19', 'time': '21:00', 'm_call': 'BG1ABC', 'o_call': 'BG2DEF',
    'freq': '145.000', 'freq_rx': '435.000', 'mode': 'FM', 'prop_mode': 'SAT',
    'sat_name': 'ISS', 'm_rst': '59', 'o_rst': '59', 'm_qth': '北京', 'o_qth': '上海',
    'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
    'notes': '',
}

# ---------- 拦截：写文件 ----------
_orig_write = fhl_rw.write_fhl_file
_writes = []          # [(path, data)]
_dialogs = []         # 保存对话框标题
_msgs = []            # ('info'|'warning', title, text)
_msgboxes = []        # 关闭守卫等自绘对话框：('标题', '正文', [按钮文本])
_planned_target = [None]
_click_want = ['保存']


def _spy_write(path, data, key=None):
    _writes.append((path, data))
    return _orig_write(path, data, key)


def _fake_get_save(parent=None, title='', dir='', filt='', *a, **k):
    _dialogs.append(title)
    return _planned_target[0], filt


def _fake_msgbox_exec(self):
    texts = [b.text() for b in self.buttons()]
    _msgboxes.append((self.windowTitle(), self.text(), texts))
    self._fake_clicked = None
    for b in self.buttons():
        if b.text() == _click_want[0]:
            self._fake_clicked = b
            break
    return 0


def _fake_clicked_button(self):
    return getattr(self, '_fake_clicked', None)


def _fake_info(parent, title, text, *a, **k):
    _msgs.append(('info', title, text))
    return QMessageBox.StandardButton.Ok


def _fake_warning(parent, title, text, *a, **k):
    _msgs.append(('warning', title, text))
    return QMessageBox.StandardButton.Ok


fhl_rw.write_fhl_file = _spy_write
QFileDialog.getSaveFileName = staticmethod(_fake_get_save)
QMessageBox.exec = _fake_msgbox_exec
QMessageBox.clickedButton = _fake_clicked_button
QMessageBox.information = staticmethod(_fake_info)
QMessageBox.warning = staticmethod(_fake_warning)

app = QApplication(sys.argv)
import project


def reset(tag):
    _writes.clear()
    _dialogs.clear()
    _msgs.clear()
    _msgboxes.clear()
    _orig_write(BK, [dict(REC)], None)          # 模拟“有新未保存内容可恢复”
    target = os.path.join(TMP, f'{tag}.fhl')
    _planned_target[0] = target
    _click_want[0] = '保存'
    return target


def project_writes(target):
    t = os.path.abspath(target)
    return [w for w in _writes if os.path.abspath(w[0]) == t]


def make_window():
    w = QMainWindow()
    project.main(w, [dict(REC)], '', key_=None, recovered=True)
    return w


def find_action(w, text):
    for act in w.menuBar().actions():
        menu = act.menu()
        if menu is None:
            continue
        for a in menu.actions():
            if a.text() == text:
                return a
    return None


try:
    # ============ 场景 1：打开恢复窗口不该自己保存 ============
    log('== 场景1：打开恢复窗口（自动保存开启）')
    target = reset('s1')
    bk_before = open(BK, 'rb').read()
    w = make_window()
    check('打开时不弹保存对话框', len(_dialogs) == 0, f'实际 {_dialogs}')
    check('打开时不写项目文件', len(project_writes(target)) == 0)
    check('打开时不动备份文件', open(BK, 'rb').read() == bk_before)

    # 关闭：应提示一次保存，落盘一次
    w.close()
    check('关闭时提示「未保存的更改」', len(_msgboxes) == 1 and '未保存' in _msgboxes[0][0],
          f'{_msgboxes}')
    check('关闭保存：项目文件只写一次', len(project_writes(target)) == 1,
          f'实际 {len(project_writes(target))} 次')
    check('关闭保存：内容正确', project_writes(target) and project_writes(target)[0][1] == [REC])
    check('关闭保存：备份已清空', not backup.is_backup_nonempty(BK))

    # ============ 场景 2：恢复后主动保存 → 关闭不再提示 ============
    log('== 场景2：恢复后主动点「保存」，关闭时不应再保存一次')
    target = reset('s2')
    w = make_window()
    act = find_action(w, '保存')
    check('找到「保存」菜单项', act is not None)
    act.trigger()
    check('主动保存：弹一次「保存恢复的文件」', _dialogs == ['保存恢复的文件'], f'{_dialogs}')
    check('主动保存：项目文件写一次', len(project_writes(target)) == 1)
    check('主动保存：提示「已保存恢复的内容」',
          any('已保存恢复的内容' in text for _, _, text in _msgs), f'{_msgs}')
    check('主动保存：备份已清空', not backup.is_backup_nonempty(BK))

    _msgboxes.clear()
    w.close()
    check('关闭时不再提示保存', len(_msgboxes) == 0, f'{_msgboxes}')
    check('关闭时不再写项目文件', len(project_writes(target)) == 1,
          f'实际 {len(project_writes(target))} 次')
    check('窗口标题已改为目标文件名',
          os.path.basename(target) in w.windowTitle(), w.windowTitle())

    # ============ 场景 3：恢复后编辑再保存 ============
    log('== 场景3：恢复后编辑内容再保存')
    target = reset('s3')
    w = make_window()
    project.file[0]['notes'] = '编辑过'
    act = find_action(w, '保存')
    act.trigger()
    saved = project_writes(target)
    check('落盘一次且含编辑结果', len(saved) == 1 and saved[0][1][0]['notes'] == '编辑过')
    _msgboxes.clear()
    w.close()
    check('关闭时不再提示保存', len(_msgboxes) == 0)

    # ============ 场景 4：关闭时选「不保存」→ 备份保留 ============
    log('== 场景4：恢复后关闭选「不保存」，备份应保留可恢复内容')
    target = reset('s4')
    w = make_window()
    _click_want[0] = '不保存'
    w.close()
    check('关闭选不保存：项目文件未写', len(project_writes(target)) == 0)
    check('关闭选不保存：备份仍非空（下次可恢复）', backup.is_backup_nonempty(BK))
    data_back, _ = fhl_rw.read_fhl_file(BK)
    check('备份内容可读且与恢复内容一致', data_back == [REC], f'{data_back}')

    # ============ 场景 5：「保存并退出」在恢复场景不再崩 ============
    log('== 场景5：恢复场景点「保存并退出」（修复前以空路径写文件会抛异常）')
    target = reset('s5')
    w = make_window()
    act = find_action(w, '保存并退出')
    check('找到「保存并退出」菜单项', act is not None)
    # 槽函数里的 SystemExit 会直接从 PySide6 的 C++ 边界终止进程（finally 都跑不到），
    # 故本进程内临时把 sys.exit 置为 no-op，只为校验落盘结果（不影响其它场景）。
    _real_exit = sys.exit
    sys.exit = lambda *a, **k: None
    err = None
    try:
        act.trigger()
    except Exception as e:                       # 修复前：FileNotFoundError
        err = f'{type(e).__name__}: {e}'
    finally:
        sys.exit = _real_exit
    check('未抛异常（不再以空路径写文件）', err is None, str(err))
    check('保存并退出：弹「保存恢复的文件」', _dialogs == ['保存恢复的文件'], f'{_dialogs}')
    check('保存并退出：落盘一次', len(project_writes(target)) == 1,
          f'实际 {len(project_writes(target))} 次')

    # ============ 场景 6：普通项目（有保存路径）仍随自动保存落盘 ============
    log('== 场景6：普通项目（有保存路径）打开时仍自动保存一次')
    target = reset('s6')
    w6 = QMainWindow()
    project.main(w6, [dict(REC)], target, key_=None)
    check('普通项目打开即自动保存一次', len(project_writes(target)) == 1,
          f'实际 {len(project_writes(target))} 次')
    check('普通项目打开不弹保存对话框', len(_dialogs) == 0, f'{_dialogs}')
    _msgboxes.clear()
    w6.close()
    check('普通项目无更改时关闭不提示保存', len(_msgboxes) == 0, f'{_msgboxes}')

finally:
    open(MX, 'wb').write(_orig_mx)
    if _orig_bk is None:
        if os.path.exists(BK):
            os.remove(BK)
    else:
        open(BK, 'wb').write(_orig_bk)
    log('-- 已还原 file/m_xml.txt 与 file/project_backup.fhl')
    log('')
    log(f'===== 结果：{len(PASS)} 通过 / {len(FAIL)} 失败 =====')
    for f in FAIL:
        log(f'   FAILED: {f}')
    OUT.close()
