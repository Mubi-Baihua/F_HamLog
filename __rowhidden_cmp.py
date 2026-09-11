# -*- coding: utf-8 -*-
"""临时对比：QListWidgetItem.setHidden vs QListWidget.setRowHidden 的布局差异。"""
import sys
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

app = QApplication(sys.argv)
names = [f'D-{i}' for i in range(50)]
names[40] = 'XW-2F'


def build(use_row_hidden):
    lw = QListWidget()
    items = {}
    for n in names:
        items[n] = QListWidgetItem(n, lw)
    lw.resize(300, 400)
    lw.show()
    app.processEvents()
    for row, n in enumerate(names):
        hide = (n != 'XW-2F')
        if use_row_hidden:
            lw.setRowHidden(row, hide)
        else:
            items[n].setHidden(hide)
    app.processEvents()
    return lw, items


for flag, label in ((False, 'item.setHidden(旧)'), (True, 'list.setRowHidden(新)')):
    lw, items = build(flag)
    y = lw.visualItemRect(items['XW-2F']).y()
    vis = [r for r in range(lw.count()) if not lw.isRowHidden(r)]
    print(f'{label:24} 目标项 y={y:6.0f}  可见行={vis}  isRowHidden(0)={lw.isRowHidden(0)}')
    print(f'{"":24} -> {"布局已重排：匹配项在顶部" if y == 0 else "布局未重排：仍停在原位(视觉未过滤)"}')
