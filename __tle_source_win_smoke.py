# -*- coding: utf-8 -*-
"""「星历数据源」独立窗口 + 独立配置文件（file/tle_sources.txt）的 offscreen 烟测。

覆盖：
  A. 函数级：地址校验 / 文本解析 / 读写独立文件 / 读取优先级（独立文件 → 旧设置键 → 默认）
  B. 窗口级：列表内容、双击即可编辑（编辑触发器 + 可编辑标志）、就地编辑校验与回滚、
     添加（含非法与重复拦截）、删除（至少保留一个）、上移下移、恢复默认、
     **点「保存」才落盘（不自动保存），保存成功后窗口自动关闭**、
     关窗不做任何提示（未保存更改直接丢弃）
  C. 集成：设置窗口只剩「设置星历数据源」入口按钮（没有内嵌列表）、打开独立窗口、
     重复打开复用同一窗口、保存更改不再往 m_xml.txt 写 sat_tle_sources

不污染用户数据：全程把 sp.TLE_SOURCES_PATH / sp.SETTINGS_PATH 指向临时文件；
仅最后一项需要真实 file/m_xml.txt 时先备份字节、结束时还原。
"""

import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QMainWindow, QListWidget, QPushButton,
    QInputDialog, QMessageBox, QLabel)

import satellite_pred as sp  # noqa: E402
import tle_source_window as tsw  # noqa: E402
import set as settings_window  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
REAL_SETTINGS = os.path.join(ROOT, 'file', 'm_xml.txt')

RESULT = []


def ok(name, cond, extra=''):
    RESULT.append(('PASS' if cond else 'FAIL', name, extra))
    print(('PASS' if cond else 'FAIL'), '-', name, extra)


TMP = tempfile.mkdtemp(prefix='fhl_src_')
SRC_FILE = os.path.join(TMP, 'tle_sources.txt')
SETTINGS_FILE = os.path.join(TMP, 'm_xml.txt')
REAL_SRC_PATH = sp.TLE_SOURCES_PATH   # 打补丁前的真实路径，用于校验常量本身

# 把数据源文件与设置文件都指向临时目录，避免动到用户数据
sp.TLE_SOURCES_PATH = SRC_FILE
sp.SETTINGS_PATH = SETTINGS_FILE

DEFAULT = list(sp.DEFAULT_TLE_SOURCES)
MIRROR_A = 'https://mirror.example/a.txt'
MIRROR_B = 'https://mirror.example/b.txt'


def write_settings(extra=None):
    data = {'m_call': 'BI8SQL', 'sat_auto_update': False, 'sat_sats': []}
    if extra:
        data.update(extra)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        f.write(str(data))


def file_urls():
    """按数据源文件里的实际内容取地址（跳过 # 注释与空行）。"""
    return sp.parse_tle_sources_text(open(SRC_FILE, encoding='utf-8').read())


def data_lines():
    return [ln for ln in open(SRC_FILE, encoding='utf-8').read().splitlines()
            if ln.strip() and not ln.strip().startswith('#')]


def make_window():
    """开一个真实的「星历数据源」窗口并返回 (win, list, buttons)。"""
    win = QMainWindow()
    tsw.main(win)
    lst = win.findChildren(QListWidget)[0]
    buttons = {b.text(): b for b in win.findChildren(QPushButton)}
    return win, lst, buttons


def row_texts(lst):
    """列表各行地址，按行序。"""
    return [lst.item(i).text() for i in range(lst.count())]


def set_text(lst, row, text):
    """等价于双击该行后在编辑器里改完回车（delegate 提交即 setText）。"""
    lst.item(row).setText(text)


app = QApplication.instance() or QApplication([])
widgets = []
try:
    # ---------------- A. 函数级 ----------------
    ok('数据源文件为独立文件（不是 m_xml.txt）',
       os.path.basename(REAL_SRC_PATH) == 'tle_sources.txt'
       and REAL_SRC_PATH != REAL_SETTINGS,
       REAL_SRC_PATH)
    ok('默认数据源为内置 Celestrak', DEFAULT == [sp.CELESTRAK_ACTIVE_URL], str(DEFAULT))

    ok('地址校验：http/https/ftp 通过、其它拒绝',
       sp.is_valid_tle_source('http://a/b') and sp.is_valid_tle_source('https://a/b')
       and sp.is_valid_tle_source('ftp://a/b')
       and not sp.is_valid_tle_source('a/b.txt')
       and not sp.is_valid_tle_source('')
       and not sp.is_valid_tle_source('http://a/b c'))

    parsed = sp.parse_tle_sources_text(
        '# 注释\n\nhttps://a/1.txt\n  https://b/2.txt  \nhttps://a/1.txt\n')
    ok('解析：忽略注释/空行、去空白、按顺序去重',
       parsed == ['https://a/1.txt', 'https://b/2.txt'], str(parsed))

    # 无文件、无旧键 → 默认
    ok('无独立文件且无旧键 → 回退默认', sp.load_tle_sources() == DEFAULT)

    # 只有旧键（早期版本写在 m_xml.txt 里）→ 兼容读取
    write_settings({'sat_tle_sources': [MIRROR_A]})
    ok('旧设置键可兼容读取', sp.load_tle_sources() == [MIRROR_A], str(sp.load_tle_sources()))

    # 独立文件存在 → 优先于旧键
    sp.save_tle_sources([MIRROR_B])
    ok('独立文件优先于旧键', sp.load_tle_sources() == [MIRROR_B], str(sp.load_tle_sources()))
    ok('保存时清掉设置文件里的旧键',
       'sat_tle_sources' not in eval(open(SETTINGS_FILE, encoding='utf-8').read()))
    ok('清理旧键不破坏其它设置',
       eval(open(SETTINGS_FILE, encoding='utf-8').read()).get('m_call') == 'BI8SQL')

    text = open(SRC_FILE, encoding='utf-8').read()
    ok('文件为每行一个地址（注释行跳过）', data_lines() == [MIRROR_B], str(data_lines()))
    ok('文件带可读的表头注释', text.startswith('# F HamLog 星历(TLE) 数据源列表'), text[:30])
    ok('保存会规整空值/重复并至少保留一个默认源',
       sp.save_tle_sources(['  ', MIRROR_A, MIRROR_A]) == [MIRROR_A]
       and sp.save_tle_sources([]) == DEFAULT)
    ok('文件被清空到只有注释 → 回退默认',
       (open(SRC_FILE, 'w', encoding='utf-8').write('# 只有注释\n'),
        sp.load_tle_sources() == DEFAULT)[1])

    # ---------------- B. 窗口级 ----------------
    sp.save_tle_sources([DEFAULT[0], MIRROR_A])
    win, lst, buttons = make_window()
    widgets.append(win)
    ok('窗口标题为「星历数据源」', win.windowTitle() == '星历数据源', win.windowTitle())
    ok('列表按文件内容列出数据源',
       row_texts(lst) == [DEFAULT[0], MIRROR_A], str(row_texts(lst)))
    ok('列表项均为可编辑（双击即可编辑）',
       all(lst.item(i).flags() & Qt.ItemFlag.ItemIsEditable
           for i in range(lst.count())))
    ok('按钮齐全',
       all(t in buttons for t in ('添加', '删除', '上移', '下移', '恢复默认',
                                  '保存', '关闭')),
       str(sorted(buttons)))
    ok('没有「测试延迟」按钮', '测试延迟' not in buttons, str(sorted(buttons)))
    ok('初始无未保存更改，「保存」禁用', not buttons['保存'].isEnabled())

    trig = lst.editTriggers()
    ok('双击即可编辑（编辑触发器含 DoubleClicked）',
       bool(trig & QAbstractItemView.EditTrigger.DoubleClicked), str(trig))

    # --- 双击改完回车：只改窗口内列表，点「保存」才写文件 ---
    set_text(lst, 1, MIRROR_B)
    ok('就地编辑后列表已更新', lst.item(1).text() == MIRROR_B)
    ok('就地编辑后不自动写文件', file_urls() == [DEFAULT[0], MIRROR_A], str(file_urls()))
    ok('提交后记录新的基准值（可再次回滚）',
       lst.item(1).data(Qt.UserRole) == MIRROR_B)
    ok('有未保存更改时「保存」可用', buttons['保存'].isEnabled())

    # --- 点「保存」才落盘，且保存成功后窗口自动关闭 ---
    buttons['保存'].click()
    ok('保存后写入独立文件', file_urls() == [DEFAULT[0], MIRROR_B], str(file_urls()))
    ok('保存成功后窗口自动关闭', not win.isVisible())

    # --- 非法地址回滚 ---
    set_text(lst, 1, 'mirror.example/b.txt')
    ok('非法地址被回滚', lst.item(1).text() == MIRROR_B, lst.item(1).text())
    ok('非法地址未写进文件', file_urls() == [DEFAULT[0], MIRROR_B])
    ok('非法地址给出原因提示',
       any('未修改' in l.text() for l in win.findChildren(QLabel)),
       str([l.text() for l in win.findChildren(QLabel)]))

    # --- 空地址回滚 ---
    set_text(lst, 1, '   ')
    ok('空地址被回滚', lst.item(1).text() == MIRROR_B,
       repr(lst.item(1).text()))

    # --- 重复地址回滚 ---
    set_text(lst, 1, DEFAULT[0])
    ok('重复地址被回滚', lst.item(1).text() == MIRROR_B, lst.item(1).text())
    ok('重复地址未写进文件', file_urls() == [DEFAULT[0], MIRROR_B])

    # --- 首尾空白自动规范化（同样等「保存」） ---
    set_text(lst, 1, '   %s   ' % MIRROR_A)
    ok('首尾空白自动去掉', lst.item(1).text() == MIRROR_A,
       repr(lst.item(1).text()))
    ok('规范化结果未自动落盘', file_urls() == [DEFAULT[0], MIRROR_B], str(file_urls()))
    buttons['保存'].click()
    ok('规范化结果保存后落盘', file_urls() == [DEFAULT[0], MIRROR_A], str(file_urls()))

    # --- 添加（patch QInputDialog / QMessageBox） ---
    _real_gettext = QInputDialog.getText
    _real_warning = QMessageBox.warning
    _real_information = QMessageBox.information
    _real_question = QMessageBox.question
    queue = ['not-a-url', MIRROR_A, MIRROR_B]
    warns = []
    infos = []
    QInputDialog.getText = staticmethod(
        lambda *a, **k: (queue.pop(0), True) if queue else ('', False))
    QMessageBox.warning = staticmethod(lambda *a, **k: warns.append(a[2] if len(a) > 2 else ''))
    QMessageBox.information = staticmethod(
        lambda *a, **k: infos.append(a[2] if len(a) > 2 else ''))
    try:
        buttons['添加'].click()          # 非法地址 → 拒
        buttons['添加'].click()          # 已存在 → 拒
        buttons['添加'].click()          # 正常添加
    finally:
        QInputDialog.getText = _real_gettext
    ok('添加非法地址被拒并提示', len(warns) == 1 and 'http' in warns[0], str(warns))
    ok('添加重复地址被拒并提示',
       any('已在列表中' in m for m in infos), str(infos))
    ok('正常添加成功且追加在末尾',
       row_texts(lst) == [DEFAULT[0], MIRROR_A, MIRROR_B], str(row_texts(lst)))
    ok('添加后不自动落盘', file_urls() == [DEFAULT[0], MIRROR_A], str(file_urls()))
    buttons['保存'].click()
    ok('添加后保存才落盘', file_urls() == [DEFAULT[0], MIRROR_A, MIRROR_B], str(file_urls()))

    # --- 上移 / 下移 ---
    lst.setCurrentRow(2)
    buttons['上移'].click()
    buttons['上移'].click()
    ok('上移到首位即提高优先级', lst.item(0).text() == MIRROR_B,
       lst.item(0).text())
    ok('上移后当前行跟随', lst.currentRow() == 0, str(lst.currentRow()))
    ok('顺序调整不自动落盘', file_urls()[0] == DEFAULT[0], str(file_urls()))
    order_before = row_texts(lst)
    buttons['上移'].click()   # 已在首位，越界不动
    ok('首位再上移无变化', row_texts(lst) == order_before)
    buttons['下移'].click()
    ok('下移交换相邻两项',
       row_texts(lst) == [order_before[1], order_before[0], order_before[2]],
       str(row_texts(lst)))

    # --- 删除 ---
    lst.setCurrentRow(0)
    buttons['删除'].click()
    ok('删除成功', row_texts(lst) == [MIRROR_B, MIRROR_A], str(row_texts(lst)))
    ok('删除后不自动落盘', file_urls() == [DEFAULT[0], MIRROR_A, MIRROR_B], str(file_urls()))
    lst.setCurrentRow(0)
    buttons['删除'].click()
    infos.clear()
    lst.setCurrentRow(0)
    buttons['删除'].click()
    ok('至少保留一个数据源', lst.count() == 1, str(lst.count()))
    ok('删到最后一个时给出提示',
       any('至少' in m for m in infos), str(infos))

    # --- 恢复默认 ---
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        buttons['恢复默认'].click()
    finally:
        QMessageBox.question = _real_question
    ok('恢复默认后列表回到内置源', row_texts(lst) == DEFAULT, str(row_texts(lst)))
    ok('恢复默认后不自动落盘', file_urls() == [DEFAULT[0], MIRROR_A, MIRROR_B], str(file_urls()))
    buttons['保存'].click()
    ok('恢复默认后保存落盘', file_urls() == DEFAULT, str(file_urls()))
    QMessageBox.warning = _real_warning
    QMessageBox.information = _real_information

    # --- 未保存更改时关窗：不做任何提示，直接丢弃并关闭 ---
    set_text(lst, 0, MIRROR_B)   # 制造未保存更改
    asked = []
    QMessageBox.question = staticmethod(lambda *a, **k: asked.append(1))
    try:
        win.close()
    finally:
        QMessageBox.question = _real_question
    ok('未保存关窗：不弹任何询问', asked == [], str(asked))
    ok('未保存关窗：不写入文件且窗口关闭',
       file_urls() == DEFAULT and not win.isVisible(), str(file_urls()))

    # --- 关掉窗口不应丢配置（下次打开读文件） ---
    win2, lst2, _b2 = make_window()
    widgets.append(win2)
    ok('重开窗口读到上次保存的内容', row_texts(lst2) == DEFAULT)

    # ---------------- C. 与设置窗口的集成 ----------------
    m_bak = None
    if os.path.exists(REAL_SETTINGS):
        m_bak = REAL_SETTINGS + '.srcsmoke_bak'
        shutil.copyfile(REAL_SETTINGS, m_bak)

    set_win = QMainWindow()
    settings_window.main(set_win)
    widgets.append(set_win)
    ok('设置窗口不再内嵌数据源列表',
       len(set_win.findChildren(QListWidget)) == 0,
       str(len(set_win.findChildren(QListWidget))))
    sbtn = {b.text(): b for b in set_win.findChildren(QPushButton)}
    ok('设置窗口有「设置星历数据源」按钮', '设置星历数据源' in sbtn, str(sorted(sbtn)))
    ok('设置窗口不再显示数据源个数摘要',
       not any('当前' in l.text() for l in set_win.findChildren(QLabel)))

    # 点击按钮 → 打开真实的独立窗口（并把窗口引用挂在 set 模块上）
    sbtn['设置星历数据源'].click()
    opened = getattr(settings_window, 'tle_source_win', None)
    ok('按钮打开独立数据源窗口', opened is not None and opened.isVisible())
    widgets.append(opened)
    first = opened
    sbtn['设置星历数据源'].click()
    ok('重复点击复用同一窗口（不重复打开）',
       getattr(settings_window, 'tle_source_win', None) is first)

    # 独立窗口里加一个数据源（不再有设置窗口摘要同步，但添加本身应生效）
    lst3 = first.findChildren(QListWidget)[0]
    b3 = {b.text(): b for b in first.findChildren(QPushButton)}
    _real_get3 = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: (MIRROR_A, True))
    try:
        b3['添加'].click()
    finally:
        QInputDialog.getText = _real_get3
    ok('独立窗口内添加生效', lst3.count() == 2, str(lst3.count()))
    b3['保存'].click()
    ok('独立窗口点「保存」后写入临时文件',
       file_urls() == [DEFAULT[0], MIRROR_A], str(file_urls()))
    ok('集成：保存后窗口自动关闭', not first.isVisible())
    first.close()   # 兜底（保存后应已自动关闭）

    # 「保存更改」不再往 m_xml.txt 写 sat_tle_sources
    _real_q2 = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    try:
        {b.text(): b for b in set_win.findChildren(QPushButton)}['保存更改'].click()
    finally:
        QMessageBox.warning = _real_q2
    real_saved = eval(open(REAL_SETTINGS, encoding='utf-8').read())
    ok('设置窗口保存更改不再写 sat_tle_sources',
       'sat_tle_sources' not in real_saved, str(list(real_saved)[:6]))
    ok('设置窗口保存更改仍保留其它键',
       'm_call' in real_saved and 'sat_sats' in real_saved)

    if m_bak and os.path.exists(m_bak):
        shutil.copyfile(m_bak, REAL_SETTINGS)
        os.remove(m_bak)
finally:
    # 兜底：关窗不做任何提示，直接关闭即可（不会弹真对话框卡住）
    for w in widgets:
        try:
            w.close()
        except Exception:
            pass
    shutil.rmtree(TMP, ignore_errors=True)

print()
failed = [r for r in RESULT if r[0] == 'FAIL']
print('总计 %d 项，失败 %d 项' % (len(RESULT), len(failed)))
for r in failed:
    print('  FAIL:', r[1], r[2])
print('RESULT:', 'ALL PASS' if not failed else 'HAS FAILURES')
print('临时数据源文件内容示例（测试实际写入的临时文件）：')
if os.path.exists(SRC_FILE):
    print(open(SRC_FILE, encoding='utf-8').read())
else:
    print('（临时文件未生成）')
sys.exit(1 if failed else 0)
