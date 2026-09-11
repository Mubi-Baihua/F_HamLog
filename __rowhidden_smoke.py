# -*- coding: utf-8 -*-
"""临时冒烟：验证过滤后视图真正重排（匹配项置顶、不匹配行不再占位）。"""
import sys
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from satellite_window import SatelliteSelectDialog

# 造 200 颗，把目标放在很靠后的位置（模拟真实 TLE 里卫星排在后面）
names = [f'DUMMY-{i:03d}' for i in range(200)]
target_row = 150
names[target_row] = 'XW-2F'
names[target_row + 1] = 'SAUDISAT 1C (SO-50)'
names[3] = 'SO-50'

dlg = SatelliteSelectDialog(None, names, set())
dlg.resize(360, 480)
dlg.show()
app.processEvents()

lw = dlg.list_widget


def probe(text, want_row):
    dlg.search_edit.setText(text)
    app.processEvents()
    vis_rows = [r for r in range(lw.count()) if not lw.isRowHidden(r)]
    item = dlg.items['XW-2F'] if 'XW-2F' in dlg.items else dlg.items['SO-50']
    rect = lw.visualItemRect(item)
    print(f'{text!r:8} 可见行={vis_rows[:6]}{"..." if len(vis_rows) > 6 else ""} '
          f'共{len(vis_rows)}行 | 目标项 y={rect.y():.0f} h={rect.height():.0f} '
          f'| 计数="{dlg.count_label.text()}"')
    return vis_rows, rect.y()


# 无搜索：全部可见，目标在其原始位置（y 远大于 0）
vis0, y0 = probe('', target_row)
assert len(vis0) == 200, vis0.__len__()

# 搜索：只留 1 行，且该行必须被布局到视口顶部（y == 0），
# 这是"视图已重排"的判据；若只是改了标志而未重排，y 仍会是 150*行高。
vis1, y1 = probe('xw 2f', target_row)
ok_layout = (vis1 == [target_row]) and (y1 == 0)
print('布局已重排(匹配项置顶):', ok_layout, f'(原 y={y0:.0f} → 过滤后 y={y1:.0f})')

# 多命中：两行都可见且连续出现在顶部
dlg.search_edit.setText('so50')
app.processEvents()
vis2 = [r for r in range(lw.count()) if not lw.isRowHidden(r)]
y_first = lw.visualItemRect(dlg.items['SO-50']).y()
print('so50 ->', vis2, 'first y =', y_first, '| 计数 =', dlg.count_label.text())
ok_multi = (vis2 == [3, target_row + 1]) and y_first == 0

print('RESULT:', 'OK' if (ok_layout and ok_multi) else 'FAIL')
