"""悬浮提示框（toast_tip）冒烟：构造、堆叠、主题取色、1 秒自动关闭。

不依赖真实项目数据，仅在离屏下验证控件行为。
用法：python __toast_smoke.py
产物：__toast_out.txt
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import toast_tip  # noqa: E402
import theme  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

app = QApplication(sys.argv)
theme.init_app(app)

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))


def pump(ms=50):
    for _ in range(max(1, ms // 10)):
        app.processEvents()


# 父窗口
win = QMainWindow()
win.setGeometry(100, 100, 800, 600)
win.show()
pump()

# 1. 基本构造
t1 = toast_tip.show_toast('已复制 3 条日志到剪贴板。', win)
ok('show_toast 返回控件', t1 is not None)
ok('控件已加入在屏列表', t1 in toast_tip._ACTIVE, 'count=%d' % len(toast_tip._ACTIVE))
ok('控件有可见尺寸', t1.width() > 0 and t1.height() > 0,
   '%dx%d' % (t1.width(), t1.height()))
ok('控件可见', t1.isVisible())

# 2. 原地堆叠：再弹一个，直接盖在同一屏幕上方位置，旧提示不挪动
t2 = toast_tip.show_toast('已粘贴 5 条日志。', win)
ok('两个提示同时在屏', len(toast_tip._ACTIVE) == 2, 'count=%d' % len(toast_tip._ACTIVE))
ok('原地堆叠（同一 y）', t1.y() == t2.y(),
   't1.y=%d t2.y=%d' % (t1.y(), t2.y()))
ok('显示在屏幕上方', t1.y() <= 40, 'y=%d' % t1.y())

# 3. 警告类取语义红
t3 = toast_tip.show_toast('剪贴板内容无法识别为日志数据。', win, kind='warning')
ok('警告提示使用了警告色', t3._fg.name() == theme.warn_color().name(), t3._fg.name())

# 4. 无父窗口也能用（center of screen）
t4 = toast_tip.show_toast('无父窗口提示', None)
ok('无父窗口提示可构造', t4 is not None and t4.isVisible())

# 5. 1 秒后自动关闭（从创建起约 1.4s）
elapsed = 0
while elapsed < 1600:
    time.sleep(0.05)
    pump()
    elapsed += 50
ok('1 秒后自动关闭并退屏', len(toast_tip._ACTIVE) == 0, 'count=%d' % len(toast_tip._ACTIVE))

# 6. 关闭事件回收：手动关一个也能从列表移除
t5 = toast_tip.show_toast('手动关闭测试', win)
ok('创建后在屏', len(toast_tip._ACTIVE) == 1)
t5.close()
pump()
ok('close 后从列表移除', t5 not in toast_tip._ACTIVE)

win.close()
pump()

# 输出
lines = []
n_fail = 0
for status, name, extra in results:
    if status == 'FAIL':
        n_fail += 1
    lines.append('[%s] %s%s' % (status, name, ('  <- ' + extra) if extra else ''))
lines.append('')
lines.append('合计：%d 项，失败 %d 项' % (
    len([r for r in results if r[0] in ('PASS', 'FAIL')]), n_fail))
text = '\n'.join(lines)
with open(os.path.join(HERE, '__toast_out.txt'), 'w', encoding='utf-8') as f:
    f.write(text + '\n')
print(text)
sys.exit(1 if n_fail else 0)
