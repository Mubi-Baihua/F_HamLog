# -*- coding: utf-8 -*-
"""自选卫星数量上限（250）拦阻 + 清除所有选择 的 headless 烟测。

覆盖：
1. MAX_SELECTED_SATELLITES == 250；clamp_selected_count 的裁剪语义与确定性
2. 未超限时点「确定」正常关闭（Accepted），返回集合完整
3. 超限时点「确定」不关闭，弹出「选择的卫星过多」，含三个按钮
4. 超限 + 点「重新选择」→ 对话框仍在，选择不变
5. 超限 + 点「清除所有选择」→ 出现二次确认；选「否」不清空，选「是」清空
6. 清空后再次点「确定」可正常关闭，返回空集合
7. 计数标签在超限时变红并显示"超过上限"
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton
from PySide6.QtCore import Qt, QTimer

import satellite_pred as sp
from satellite_window import SatelliteSelectDialog

PASS = []
LIMIT = sp.MAX_SELECTED_SATELLITES


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''))


def names_n(n):
    return [f'SAT-{i:04d}' for i in range(n)]


def dialog_buttons(dlg):
    """对话框上可见的按钮文字列表。"""
    return [b.text() for b in dlg.findChildren(QPushButton) if b.isVisible()]


def click_std(std, msec=140):
    """点击 QMessageBox 上的标准按钮（Yes/No 等），按 standardButton 匹配。

    不按文字匹配：按钮文案可能被本地化或带助记符，按 role 匹配更稳。
    """
    def _do():
        for w in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                b = w.button(std)
                if b is not None and b.isVisible():
                    b.click()
                    return
    QTimer.singleShot(msec, _do)


def top_button_by_text(text):
    """按文字找按钮：优先在可见的 QMessageBox 里找，其次在可见的 QDialog 里找。

    只在**可见**的窗口里找是关键：offscreen 下 topLevelWidgets() 会同时返回
    SatelliteSelectDialog 自己，如果取到隐藏窗口上的按钮再 click()，槽函数不会触发，
    表现为测试永久挂死（实测踩过）。
    """
    std_map = {
        'Yes': QMessageBox.StandardButton.Yes,
        'No': QMessageBox.StandardButton.No,
    }
    # 注意：标准按钮的 text() 带助记符（实测为 '&Yes' / '&No'），
    # 因此 Yes/No 必须走 w.button(role) 匹配；下方纯文本匹配仅用于自定义按钮。
    boxes = []
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, QMessageBox) and w.isVisible():
            boxes.append(w)
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, QDialog) and not isinstance(w, QMessageBox) and w.isVisible():
            boxes.append(w)
    for w in boxes:
        std = std_map.get(text)
        if std is not None and isinstance(w, QMessageBox):
            b = w.button(std)
            if b is not None and b.isVisible():
                return w, b
        for b in w.findChildren(QPushButton):
            if b.isVisible() and b.text() == text:
                return w, b
    return None, None


def _clicker(text, timeout_ms=5000, delay_ms=0):
    """返回一个已启动的重复 QTimer 包装；找到按钮即点击并停止。

    必须用**独立的 QTimer 对象**而不是链式 singleShot：消息框由 accept() 内部的
    exec() 弹出，属于嵌套模态循环；链式 singleShot 在模态嵌套后不再重新触发，
    会导致永远点不到按钮、测试挂死（实测踩过）。
    delay_ms>0 时先等待一段时间再开始找按钮（用于"上一步完成后再点"的场景）。
    """
    t = QTimer()
    t.setInterval(50)
    state = {'n': 0, 'waited': 0}

    def _tick():
        if state['waited'] < delay_ms:
            state['waited'] += 50
            return
        state['n'] += 1
        w, b = top_button_by_text(text)
        if b is not None:
            b.click()
            t.stop()
            return
        if state['n'] * 50 >= timeout_ms:
            t.stop()

    t.timeout.connect(_tick)
    t.start()
    return t


def _grabber(store, timeout_ms=5000, delay_ms=0):
    """返回一个已启动的重复 QTimer 包装；抓到消息框内容即停止。"""
    t = QTimer()
    t.setInterval(50)
    state = {'n': 0, 'waited': 0}

    def _tick():
        if state['waited'] < delay_ms:
            state['waited'] += 50
            return
        state['n'] += 1
        for w in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                store['title'] = w.windowTitle()
                store['text'] = w.text()
                store['info'] = w.informativeText()
                store['buttons'] = [b.text() for b in w.findChildren(QPushButton)
                                    if b.isVisible()]
                t.stop()
                return
        if state['n'] * 50 >= timeout_ms:
            t.stop()

    t.timeout.connect(_tick)
    t.start()
    return t


def click_later(btn_getter, msec=80):
    """延迟点击，避免在 exec() 阻塞前点空。btn_getter() 返回 (widget, button)。"""
    def _do():
        w, b = btn_getter()
        if b is not None:
            b.click()
    QTimer.singleShot(msec, _do)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# ---------- 1. 常量与裁剪函数 ----------
ok('上限常量为 250', LIMIT == 250, str(LIMIT))
small = {f'X{i}' for i in range(100)}
keep, over = sp.clamp_selected_count(small)
ok('未超限时原样保留', keep == small and over == 0, f'{len(keep)}/{over}')
big = {f'Y{i:04d}' for i in range(1200)}
keep2, over2 = sp.clamp_selected_count(big)
ok('超限时裁到上限颗数', len(keep2) == LIMIT and over2 == 1200 - LIMIT,
   f'{len(keep2)}/{over2}')
ok('裁剪结果确定（同一输入两次一致）', keep2 == sp.clamp_selected_count(big)[0])
ok('裁剪取的是排序后前 %d 颗' % LIMIT, keep2 == set(sorted(big)[:LIMIT]))
ok('空/None 安全', sp.clamp_selected_count(None)[0] == set() and
   sp.clamp_selected_count(set())[1] == 0)

# ---------- 2. 未超限 → 正常关闭 ----------
dlg = SatelliteSelectDialog(None, names_n(50), {f'SAT-{i:04d}' for i in range(10)})
dlg.show()
app.processEvents()
ok('未超限时 get_selected 计数正确', len(dlg.get_selected()) == 10, str(len(dlg.get_selected())))
QTimer.singleShot(60, lambda: dlg.accept())
res = dlg.exec()
ok('未超限点确定 → Accepted', res == QDialog.Accepted, str(res))
ok('未超限返回集合完整', len(dlg.get_selected()) == 10)
dlg.deleteLater()

# ---------- 3. 超限 → 拦下并提示 ----------
dlg = SatelliteSelectDialog(None, names_n(900), set(names_n(900)))
dlg.show()
app.processEvents()
ok('超限时计数标签变红并提示超过上限',
   '超过上限' in dlg.count_label.text() and '#c0392b' in dlg.count_label.styleSheet(),
   dlg.count_label.text())

seen = {}
g1 = _grabber(seen)                            # 抓「选择的卫星过多」提示框
QTimer.singleShot(150, lambda: dlg.accept())   # 触发「确定」→ 应弹提示并停下
c1 = _clicker('重新选择', delay_ms=700)          # 点「重新选择」→ 应留在对话框
# 点完「重新选择」后对话框会停在原地等用户继续调整，必须再关掉它，否则 exec() 永不返回
c1b = _clicker('Cancel', timeout_ms=1500, delay_ms=1400)
res = dlg.exec()
ok('超限点确定 → 对话框未关闭', res != QDialog.Accepted, str(res))
ok('提示标题为「选择的卫星过多」', seen.get('title') == '选择的卫星过多', str(seen.get('title')))
ok('提示正文为「选择的卫星过多。」', seen.get('text') == '选择的卫星过多。', str(seen.get('text')))
btns = seen.get('buttons') or []
ok('提示含「重新选择」按钮', '重新选择' in btns, str(btns))
ok('提示含「清除所有选择」按钮', '清除所有选择' in btns, str(btns))
ok('点「重新选择」后选择保持不变', len(dlg.get_selected()) == 900, str(len(dlg.get_selected())))
ok('点「重新选择」不触发重开（reset_requested 仍为 False）',
   dlg.reset_requested is False, str(dlg.reset_requested))

# ---------- 4. 超限 + 清除所有选择 + 二次确认「否」 ----------
seen2 = {}
QTimer.singleShot(150, lambda: dlg.accept())       # 触发「确定」→ 弹超限提示
c2 = _clicker('清除所有选择', delay_ms=700)      # 点清除 → 弹二次确认
g2 = _grabber(seen2, delay_ms=1000)                # 延迟抓取，跳过超限提示，抓二次确认
c3 = _clicker('No', delay_ms=1400)                 # 在二次确认里选「否」
c3b = _clicker('Cancel', timeout_ms=1500, delay_ms=2200)   # 收尾关闭对话框
res = dlg.exec()
ok('二次确认标题为「确认清除」', seen2.get('title') == '确认清除', str(seen2.get('title')))
ok('二次确认文案提及颗粒数', '900' in str(seen2.get('text')), str(seen2.get('text')))
ok('二次确认文案说明会重新打开选择窗口', '重新打开选择窗口' in str(seen2.get('text')),
   str(seen2.get('text')))
ok('二次确认选「否」→ 不清空、不重开',
   len(dlg.get_selected()) == 900 and dlg.reset_requested is False,
   f'{len(dlg.get_selected())} / {dlg.reset_requested}')

# ---------- 5. 超限 + 清除所有选择 + 二次确认「是」→ 关闭并请求重开 ----------
seen3 = {}
QTimer.singleShot(150, lambda: dlg.accept())       # 触发「确定」→ 弹超限提示
c4 = _clicker('清除所有选择', delay_ms=700)      # 重新点清除
g3 = _grabber(seen3, delay_ms=1000)                # 延迟抓取，抓二次确认
c5 = _clicker('Yes', delay_ms=1400)                # 二次确认选「是」
res = dlg.exec()
ok('二次确认标题为「确认清除」', seen3.get('title') == '确认清除', str(seen3.get('title')))
ok('二次确认选「是」→ 对话框关闭（Rejected）', res != QDialog.Accepted, str(res))
ok('二次确认选「是」→ reset_requested 置 True（调用方将重开新窗口）',
   dlg.reset_requested is True, str(dlg.reset_requested))
dlg.deleteLater()

# ---------- 5b. 重开循环：清除后以空选择重建新窗口 ----------
# 模拟调用方的 while 循环：第一次 accept 超限 → 清除 → 重开；第二次直接确定。
selected_names = set(names_n(900))
rounds = []


def _round(sel):
    """跑一轮对话框：超限则清除重开（返回 (False, set())），否则接受。"""
    d2 = SatelliteSelectDialog(None, names_n(900), sel)
    d2.show()
    app.processEvents()
    rounds.append(len(d2.get_selected()))
    if len(d2.get_selected()) > LIMIT:
        # 第一轮：触发确定 → 清除 → 二次确认「是」
        QTimer.singleShot(120, lambda: d2.accept())
        _clicker('清除所有选择', delay_ms=600)
        _clicker('Yes', delay_ms=1200)
        r = d2.exec()
        req = d2.reset_requested
        d2.deleteLater()
        return (r == QDialog.Accepted), req
    # 第二轮：全新窗口，勾 2 颗后确定
    if not sel:
        d2.items[d2._row_names[0]].setCheckState(Qt.CheckState.Checked)
        d2.items[d2._row_names[1]].setCheckState(Qt.CheckState.Checked)
    QTimer.singleShot(120, lambda: d2.accept())
    r = d2.exec()
    got = d2.get_selected() if r == QDialog.Accepted else None
    d2.deleteLater()
    return (r == QDialog.Accepted), got


acc, req = _round(selected_names)
ok('重开循环：首轮超限被清除并请求重开', (not acc) and req is True, f'{acc}/{req}')
selected_names = set()   # 调用方在重开前清空选择
acc2, got2 = _round(selected_names)
ok('重开循环：新窗口为空选择（未继承旧的 900 颗）', rounds[1] == 0, str(rounds))
ok('重开循环：新窗口可正常确定并返回勾选结果',
   acc2 and got2 is not None and len(got2) == 2, f'{acc2}/{got2}')

# ---------- 6. 少量选择 → 正常关闭并返回 ----------
dlg = SatelliteSelectDialog(None, names_n(900), set())
dlg.show()
app.processEvents()
n0, n1 = dlg._row_names[0], dlg._row_names[1]
dlg.items[n0].setCheckState(Qt.CheckState.Checked)
dlg.items[n1].setCheckState(Qt.CheckState.Checked)
QTimer.singleShot(60, lambda: dlg.accept())
res = dlg.exec()
ok('少量选择点确定 → Accepted', res == QDialog.Accepted, str(res))
ok('返回恰好勾选的 2 颗', dlg.get_selected() == {n0, n1}, str(sorted(dlg.get_selected())))
dlg.deleteLater()

# ---------- 7. 读取 m_xml 保存的超量选择 → 同样弹提示 ----------
# 直接驱动共用的提示函数（main() 里就是拿它接的返回值做清空/落盘）。
from satellite_window import prompt_over_limit_selection

hint = '设置文件 file/m_xml.txt 中保存的自选卫星已超过上限。'
seen4 = {}
# 抓取器必须比点击器先就位：QMessageBox 的按钮是延迟布局的，
# 若抓取与点击同一 tick 竞争，会出现「点到了但没抓到文案」。
g0 = _grabber(seen4, delay_ms=0)


# 7a. 点「重新选择」→ 不清空
c = _clicker('重新选择', delay_ms=200, timeout_ms=2000)
res = prompt_over_limit_selection(None, 900, LIMIT, source_hint=hint)
ok('m_xml 超限提示返回 False（重新选择 → 不清空）', res is False, str(res))
ok('m_xml 超限提示标题为「选择的卫星过多」',
   seen4.get('title') == '选择的卫星过多', str(seen4.get('title')))
ok('m_xml 超限提示正文含 m_xml.txt 来源说明',
   'm_xml.txt' in str(seen4.get('info')), str(seen4.get('info')))
ok('m_xml 超限提示按钮为 重新选择/清除所有选择/取消',
   seen4.get('buttons') == ['重新选择', '清除所有选择', '取消'],
   str(seen4.get('buttons')))

# 7b. 点「清除所有选择」但二次确认选「否」→ 不清空
seen5 = {}
g2 = _grabber(seen5, delay_ms=900)
_clicker('清除所有选择', delay_ms=200)
_clicker('No', delay_ms=1200)
res = prompt_over_limit_selection(None, 900, LIMIT, source_hint=hint)
ok('m_xml 超限 + 二次确认选「否」→ 不清空（返回 False）', res is False, str(res))
ok('m_xml 二次确认标题为「确认清除」', seen5.get('title') == '确认清除', str(seen5.get('title')))

# 7c. 点「清除所有选择」+ 二次确认选「是」→ 返回 True（调用方清空并落盘）
g3 = _grabber({}, delay_ms=900)
_clicker('清除所有选择', delay_ms=200)
_clicker('Yes', delay_ms=1200)
res = prompt_over_limit_selection(None, 900, LIMIT, source_hint=hint)
ok('m_xml 超限 + 二次确认选「是」→ 返回 True（清空并落盘）', res is True, str(res))

print()
print(f'总计 {len(PASS)} 项，通过 {sum(PASS)} 项。')
sys.exit(0 if all(PASS) else 1)
