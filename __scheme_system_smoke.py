"""真实桌面平台下验证「以跟随系统的为准」：手动浅色/深色 == 系统对应明暗的调色板。

- 需要真实桌面（Windows 平台插件），**勿在 CI/离屏跑**；
- 不显示任何窗口、不改系统设置（只读注册表判断系统当前明暗）；
- 只做取证与断言，不写任何数据文件。

用法：python __scheme_system_smoke.py      产物：__scheme_system_out.txt
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import theme  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette, QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

results = []


def ok(name, cond, extra=''):
    results.append(('PASS' if cond else 'FAIL', name, extra))


def contrast(fg, bg):
    def lum(c):
        def ch(v):
            v = v / 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())
    l1, l2 = sorted([lum(fg), lum(bg)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


ROLES = (QPalette.Window, QPalette.Base, QPalette.Button, QPalette.Text,
         QPalette.Mid, QPalette.Highlight, QPalette.Link)


def roles_of(pal):
    return {str(r).split('.')[-1]: pal.color(r).name() for r in ROLES}


def os_theme():
    """系统当前的应用明暗（只读注册表）；读不到返回 '未知'。"""
    try:
        import winreg
        key = r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            val, _ = winreg.QueryValueEx(k, 'AppsUseLightTheme')
        return '浅色' if val else '深色'
    except Exception as e:  # noqa: BLE001
        return '未知(%s)' % e


app = QApplication(sys.argv)
hints = app.styleHints()

out = []
out.append('平台风格: %s   Qt %s' % (app.style().objectName(), Qt.__version__
                                 if hasattr(Qt, '__version__') else ''))
out.append('系统当前明暗（注册表 AppsUseLightTheme）: %s' % os_theme())
out.append('')

snap = {}
for mode, label in ((theme.MODE_SYSTEM, '跟随系统'),
                    (theme.MODE_LIGHT, '手动浅色'),
                    (theme.MODE_DARK, '手动深色')):
    theme.set_mode(mode, app)
    for _ in range(3):
        app.processEvents()
    pal = QPalette(app.palette())
    snap[mode] = {
        'label': label,
        'roles': roles_of(pal),
        'src': theme._last_source,
        'scheme': str(hints.colorScheme()),
        'pal': pal,
        'hint': theme.hint_color().name(),
        'warn': theme.warn_color().name(),
        'link': theme.link_color().name(),
    }

for mode in (theme.MODE_SYSTEM, theme.MODE_LIGHT, theme.MODE_DARK):
    s = snap[mode]
    out.append('%-6s scheme=%-14s 来源=%-9s %s' % (
        s['label'], s['scheme'], s['src'],
        ' '.join('%s=%s' % (k, v) for k, v in s['roles'].items())))
out.append('')

# ---- 1) 核心性质：跟随系统 == 手动<系统当前明暗>（逐角色完全一致） ----
sys_theme = os_theme()
expect_mode = theme.MODE_LIGHT if sys_theme == '浅色' else (
    theme.MODE_DARK if sys_theme == '深色' else None)
if expect_mode is None:
    ok('系统明暗可判定', False, sys_theme)
else:
    a, b = snap[theme.MODE_SYSTEM]['roles'], snap[expect_mode]['roles']
    diff = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
    ok('跟随系统 == %s（系统当前=%s）'
       % (snap[expect_mode]['label'], sys_theme), not diff, str(diff))

# ---- 2) 手动浅色/深色 由平台调色板提供（未被兜底调色板顶掉） ----
for mode in (theme.MODE_LIGHT, theme.MODE_DARK):
    s = snap[mode]
    ok('%s 采用平台调色板（非兜底）' % s['label'], s['src'] == 'platform',
       '来源=%s scheme=%s' % (s['src'], s['scheme']))

# ---- 3) 请求的方案确实被平台照办（明暗与请求一致） ----
for mode, want_dark in ((theme.MODE_LIGHT, False), (theme.MODE_DARK, True)):
    s = snap[mode]
    is_dark = QColor(s['roles']['Window']).lightness() < 128
    ok('%s 明暗符合请求' % s['label'], is_dark == want_dark,
       'Window=%s' % s['roles']['Window'])

# ---- 4) 平台调色板下的可读性（次要文字/警告/链接） ----
for mode in (theme.MODE_SYSTEM, theme.MODE_LIGHT, theme.MODE_DARK):
    s = snap[mode]
    bg = s['pal'].color(QPalette.Window)
    for tag, fg in (('次要文字', s['hint']), ('警告', s['warn']), ('链接', s['link'])):
        c = contrast(QColor(fg), bg)
        ok('%s: %s对比度≥4.5' % (s['label'], tag), c >= 4.5,
           '%.2f:1 %s on %s' % (c, fg, bg.name()))

# ---- 5) 系统为深色时的等价性（当前系统是浅色，无法直接观测 → 按规则推演） ----
# 注意：推演用的调色板必须**手工构造**（取值取自实测的手动深色 = 平台深色）。
# 实测发现：把 app.palette() 的拷贝再 setPalette 回去，Qt 会当作「颜色没变」直接
# 忽略（见 __pal_probe5），用它来假装「平台深色」会得到假阴性。
_real_scheme = theme.system_scheme
try:
    theme.set_mode(theme.MODE_SYSTEM, app)             # 真的切到「跟随系统」
    theme.system_scheme = lambda: Qt.ColorScheme.Dark  # 再模拟系统为深色
    ok('系统为深色时「跟随系统」按深色处理', theme._want_dark() is True,
       str(theme._want_dark()))

    platform_dark = QPalette()
    for role, name in snap[theme.MODE_DARK]['roles'].items():
        platform_dark.setColor(getattr(QPalette, role), QColor(name))
    app.setPalette(platform_dark)
    src = theme._adopt_platform_palette(app, theme._want_dark())
    ok('系统为深色时「跟随系统」原样采用平台深色（与手动深色同一套色）',
       src == 'platform'
       and roles_of(QPalette(app.palette())) == snap[theme.MODE_DARK]['roles'],
       '%s %s' % (src, roles_of(QPalette(app.palette()))))
finally:
    theme.system_scheme = _real_scheme
    theme.set_mode(theme.MODE_SYSTEM, app)

# ---- 汇总 ----
n_fail = len([r for r in results if r[0] == 'FAIL'])
lines = ['[%s] %s%s' % (st, name, ('  <- ' + extra) if extra else '')
         for st, name, extra in results]
lines.append('')
lines.append('合计：%d 项，失败 %d 项' % (len(results), n_fail))
text = '\n'.join(out + lines)
with open(os.path.join(HERE, '__scheme_system_out.txt'), 'w', encoding='utf-8') as f:
    f.write(text + '\n')
print(text)
sys.exit(1 if n_fail else 0)
