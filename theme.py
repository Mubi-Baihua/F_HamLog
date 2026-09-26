"""主题工具：颜色模式（跟随系统/浅色/深色）与跟随调色板的取色。

两件事：

1. **颜色模式**——用户在「设置」里选择，持久化到 `file/m_xml.txt` 的
   `theme_mode` 键：

     - ``system``（默认）跟随系统深浅色；
     - ``light`` / ``dark`` 固定浅色/深色。

   **以跟随系统的观感为准**：三种模式都先向 Qt 请求目标配色方案
   （``QStyleHints.setColorScheme``），再把平台给出的调色板作为最终外观——
   这样「手动深色」与「系统深色」是同一套色（实测 Windows 11 风格下深色为
   ``#1e1e1e``/``#2d2d2d``、浅色为 ``#f3f3f3``/``#ffffff``）。只有当平台
   不认这个请求（离屏、旧 Qt、不支持深色的系统）导致调色板与目标明暗不符时，
   才用本模块自建的 `_DARK_ROLES` / `_LIGHT_ROLES` 兜底。

2. **主题取色**——界面里不得写死颜色：写死的 ``color:#444``、``#f3f3f3``
   在深色模式下会变成「深灰字压深底」「白字压浅底」，内容直接看不见。
   这里统一从当前调色板推导，并提供随主题变化的语义色（次要文字/警告/链接）。

典型用法::

    import theme

    theme.init_app(app)                                      # main.py 启动时一次
    lbl.setStyleSheet(theme.hint_css())                       # 次要文字
    lbl.setStyleSheet(theme.warn_css('font-weight:bold;'))    # 警告
    theme.watch_theme(window, refresh_colors)                # 主题变化时重刷
"""

import os
import weakref

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
#  颜色模式
# ---------------------------------------------------------------------------

MODE_SYSTEM = 'system'
MODE_LIGHT = 'light'
MODE_DARK = 'dark'
DEFAULT_MODE = MODE_SYSTEM

# 设置文件里的键；MODE_LABELS 的顺序即「设置」窗口下拉框的顺序
MODE_KEY = 'theme_mode'
MODE_LABELS = (
    (MODE_SYSTEM, '跟随系统'),
    (MODE_LIGHT, '浅色'),
    (MODE_DARK, '深色'),
)
MODE_LABEL_OF = dict(MODE_LABELS)
VALID_MODES = tuple(MODE_LABEL_OF)

_mode = DEFAULT_MODE

# ---------------------------------------------------------------------------
#  兜底调色板：**仅在平台不认 setColorScheme 时使用**
#  （Windows 11 风格下正常路径采用系统给出的调色板，见 _adopt_platform_palette）
# ---------------------------------------------------------------------------

_DARK_ROLES = {
    QPalette.Window: '#353535',
    QPalette.WindowText: '#ffffff',
    QPalette.Base: '#252525',
    QPalette.AlternateBase: '#3a3a3a',
    QPalette.Text: '#ffffff',
    QPalette.Button: '#353535',
    QPalette.ButtonText: '#ffffff',
    QPalette.ToolTipBase: '#2b2b2b',
    QPalette.ToolTipText: '#ffffff',
    QPalette.BrightText: '#ff8080',
    QPalette.Link: '#6aa6ff',
    QPalette.Highlight: '#2f6fed',
    QPalette.HighlightedText: '#ffffff',
    QPalette.Light: '#4a4a4a',
    QPalette.Midlight: '#404040',
    QPalette.Mid: '#2a2a2a',
    QPalette.Dark: '#1e1e1e',
    QPalette.Shadow: '#141414',
    QPalette.PlaceholderText: '#9a9a9a',
}

_LIGHT_ROLES = {
    QPalette.Window: '#f0f0f0',
    QPalette.WindowText: '#000000',
    QPalette.Base: '#ffffff',
    QPalette.AlternateBase: '#f7f7f7',
    QPalette.Text: '#000000',
    QPalette.Button: '#f0f0f0',
    QPalette.ButtonText: '#000000',
    QPalette.ToolTipBase: '#ffffff',
    QPalette.ToolTipText: '#000000',
    QPalette.BrightText: '#c0392b',
    QPalette.Link: '#0066cc',
    QPalette.Highlight: '#2f6fed',
    QPalette.HighlightedText: '#ffffff',
    QPalette.Light: '#ffffff',
    QPalette.Midlight: '#e8e8e8',
    QPalette.Mid: '#c0c0c0',
    QPalette.Dark: '#a0a0a0',
    QPalette.Shadow: '#505050',
    QPalette.PlaceholderText: '#8a8a8a',
}

# 禁用态文字：两套主题下都压暗，免得"可用/禁用"看起来一样
_DISABLED_FG = '#7f7f7f'

# 语义色
_DARK_WARN = '#ff8080'
_LIGHT_WARN = '#c0392b'
_ACCENT = '#2f6fed'


def _build_palette(roles):
    """以 style 默认调色板为基底覆盖角色，未覆盖的部分保持原生观感。"""
    try:
        base = QApplication.style().standardPalette()
    except Exception:
        base = QPalette()
    pal = QPalette(base)
    for role, val in roles.items():
        pal.setColor(role, QColor(val))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(_DISABLED_FG))
    return pal


def dark_palette():
    """兜底深色调色板（平台不支持 setColorScheme 时使用）。"""
    return _build_palette(_DARK_ROLES)


def light_palette():
    """兜底浅色调色板（平台不支持 setColorScheme 时使用）。"""
    return _build_palette(_LIGHT_ROLES)


# ---------------------------------------------------------------------------
#  读取 / 保存颜色模式（设置文件 file/m_xml.txt，与 set.py 同一份）
# ---------------------------------------------------------------------------

def settings_path():
    """设置文件路径。

    优先复用 `satellite_pred.app_path` 的打包路径解析（单一事实来源），
    不可用时退回相对路径。延迟导入，避免模块级重依赖。
    """
    try:
        import satellite_pred as sp
        return sp.SETTINGS_PATH
    except Exception:
        return os.path.join('file', 'm_xml.txt')


def read_settings():
    """读出设置 dict（形如 `eval` 的字面量）；失败返回空 dict。"""
    try:
        with open(settings_path(), 'r', encoding='utf-8') as f:
            data = eval(f.read())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_mode():
    """读已保存的颜色模式；缺失/非法值一律按「跟随系统」。"""
    raw = str(read_settings().get(MODE_KEY, DEFAULT_MODE) or DEFAULT_MODE).strip().lower()
    return raw if raw in MODE_LABEL_OF else DEFAULT_MODE


def save_mode(mode):
    """把颜色模式写回设置文件（只改这一个键，保留其它设置）。"""
    mode = normalize_mode(mode)
    data = read_settings()
    data[MODE_KEY] = mode
    path = settings_path()
    try:
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(str(data))
    except Exception:
        return False
    return True


def normalize_mode(mode):
    mode = str(mode or '').strip().lower()
    return mode if mode in MODE_LABEL_OF else DEFAULT_MODE


# ---------------------------------------------------------------------------
#  应用颜色模式
# ---------------------------------------------------------------------------

def _scheme_of(mode):
    if mode == MODE_DARK:
        return Qt.ColorScheme.Dark
    if mode == MODE_LIGHT:
        return Qt.ColorScheme.Light
    return Qt.ColorScheme.Unknown      # Unknown = 交回系统跟随


def system_scheme():
    """系统当前的配色方案；探测不到（离屏等）返回 ``Unknown``。"""
    app = QApplication.instance()
    if app is None:
        return Qt.ColorScheme.Unknown
    try:
        return app.styleHints().colorScheme()
    except Exception:
        return Qt.ColorScheme.Unknown


def _want_dark():
    """当下应该呈现的明暗：跟随系统时即系统的方案；``None`` = 说不准。

    以系统为准——「跟随系统」直接采信系统探测结果，手动选项则指定明暗。
    """
    if _mode != MODE_SYSTEM:
        return _mode == MODE_DARK
    scheme = system_scheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return None


def _palette_is_dark(pal):
    return pal.color(QPalette.Window).lightness() < 128


def _settle(app, times=3):
    """跑掉已投递的事件：平台/样式的调色板更新可能是投递式的。

    用 `sendPostedEvents` 而不是 `processEvents`——同样能送达调色板变更事件，
    但不会顺手取出用户输入/定时器事件，避免在槽函数里被重入。
    """
    for _ in range(times):
        try:
            app.sendPostedEvents()
        except Exception:
            try:
                app.processEvents()
            except Exception:
                break


def _adopt_platform_palette(app, want_dark):
    """采用平台给出的调色板；只有当它与目标明暗不符时才用自建调色板兜底。

    返回实际采用的来源（``'system'`` / ``'platform'`` / ``'fallback'``），便于测试。
    """
    if want_dark is None:
        return 'system'                # 探测不到系统配色 → 保持平台原样
    if _palette_is_dark(app.palette()) == want_dark:
        # 平台已按目标方案给色（Windows 11 风格支持 setColorScheme）→ 原样采用，
        # 这样「手动深色」与「系统深色」是同一套色，不存在观感差距
        return 'platform'
    app.setPalette(dark_palette() if want_dark else light_palette())
    _settle(app, 1)
    return 'fallback'


_scheme_hook = None
_applying = False
# 最近一次实际采用的调色板来源：'system' / 'platform' / 'fallback'（便于诊断与测试）
_last_source = None


def _install_scheme_listener(app):
    """系统深浅色变化时重新确认配色（一次即可，重复调用无副作用）。

    强制浅色/深色时，系统切换会连调色板一起换掉，需要把我们请求的方案再按一次；
    「跟随系统」则不必干预——Qt 自己就会换成对应方案的调色板。
    """
    global _scheme_hook
    if _scheme_hook is not None:
        return

    def _on_scheme_changed(*_args):
        if _applying or _mode == MODE_SYSTEM:
            return
        apply(app)

    try:
        app.styleHints().colorSchemeChanged.connect(_on_scheme_changed)
        _scheme_hook = _on_scheme_changed     # 保引用，防止被回收
    except Exception:
        _scheme_hook = None


def apply(app=None, mode=None):
    """把颜色模式套用到整个应用（mode=None 表示沿用当前模式）。

    以跟随系统的观感为准：撤掉本应用的调色板覆盖 → 请求目标配色方案 →
    采用平台给出的调色板（必要时才用自建调色板兜底）。
    """
    global _mode, _applying, _last_source
    app = app or QApplication.instance()
    if mode is not None:
        _mode = normalize_mode(mode)
    if app is None:
        return _mode
    if _applying:          # 防重入：下面这几步本身会触发 colorSchemeChanged
        return _mode
    _install_scheme_listener(app)
    _applying = True
    try:
        try:
            app.setPalette(QPalette())            # 撤掉覆盖 → 回到平台/系统调色板
        except Exception:
            pass
        try:
            app.styleHints().setColorScheme(_scheme_of(_mode))
        except Exception:
            pass        # 老版本 Qt 没有 setColorScheme：直接走下面的兜底
        _settle(app)
        _last_source = _adopt_platform_palette(app, _want_dark())
    finally:
        _applying = False
    return _mode


def init_app(app):
    """启动时调用：读设置并应用颜色模式，返回生效的模式。"""
    apply(app, load_mode())
    return _mode


def current_mode():
    """当前生效的模式（`system` 表示交给系统）。"""
    return _mode


def set_mode(mode, app=None):
    """切换模式，返回生效的模式（是否落盘由调用方决定）。"""
    return apply(app, mode)


# ---------------------------------------------------------------------------
#  主题取色（一律从当前调色板推导，不写死颜色）
# ---------------------------------------------------------------------------

# 次要文字色：把正文色向背景混合的比例（越大越淡，0.35 ≈ 原来的 #444/#555 观感）
HINT_BLEND = 0.35

# 调色板/主题变化的事件集合（ThemeChange 仅 Qt 6.5+ 存在）
THEME_EVENTS = {QEvent.PaletteChange, QEvent.ApplicationPaletteChange}
if hasattr(QEvent, 'ThemeChange'):
    THEME_EVENTS.add(QEvent.ThemeChange)

_watchers = weakref.WeakSet()


def blend(a, b, ratio):
    """把颜色 a 按 ratio 向 b 混合（0 = 全 a，1 = 全 b）。"""
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(a.red() * (1 - ratio) + b.red() * ratio),
        round(a.green() * (1 - ratio) + b.green() * ratio),
        round(a.blue() * (1 - ratio) + b.blue() * ratio),
    )


def palette(widget=None):
    """控件自身调色板（更贴近其实际取色），无控件时退回应用调色板。"""
    return widget.palette() if widget is not None else QApplication.palette()


def is_dark(widget=None):
    """当前是否深色主题（按窗口底色的明度判断）。"""
    return palette(widget).color(QPalette.Window).lightness() < 128


def hint_color(widget=None):
    """次要文字色：浅色主题下为深灰、深色主题下为浅灰，两种情况都保持可读。"""
    pal = palette(widget)
    return blend(pal.color(QPalette.WindowText), pal.color(QPalette.Window), HINT_BLEND)


def warn_color(widget=None):
    """警告/错误文字色：深色主题下提亮，否则红字压在深底上看不清。"""
    return QColor(_DARK_WARN if is_dark(widget) else _LIGHT_WARN)


def link_color(widget=None):
    """链接色：取自调色板 Link 角色（已按主题配好）。"""
    return palette(widget).color(QPalette.Link)


def accent_color():
    """产品主色（强调按钮），深浅色下都能配白字。"""
    return QColor(_ACCENT)


def subtle_bg(widget=None):
    """次级背景色（如表格冻结列）：与主视图底色轻微区分，且跟随主题深浅。

    传 widget 时取其调色板。**不要传「用 stylesheet 设过 background-color 的
    控件」**：QSS 会把该颜色反写进控件自己的调色板，用它取色会在首次设置后
    锁死、系统切换深浅色时不再跟随；传父级或未被 QSS 染色的控件更安全。
    """
    return palette(widget).color(QPalette.Window)


def border_color(widget=None):
    """分割线/边框色：浅色下取中灰、深色下取比底色略亮的灰（Mid 在深色下偏暗）。"""
    return palette(widget).color(
        QPalette.Midlight if is_dark(widget) else QPalette.Mid)


# ---- 常用 QSS 片段（省得各处拼字符串，也避免写死颜色） ----

def hint_css(extra=''):
    """次要文字色 + 附加样式（如 'font-size:9pt;'）。"""
    return 'color:%s; %s' % (hint_color().name(), extra)


def warn_css(extra=''):
    """警告文字色 + 附加样式。"""
    return 'color:%s; %s' % (warn_color().name(), extra)


def link_css(extra=''):
    """链接色 + 附加样式。"""
    return 'color:%s; %s' % (link_color().name(), extra)


def watch_theme(target, callback):
    """调色板/主题变化时调用 callback，返回由 target 持有生命周期的监听器。

    target 销毁后监听器一并回收（Qt 父子关系），无需手工注销。
    """
    class _ThemeWatcher(QObject):
        def eventFilter(self, obj, event):
            if event.type() in THEME_EVENTS:
                try:
                    callback()
                except Exception:
                    pass
            return False

    watcher = _ThemeWatcher(target)
    target.installEventFilter(watcher)
    _watchers.add(watcher)  # 仅防被 GC（target 销毁后随之失效）
    return watcher
