# -*- coding: utf-8 -*-
"""临时冒烟：验证 SatelliteSelectDialog「未搜索时已选卫星置顶」。

覆盖：
  1) 初始未搜索：已选项置顶（保持各自原有相对顺序）
  2) 未搜索时取消勾选（最靠前的已选）：该项掉到剩余已选之后
  3) 未搜索时新勾选：新项加入顶部已选组
  4) 搜索中：只显示匹配项，且搜索时不重排
  5) 清空搜索：重新置顶当前已选集合
  6) get_selected 返回值正确
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)

from satellite_window import SatelliteSelectDialog

# 200 颗；目标放在靠后位置（模拟真实 TLE 里卫星排在后面）
names = [f'DUMMY-{i:03d}' for i in range(200)]
names[3] = 'SO-50'
names[10] = 'DUMMY-010'
names[150] = 'XW-2F'

# 原始相对顺序按行号：SO-50(3) < DUMMY-010(10) < XW-2F(150)
selected = {'SO-50', 'DUMMY-010', 'XW-2F'}
dlg = SatelliteSelectDialog(None, names, selected)
dlg.resize(360, 480)
dlg.show()
app.processEvents()
lw = dlg.list_widget

results = []


def top(n=3):
    return [lw.item(i).text() for i in range(min(n, lw.count()))]


def vis_rows():
    return [r for r in range(lw.count()) if not lw.isRowHidden(r)]


def row_of(name):
    return dlg._row_names.index(name)


# 1) 初始未搜索：已选置顶（按原相对顺序 SO-50, DUMMY-010, XW-2F）
t = top(3)
ok1 = (t == ['SO-50', 'DUMMY-010', 'XW-2F']) and len(vis_rows()) == 200
results.append(('初始未搜索已选置顶', ok1))
print(f'1) 顶部={t} 共可见={len(vis_rows())} 计数={dlg.count_label.text()!r}')

# 2) 取消勾选最靠前的已选 SO-50 → 掉到剩余已选（DUMMY-010, XW-2F）之后
dlg.items['SO-50'].setCheckState(Qt.CheckState.Unchecked)
app.processEvents()
t = top(2)
ok2 = (t == ['DUMMY-010', 'XW-2F']) and (row_of('SO-50') >= 2)
results.append(('取消勾选后掉出置顶组', ok2))
print(f'2) 取消 SO-50 后顶部={t} SO-50 行号={row_of("SO-50")}')

# 3) 新勾选 DUMMY-020 → 加入顶部已选组（排在原已选之后，因原行号更靠后）
dlg.items['DUMMY-020'].setCheckState(Qt.CheckState.Checked)
app.processEvents()
t = top(3)
ok3 = (t == ['DUMMY-010', 'XW-2F', 'DUMMY-020'])
results.append(('新勾选加入置顶组', ok3))
print(f'3) 勾选 DUMMY-020 后顶部={t}')

# 4) 搜索 xw 2f：只显示匹配项，且搜索中不打乱顺序（不重排）
before_order = list(dlg._row_names)
dlg.search_edit.setText('xw 2f')
app.processEvents()
vr = vis_rows()
ok4 = (vr == [row_of('XW-2F')]) and (list(dlg._row_names) == before_order)
results.append(('搜索仅显示匹配项且不重排', ok4))
print(f'4) 搜索"xw 2f" 可见行={vr} 计数={dlg.count_label.text()!r}')

# 5) 清空搜索：重新置顶当前已选（DUMMY-010, XW-2F, DUMMY-020）
dlg.search_edit.setText('')
app.processEvents()
t = top(3)
ok5 = (t == ['DUMMY-010', 'XW-2F', 'DUMMY-020']) and len(vis_rows()) == 200
results.append(('清空搜索重新置顶', ok5))
print(f'5) 清空搜索后顶部={t} 共可见={len(vis_rows())} 计数={dlg.count_label.text()!r}')

# 6) get_selected 正确
sel = dlg.get_selected()
ok6 = (sel == {'DUMMY-010', 'XW-2F', 'DUMMY-020'})
results.append(('get_selected 正确', ok6))
print(f'6) get_selected={sorted(sel)}')

print('---')
allok = all(v for _, v in results)
for name, v in results:
    print(('PASS ' if v else 'FAIL ') + name)
print('RESULT:', 'ALL_OK' if allok else 'FAIL')
