# -*- coding: utf-8 -*-
"""校验：① 表格 UI 与旧实现逐项一致（列宽/无 stretch/默认行高/委托外观）；② 自动跳底仅首次打开。

离屏运行，不触碰 file/ 用户数据（项目备份与设置均重定向临时目录）。
用法：python __ui_scroll_smoke.py [N]
"""
import os
import sys
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QStyle

import backup
import test as fhlgen

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
BAK = SETTINGS + '.sc_bak'
shutil.copyfile(SETTINGS, BAK)
TMPDIR = tempfile.mkdtemp(prefix='fhl_scroll_')
TMP_FHL = os.path.join(TMPDIR, 'perf.fhl')
backup.PROJECT_BACKUP = os.path.join(TMPDIR, 'project_backup.fhl')

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
records = fhlgen.generate_records(N)

import project as pj

PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''), flush=True)


def _cleanup():
    try:
        if os.path.exists(BAK):
            shutil.copyfile(BAK, SETTINGS)
            os.remove(BAK)
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)


import atexit
atexit.register(_cleanup)

# 期望的原始列宽（与 HEAD:project.py 逐行一致）
EXPECT_WIDTHS = [45, 80, 70, 90, 90, 70, 80, 90, 90, 80, 80, 120, 120, 80]

# 记录 scrollToBottom 调用次数：在 main 内部没法直接挂钩，改为监控 QTableView.scrollToBottom
_scroll_calls = []
_orig_scroll = QtWidgets.QTableView.scrollToBottom


def _spy_scroll(self):
    _scroll_calls.append(1)
    return _orig_scroll(self)


QtWidgets.QTableView.scrollToBottom = _spy_scroll

win = QtWidgets.QMainWindow()
pj.main(win, filee=records, save_path=TMP_FHL)
win.show()
for _ in range(5):
    app.processEvents()
api = win._perf_api
table = api['get_table']()

# ---------- A. UI 一致性 ----------
ok('列数为 14', table.columnCount() == 14, str(table.columnCount()))
widths = [table.columnWidth(c) for c in range(14)]
ok('14 列列宽与旧实现一致', widths == EXPECT_WIDTHS, str(widths))
ok('未启用 stretchLastSection', not table.horizontalHeader().stretchLastSection())
ok('表头 resize 模式 = Interactive',
   table.horizontalHeader().sectionResizeMode(0) == QHeaderView.Interactive)
ok('行高为 Qt 默认（未被强制 24）',
   table.verticalHeader().defaultSectionSize() != 24,
   str(table.verticalHeader().defaultSectionSize()))
ok('表头文本与旧实现一致',
   [table.horizontalHeaderItem(i).text() for i in range(14)] ==
   ["选择", "日期", "时间", "己方呼号", "对方呼号", "频率", "调制模式", "传播模式",
    "卫星名称", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH", "更多"])

# 委托外观：勾选列与末列均挂了自绘委托
d0 = table.itemDelegateForColumn(0)
d13 = table.itemDelegateForColumn(13)
ok('勾选列已挂 CheckColumnDelegate', d0 is not None and d0.__class__.__name__ == 'CheckColumnDelegate')
ok('末列已挂 MoreButtonDelegate', d13 is not None and d13.__class__.__name__ == 'MoreButtonDelegate')
# 末列按钮矩形：宽度铺满内容区，高度 26（与旧 QPushButton.setFixedHeight(26) 对齐）
from PySide6.QtCore import QRect
r = d13._btn_rect(QRect(0, 0, 80, 30))
ok('「更多」按钮高度 26 且居中', r.height() == 26 and r.y() == 2, str((r.x(), r.y(), r.width(), r.height())))
ok('「更多」按钮宽度铺满列（无左右缩进）', r.x() == 0 and r.width() == 80, str((r.x(), r.width())))

# 旧实现：无 cellWidget（委托替代）
ok('表格无任何 cellWidget（改用委托）', table.cellWidget(0, 0) is None and table.cellWidget(0, 13) is None)

# ---------- B. 自动跳底仅首次打开 ----------
ok('首次打开触发了 scrollToBottom（>=1 次）', len(_scroll_calls) >= 1, str(len(_scroll_calls)))

before = len(_scroll_calls)
api['table_update']()          # 普通重建（排序/编辑/删除等场景）
after_rebuild = len(_scroll_calls)
ok('普通重建不再跳底', after_rebuild == before, f'{before} -> {after_rebuild}')

# 首次打开式重建显式传 scroll_to_bottom=True 时应真正跳到底部。
# 注意：跳底延到事件循环下一轮执行（等布局算好视口高度），故需 processEvents 后再断言位置。
app.processEvents()
api['table_update'](scroll_to_bottom=True)
for _ in range(6):
    app.processEvents()
bar_after = api['get_table']().verticalScrollBar()
ok('显式 scroll_to_bottom=True 会跳到底部',
   bar_after.value() == bar_after.maximum() and bar_after.maximum() > 0,
   f'{bar_after.value()} / {bar_after.maximum()}')

print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)

_cleanup()
atexit.unregister(_cleanup)
sys.exit(0 if all(PASS) else 1)
