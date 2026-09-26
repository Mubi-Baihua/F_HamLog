"""三模式（跟随系统／浅色／深色）冒烟：模式读写、即时生效、窗口取色对比度、静态扫描。

不污染用户数据：
  - theme.settings_path 指向临时设置文件（含其它键，用于验证不被破坏）；
  - backup.BATCH_BACKUP 指向临时文件；
  - 只在临时目录里 chdir 做「设置窗口」用例。

用法：python __theme_mode_smoke.py
产物：__theme_mode_out.txt / __theme_mode_out.png
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import backup  # noqa: E402
import theme  # noqa: E402

TMP = tempfile.mkdtemp(prefix='__theme_smoke_')
TMP_SETTINGS = os.path.join(TMP, 'm_xml.txt')
TMP_FILE_DIR = os.path.join(TMP, 'file')
os.makedirs(TMP_FILE_DIR, exist_ok=True)

# 初始设置文件：带上其它键，验证写 theme_mode 时不会破坏既有设置
_SEED = {'m_call': 'BI8SQL', 'm_qth': '成都', 'm_lat': 30.0, 'm_lon': 104.0}
with open(TMP_SETTINGS, 'w', encoding='utf-8') as f:
    f.write(str(_SEED))
with open(os.path.join(TMP_FILE_DIR, 'm_xml.txt'), 'w', encoding='utf-8') as f:
    f.write(str(_SEED))

theme.settings_path = lambda: TMP_SETTINGS      # 只读/只写临时设置
backup.BATCH_BACKUP = os.path.join(TMP, 'batch_backup.fhl')

from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QComboBox,  # noqa: E402
                               QCheckBox, QSpinBox)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette, QColor  # noqa: E402

app = QApplication(sys.argv)

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))


def pump(n=5):
    for _ in range(n):
        app.processEvents()


def contrast(fg, bg):
    """WCAG 对比度（1=无对比，21=黑白色）。"""
    def lum(c):
        def ch(v):
            v = v / 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())
    l1, l2 = sorted([lum(fg), lum(bg)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


# ---------------------------------------------------------------------------
# 1. 颜色模式的读写
# ---------------------------------------------------------------------------
ok('默认模式=跟随系统', theme.load_mode() == theme.MODE_SYSTEM, theme.load_mode())

for mode in (theme.MODE_DARK, theme.MODE_LIGHT, theme.MODE_SYSTEM):
    theme.save_mode(mode)
    ok('保存并读回 %s' % mode, theme.load_mode() == mode, theme.load_mode())

theme.save_mode('不存在的模式')
ok('非法值回退跟随系统', theme.load_mode() == theme.MODE_SYSTEM, theme.load_mode())

saved = theme.read_settings()
ok('写模式不破坏其它键', saved.get('m_call') == 'BI8SQL' and saved.get('m_lat') == 30.0,
   str(sorted(saved)))
ok('theme_mode 已落盘', saved.get(theme.MODE_KEY) == theme.MODE_SYSTEM)

# ---------------------------------------------------------------------------
# 2. 三种模式的应用效果（调色板 + 主题取色）
#    语义：以跟随系统的观感为准 —— 平台给出对应明暗的调色板就直接用，
#    平台给不出（离屏 fusion 不认 setColorScheme）才用自建调色板兜底。
#    离屏下：深色 → 兜底；浅色 → 平台（fusion 默认 #efefef）
# ---------------------------------------------------------------------------
EXPECT = {
    theme.MODE_DARK: {'dark': True, 'window': '#353535', 'text': '#ffffff',
                      'src': 'fallback'},
    theme.MODE_LIGHT: {'dark': False, 'window': '#efefef', 'text': '#000000',
                       'src': 'platform'},
}

for mode in (theme.MODE_DARK, theme.MODE_LIGHT):
    theme.set_mode(mode, app)
    pump()
    exp = EXPECT[mode]
    win_bg = app.palette().color(QPalette.Window)
    ok('%s: is_dark=%s' % (mode, exp['dark']), theme.is_dark() == exp['dark'],
       str(theme.is_dark()))
    ok('%s: Window=%s' % (mode, exp['window']), win_bg.name() == exp['window'], win_bg.name())
    ok('%s: 正文色=%s' % (mode, exp['text']),
       app.palette().color(QPalette.Text).name() == exp['text'],
       app.palette().color(QPalette.Text).name())
    ok('%s: 调色板来源=%s' % (mode, exp['src']), theme._last_source == exp['src'],
       str(theme._last_source))
    c = contrast(theme.hint_color(), win_bg)
    ok('%s: 次要文字对比度≥4.5' % mode, c >= 4.5, '%.2f:1 %s' % (
        c, theme.hint_color().name()))
    c = contrast(theme.warn_color(), win_bg)
    ok('%s: 警告色对比度≥4.5' % mode, c >= 4.5, '%.2f:1 %s' % (
        c, theme.warn_color().name()))
    c = contrast(theme.link_color(), win_bg)
    ok('%s: 链接色对比度≥4.5' % mode, c >= 4.5, '%.2f:1 %s' % (
        c, theme.link_color().name()))

# ---- 平台优先：平台给的调色板符合目标明暗时必须原样采用（这才是「以系统为准」） ----
p = QPalette()
p.setColor(QPalette.Window, QColor('#1e1e1e'))       # 模拟 Windows 11 深色
p.setColor(QPalette.WindowText, QColor('#ffffff'))
app.setPalette(p)
src = theme._adopt_platform_palette(app, True)
ok('平台已是深色 → 不覆盖（手动深色=系统深色）',
   src == 'platform' and app.palette().color(QPalette.Window).name() == '#1e1e1e',
   '%s %s' % (src, app.palette().color(QPalette.Window).name()))

app.setPalette(QPalette())
src = theme._adopt_platform_palette(app, True)
ok('平台给不出深色 → 用兜底深色',
   src == 'fallback' and app.palette().color(QPalette.Window).name() == '#353535',
   '%s %s' % (src, app.palette().color(QPalette.Window).name()))

app.setPalette(QPalette())
src = theme._adopt_platform_palette(app, None)
ok('系统配色未知 → 不干预（保持平台原样）',
   src == 'system' and app.palette().color(QPalette.Window).name() == '#efefef',
   '%s %s' % (src, app.palette().color(QPalette.Window).name()))

# ---- 「跟随系统」按探测到的系统方案决定明暗 ----
_real_scheme = theme.system_scheme
try:
    theme.system_scheme = lambda: Qt.ColorScheme.Dark
    theme.set_mode(theme.MODE_SYSTEM, app)
    pump()
    ok('跟随系统(系统=深色) → 按深色处理', theme._want_dark() is True
       and theme.is_dark(), 'want_dark=%s Window=%s'
       % (theme._want_dark(), app.palette().color(QPalette.Window).name()))
    theme.system_scheme = lambda: Qt.ColorScheme.Light
    theme.set_mode(theme.MODE_SYSTEM, app)
    pump()
    ok('跟随系统(系统=浅色) → 按浅色处理', theme._want_dark() is False
       and not theme.is_dark(), 'want_dark=%s Window=%s'
       % (theme._want_dark(), app.palette().color(QPalette.Window).name()))
finally:
    theme.system_scheme = _real_scheme

# ---- 系统配色变化时的监听器：强制模式要守住自己请求的方案 ----
ok('已注册 colorSchemeChanged 监听器', theme._scheme_hook is not None)
for mode, want_dark in ((theme.MODE_DARK, True), (theme.MODE_LIGHT, False)):
    theme.set_mode(mode, app)
    before = theme.is_dark()
    theme._scheme_hook()        # 模拟系统配色变化
    pump()
    ok('%s: 系统配色变化后仍保持本模式' % mode,
       theme.is_dark() == want_dark and before == want_dark,
       'is_dark=%s' % theme.is_dark())
theme.set_mode(theme.MODE_SYSTEM, app)
pump()

# 跟随系统：交回调色板（离屏探测不到系统配色），不应残留上一模式的覆盖
theme.set_mode(theme.MODE_SYSTEM, app)
pump()
ok('跟随系统: 交回默认调色板', app.palette().color(QPalette.Window).name() == '#efefef',
   app.palette().color(QPalette.Window).name())

# ---------------------------------------------------------------------------
# 3. 批量记录窗口：三种模式下的实际渲染取色
# ---------------------------------------------------------------------------
os.chdir(HERE)
import batch_project  # noqa: E402

shots = []
for mode in (theme.MODE_DARK, theme.MODE_LIGHT, theme.MODE_SYSTEM):
    theme.set_mode(mode, app)
    pump()
    win = QMainWindow()
    batch_project.main(win)
    win.show()
    pump()
    table = win.findChildren(batch_project.FrozenTableWidget)[0]
    clock = [lb for lb in win.findChildren(QLabel) if 'UTC' in lb.text()][0]
    hint = [lb for lb in win.findChildren(QLabel) if '快捷键' in lb.text()][0]

    bg = win.palette().color(QPalette.Window)
    c_clock = contrast(QColor(clock.styleSheet().split('color:')[-1].split(';')[0]), bg)
    c_hint = contrast(QColor(hint.styleSheet().split('color:')[-1].split(';')[0]), bg)
    ok('%s: 批量记录 时钟对比度≥4.5' % mode, c_clock >= 4.5, '%.2f:1' % c_clock)
    ok('%s: 批量记录 提示对比度≥4.5' % mode, c_hint >= 4.5, '%.2f:1' % c_hint)

    frozen_bg = QColor(table._frozen.styleSheet().split('background-color:')[-1].rstrip('; }'))
    frozen_fg = table._frozen.palette().color(QPalette.Text)
    c_frozen = contrast(frozen_fg, frozen_bg)
    ok('%s: 冻结列对比度≥4.5' % mode, c_frozen >= 4.5,
       '%.2f:1 bg=%s fg=%s' % (c_frozen, frozen_bg.name(), frozen_fg.name()))

    png = os.path.join(HERE, '__theme_mode_%s_out.png' % mode)
    win.grab().save(png)
    shots.append(png)
    win.close()

# ---------------------------------------------------------------------------
# 4. 设置窗口：颜色模式下拉即时生效 + 落盘
# ---------------------------------------------------------------------------
os.chdir(TMP)
import set as set_mod  # noqa: E402

sw = QMainWindow()
set_mod.main(sw)
sw.show()
pump()

boxes = [b for b in sw.findChildren(QComboBox)]
ok('设置窗口出现「颜色模式」下拉', len(boxes) >= 1, 'combobox 数=%d' % len(boxes))
ok('下拉前有「颜色模式:」标签',
   any(lb.text() == '颜色模式:' for lb in sw.findChildren(QLabel)))
if boxes:
    box = boxes[0]
    labels = [box.itemText(i) for i in range(box.count())]
    ok('下拉项为 跟随系统/浅色/深色',
       labels == ['跟随系统', '浅色', '深色'], str(labels))
    ok('当前项与已保存模式一致',
       box.currentData() == theme.load_mode(), str(box.currentData()))

    dark_idx = box.findData(theme.MODE_DARK)
    box.setCurrentIndex(dark_idx)          # 模拟用户选择「深色」
    pump()
    ok('选深色 → 立即生效', theme.current_mode() == theme.MODE_DARK,
       theme.current_mode())
    ok('选深色 → 立即落盘',
       theme.read_settings().get(theme.MODE_KEY) == theme.MODE_DARK,
       str(theme.read_settings().get(theme.MODE_KEY)))

    # 深色下截一张设置窗口图，并确认「颜色模式」并入开关行后没把布局挤坏
    png = os.path.join(HERE, '__theme_mode_set_out.png')
    sw.grab().save(png)
    shots.append(png)
    cw = sw.centralWidget()

    # 1) 「自动保存」与「颜色模式」必须落在同一水平行
    row_items = ([c for c in sw.findChildren(QCheckBox)]
                 + boxes
                 + [lb for lb in sw.findChildren(QLabel)
                    if lb.text() in ('更新间隔:', '颜色模式:')]
                 + [sp for sp in sw.findChildren(QSpinBox)])
    ok('设置窗口找到待检查的一行控件', len(row_items) >= 4, '控件数=%d' % len(row_items))
    if cw is not None and row_items:
        ys = [w.mapTo(cw, w.rect().center()).y() for w in row_items]
        ok('自动保存与颜色模式在同一行', max(ys) - min(ys) <= 2,
           '行中心 y=%s' % sorted(set(ys)))

        # 2) 横向：一行内每个控件都没被压缩、也没越过右边界
        squeezed = ['%s %d<%d' % (w.__class__.__name__, w.width(), w.sizeHint().width())
                    for w in row_items if w.width() < w.sizeHint().width()]
        ok('一行内控件未被压缩', not squeezed, ' | '.join(squeezed))
        over = [w.__class__.__name__ for w in row_items
                if (w.mapTo(cw, w.rect().topLeft()).x() + w.width()) > cw.width()]
        ok('一行内控件未超出窗口宽度', not over, ' | '.join(over))

        # 3) 纵向：合并后内容所需高度不应超过窗口可视高度（否则会被压扁）
        need = cw.layout().sizeHint().height()
        ok('设置窗口高度仍有余量（无需加高）', need <= cw.height(),
           '内容需要 %d，可视 %d' % (need, cw.height()))

    light_idx = box.findData(theme.MODE_LIGHT)
    box.setCurrentIndex(light_idx)
    pump()
    ok('选浅色 → 立即生效', theme.current_mode() == theme.MODE_LIGHT,
       theme.current_mode())
    ok('选浅色 → 立即落盘',
       theme.read_settings().get(theme.MODE_KEY) == theme.MODE_LIGHT,
       str(theme.read_settings().get(theme.MODE_KEY)))
    ok('设置窗口仍保留其它设置键',
       theme.read_settings().get('m_call') == 'BI8SQL')
sw.close()

# ---------------------------------------------------------------------------
# 5. 静态扫描：主要界面文件里不得再有写死的界面颜色
# ---------------------------------------------------------------------------
os.chdir(HERE)
SCAN = {
    'batch_project.py': [],
    'project.py': [],
    'set.py': [],
    'satellite_window.py': [],
    'mutual_window.py': [],
    'tle_source_window.py': [],
    'satellite_map_window.py': [],
}
# 允许保留：产品主色按钮（main.py 的 ACCENT 白字蓝底）、地图绘制语义色（QColor(...) 常量）
ALLOW_SUBSTR = ('ACCENT', 'QPushButton{background', 'QColor(', 'painter', 'QPainter')
BAD_SUBSTR = ("'color: gray", '"color: gray', "'color: #", '"color: #',
              "'color:#", '#f3f3f3', '#c0392b', "'background: #", '"background: #')

for fname in SCAN:
    path = os.path.join(HERE, fname)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError as e:
        ok('扫描 %s' % fname, False, str(e))
        continue
    hits = []
    # 只看 setStyleSheet(...) 调用（含跨行书写）：注释/docstring 里提到颜色字样不算问题
    for i, line in enumerate(lines):
        if 'setStyleSheet' not in line:
            continue
        chunk = ''.join(lines[i:i + 3])
        if any(sub in chunk for sub in ALLOW_SUBSTR):
            continue
        for bad in BAD_SUBSTR:
            if bad in chunk:
                hits.append('%d:%s' % (i + 1, line.strip()))
                break
    ok('扫描 %s 无写死界面颜色' % fname, not hits, ' | '.join(hits[:4]))

# 未纳入改动、仅需报告的旧文件
for fname in ('#remote_project.py',
              'F_HamLog_Remote_Log_Server_2.0.0/main.py'):
    results.append(('INFO', '未处理（历史/独立分发）', fname))

# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
lines = []
n_fail = 0
for status, name, extra in results:
    if status == 'FAIL':
        n_fail += 1
    lines.append('[%s] %s%s' % (status, name, ('  <- ' + extra) if extra else ''))
lines.append('')
lines.append('合计：%d 项，失败 %d 项' % (
    len([r for r in results if r[0] in ('PASS', 'FAIL')]), n_fail))
lines.append('截图：%s' % ', '.join(os.path.basename(p) for p in shots))

text = '\n'.join(lines)
with open(os.path.join(HERE, '__theme_mode_out.txt'), 'w', encoding='utf-8') as f:
    f.write(text + '\n')
print(text)
sys.exit(1 if n_fail else 0)
