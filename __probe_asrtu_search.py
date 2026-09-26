# -*- coding: utf-8 -*-
"""临时探针：在**真实的卫星过境预测窗口**里打开「选择卫星」，输入 ASRTU-1 看是否命中。

不构造合成列表，完全走 satellite_window.main() 的真实 `sats`/`names` 通路，
以排除"合成数据能命中、真实窗口不能命中"的可能。
"""
import os
import shutil
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

import satellite_pred as sp  # noqa: E402
import satellite_window as sw  # noqa: E402

SETTINGS = os.path.join(PROJECT_DIR, 'file', 'm_xml.txt')
bak = SETTINGS + '.asrtu_bak'
shutil.copyfile(SETTINGS, bak)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)

seen = {}


def probe_exec(self):
    """捕获真实对话框：记录总项数，并分别用几种输入试搜。"""
    seen['dialog'] = self
    seen['count'] = self.list_widget.count()
    seen['has_target'] = 'ASRTU-1 (RS64S/BJ2CR)' in self.items
    for q in ('ASRTU-1', 'asrtu-1', 'ASRTU-1 (RS64S/BJ2CR)', 'ASRTU'):
        self.search_edit.setText(q)
        app.processEvents()
        vis = [self._row_names[r] for r in range(self.list_widget.count())
               if not self.list_widget.isRowHidden(r)]
        seen[q] = (len(vis), vis[:3], self.count_label.text())
    return QDialog.Rejected


sw.ObserverDialog.exec = lambda self: QDialog.Rejected
sw.SatelliteSelectDialog.exec = probe_exec

try:
    sw.main(None)
    win = sw._open_windows[-1]
    for _ in range(600):
        app.processEvents()
        time.sleep(0.01)
        if 'dialog' in seen:
            break
    app.processEvents()
finally:
    shutil.copyfile(bak, SETTINGS)
    os.remove(bak)

print('列表总项数 :', seen.get('count'))
print('列表含 ASRTU-1 (RS64S/BJ2CR) :', seen.get('has_target'))
for q in ('ASRTU-1', 'asrtu-1', 'ASRTU-1 (RS64S/BJ2CR)', 'ASRTU'):
    n, sample, label = seen.get(q, ('-', '-', '-'))
    print('  搜 %-24r → 命中 %s 项  样例=%s  | 计数=%s' % (q, n, sample, label))
