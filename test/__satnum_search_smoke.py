# -*- coding: utf-8 -*-
"""冒烟：「使用卫星编号搜索」复选框（默认关闭）+ 全角输入。

覆盖：
  1. 默认关闭 —— 搜索框只按卫星名匹配，输入编号 61781 无命中；
  2. 勾选开关（**不改搜索词**）即重新过滤 —— 命中 ASRTU-1 (RS64S/BJ2CR)；
  3. 勾选开关不削减原有的名称搜索能力（asrtu / rs64s 仍命中）；
  4. 编号归一化：061781 与 61781 等价，6178 前缀模糊命中；
  5. 提示语随开关切换；
  6. 不传编号表（satnums=None）时旧的两参/三参调用方式照常可用；
  7. **全角输入**（中文输入法「全角」模式）等价于半角：ＡＳＲＴＵ－１ / ６１７８１。
"""
import sys
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

import satellite_pred as sp
import satellite_window as sw
from satellite_window import SatelliteSelectDialog

TARGET = 'ASRTU-1 (RS64S/BJ2CR)'
with open(sw.TLE_CACHE, encoding='utf-8-sig') as f:
    sats = sp.parse_tle_text(f.read())
names = [n for (n, s) in sats]
satnums = sp.satellite_number_map(sats)
assert TARGET in names, '星历里应有 ASRTU-1'
assert str(satnums[TARGET]) == '61781', satnums[TARGET]

fails = []


def check(ok, msg):
    print(('  [OK]   ' if ok else '  [FAIL] ') + msg)
    if not ok:
        fails.append(msg)


dlg = SatelliteSelectDialog(None, names, set(), satnums)
dlg.show()
app.processEvents()
lw = dlg.list_widget


def visible():
    """当前可见卫星名（不修改搜索框/开关状态）。"""
    app.processEvents()
    return [dlg._row_names[r] for r in range(lw.count()) if not lw.isRowHidden(r)]


# 1. 默认关闭 + 按编号搜不到
print('1) 默认状态')
check(not dlg.by_number_chk.isChecked(), '开关默认关闭')
check(dlg.search_edit.placeholderText() == '搜索卫星名…',
      '默认提示语为「搜索卫星名…」，实际=%r' % dlg.search_edit.placeholderText())
dlg.search_edit.setText('61781')
vis = visible()
print('     未勾选搜 61781 -> 命中 %d 颗 | %s' % (len(vis), dlg.count_label.text()))
check(vis == [], '未勾选开关时，编号 61781 不应命中任何卫星')
check('匹配 0' in dlg.count_label.text(), '未勾选时计数应显示「匹配 0」')

# 2. 勾选开关（搜索词保持不变）应立即重新过滤
print('2) 勾选开关后（不动搜索词）')
dlg.by_number_chk.setChecked(True)
vis = visible()
print('     已勾选搜 61781 -> %s | %s' % (vis, dlg.count_label.text()))
check(vis == [TARGET], '勾选后应精确命中 %s' % TARGET)
check(dlg.search_edit.placeholderText() == '搜索卫星名或编号…',
      '勾选后提示语应变为「搜索卫星名或编号…」，实际=%r'
      % dlg.search_edit.placeholderText())

# 3. 名称搜索不受影响
print('3) 勾选状态下按名称搜索')
for q in ('asrtu', 'rs64s', 'bj2cr', 'asrtu-1 (rs64s'):
    dlg.search_edit.setText(q)
    vis = visible()
    check(TARGET in vis, '勾选后搜 %r 仍能命中（命中 %d 颗）' % (q, len(vis)))

# 4. 编号归一化
print('4) 编号归一化 / 前缀模糊')
dlg.search_edit.setText('061781')
vis = visible()
check(TARGET in vis, '061781（前导 0）应等价于 61781')
dlg.search_edit.setText('6178')
vis = visible()
check(TARGET in vis, '6178 前缀应模糊命中 61781（共 %d 颗）' % len(vis))

# 5. 关掉开关 → 回到纯名称匹配
print('5) 关掉开关')
dlg.search_edit.setText('61781')
dlg.by_number_chk.setChecked(False)
vis = visible()
check(vis == [], '关闭开关后编号搜索立即失效')
check(dlg.search_edit.placeholderText() == '搜索卫星名…', '关闭后提示语复原')

# 6. 兼容旧调用（无编号表）
print('6) 向后兼容：不传编号表')
dlg2 = SatelliteSelectDialog(None, ['DUMMY-1', 'DUMMY-2'], set())
dlg2.by_number_chk.setChecked(True)


def visible2():
    app.processEvents()
    return [dlg2._row_names[r] for r in range(dlg2.list_widget.count())
            if not dlg2.list_widget.isRowHidden(r)]


check(not dlg2._norm_num or set(dlg2._norm_num.values()) == {''},
      '未传编号表时编号缓存全为空串')
dlg2.search_edit.setText('999')
check(visible2() == [], '未传编号表：编号搜索不误命中')
dlg2.search_edit.setText('1')
check(visible2() == ['DUMMY-1'], '未传编号表：名称搜索照常可用（DUMMY-1）')

# 7. 全角输入（中文输入法「全角」模式）等价于半角
#    全角字母/数字同样能通过 isalnum() 过滤，若不折叠就永远匹配不上半角名称，
#    表现为「明明输入了 ASRTU-1 却搜不到」。
print('7) 全角输入')
FW_NAME = '\uFF21\uFF33\uFF32\uFF34\uFF35\uFF0D\uFF11'          # ＡＳＲＴＵ－１
FW_NUM = '\uFF16\uFF11\uFF17\uFF18\uFF11'                        # ６１７８１
FW_FULL = ('\uFF21\uFF33\uFF32\uFF34\uFF35\uFF0D\uFF11'          # ＡＳＲＴＵ－１
           '\uFF08\uFF32\uFF33\uFF16\uFF14\uFF33\uFF0F'
           '\uFF22\uFF2A\uFF12\uFF23\uFF32\uFF09')               # （ＲＳ６４Ｓ／ＢＪ２ＣＲ）
dlg.by_number_chk.setChecked(False)
dlg.search_edit.setText(FW_NAME)
check(visible() == [TARGET], '全角 ＡＳＲＴＵ－１ 按名称应命中（开关关闭时也成立）')
dlg.search_edit.setText(FW_FULL)
check(visible() == [TARGET], '全角完整名（含全角括号/斜杠）也应命中')
dlg.by_number_chk.setChecked(True)
dlg.search_edit.setText(FW_NUM)
check(visible() == [TARGET], '全角编号 ６１７８１ 勾选开关后应命中')

print('RESULT:', 'OK' if not fails else 'FAIL(%d)' % len(fails))
sys.exit(1 if fails else 0)
