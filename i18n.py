"""多语言（中/英）支持。

设计要点
--------
中文是**源语言**（界面文字本来就用中文写），所以不做「给每处字符串套一层
`tr()`」的侵入式改造，而是**在文字显示时统一翻译**：

    中文原文 ──(词表 dict)──▶ 英文译文

三层结构：

1. **词表** —— `i18n_zh_en.py` 的 ``TRANSLATIONS``（普通 dict，中文 → 英文）。
   值里可写 ``{}`` 占位符表示可变内容，例如::

       '已删除 {} 条日志。': 'Deleted {} log(s).'

   于是**动态文案**（f-string 拼出来的）也能翻：文案渲染成
   ``已删除 3 条日志。`` 后按模板反查得到 ``Deleted 3 log(s).``

2. **控件翻译** —— `translate_widget()` 认得各类控件的显示文字：
   窗口标题、QLabel/QAbstractButton 文字、QGroupBox 标题、占位符、
   QAction 文字、下拉框/列表项、表格表头、标签页标题。

3. **自动应用** —— `install(app)` 在 QApplication 上装事件过滤器：
   顶层窗口**显示时**自动翻一遍控件树；Qt 派发 ``LanguageChange`` 时再翻一遍。

因此**新增界面代码零改动**，只要词表里有条目就跟着切语言；运行时在
「设置」里切语言，已打开窗口**原地重译**——不重建窗口、不丢未保存数据。

Qt 自带控件（标准对话框按钮、右键菜单）的语言由
``qtbase_zh_CN.qm`` / ``qtbase_en.qm`` 负责。

典型用法::

    import i18n

    i18n.install(app)                  # 建好 QApplication 后调一次
    i18n.set_language('en')            # 切换语言（即时生效）
    i18n.save_language('en')           # 落盘（写进 file/m_xml.txt）
    label.setText(i18n.tr('保存'))      # 需要显式翻译时（通常用不着）
"""

import os
import re

from PySide6.QtCore import QEvent, QObject, Qt, QTranslator
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox,
                               QGroupBox, QLabel, QLineEdit, QListWidget,
                               QMenu, QPlainTextEdit, QTabWidget, QTableView,
                               QTextEdit, QTreeWidget, QWidget)

from i18n_zh_en import TRANSLATIONS

# ---------------------------------------------------------------------------
#  语言选项与持久化
# ---------------------------------------------------------------------------

LANG_ZH = 'zh'
LANG_EN = 'en'
DEFAULT_LANG = LANG_ZH

# 「设置」窗口下拉框的顺序即此顺序；语言名一律用**母语写法**，不随界面语言变
LANG_LABELS = (
    (LANG_ZH, '简体中文'),
    (LANG_EN, 'English'),
)
LANG_LABEL_OF = dict(LANG_LABELS)
VALID_LANGS = tuple(LANG_LABEL_OF)

# 设置文件（file/m_xml.txt）里的键
LANG_KEY = 'language'

_QT_QMS = {
    LANG_ZH: 'qtbase_zh_CN.qm',
    LANG_EN: 'qtbase_en.qm',
}

_lang = DEFAULT_LANG


def settings_path():
    """设置文件路径——复用 theme 的解析（单一事实来源），失败则退回相对路径。"""
    try:
        import theme
        return theme.settings_path()
    except Exception:
        return os.path.join('file', 'm_xml.txt')


def read_settings():
    """读出设置 dict；失败返回空 dict。"""
    try:
        with open(settings_path(), 'r', encoding='utf-8') as f:
            data = eval(f.read())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_language(lang):
    """归一化为受支持的语言代码；非法值一律回落到默认（中文）。"""
    lang = str(lang or '').strip().lower()
    if lang in ('zh', 'zh_cn', 'zh-cn', 'cn', 'chinese', '中文'):
        return LANG_ZH
    if lang in ('en', 'en_us', 'en-us', 'english', '英文'):
        return LANG_EN
    return DEFAULT_LANG


def load_language():
    """读已保存的语言；缺失/非法一律按中文。"""
    return normalize_language(read_settings().get(LANG_KEY, DEFAULT_LANG))


def save_language(lang):
    """把语言写回设置文件（只改这一个键，保留其它设置）。"""
    lang = normalize_language(lang)
    data = read_settings()
    data[LANG_KEY] = lang
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


def current_language():
    """当前生效的语言代码。"""
    return _lang


def is_english():
    return _lang == LANG_EN


# ---------------------------------------------------------------------------
#  词表：精确匹配 + 模板匹配
# ---------------------------------------------------------------------------

# 占位符写法：{} / {0} / {name}
_PLACEHOLDER = re.compile(r'\{\}|\{\d+\}|\{[A-Za-z_][A-Za-z0-9_]*\}')
_CJK = re.compile(r'[\u4e00-\u9fff]')
# 模板至少要有这么多汉字，避免「{} 颗」这类短模板误伤真实数据
_MIN_TEMPLATE_CJK = 2
# 竖向表头只在行数不超过该值时翻译（主日志表上万行，逐行取表头会拖慢重建）
_MAX_VERTICAL_HEADER_ROWS = 64
# 模板占位符里捕获的片段本身可能仍是中文（状态栏常把几段拼起来），
# 递归翻译它；深度上限防止模板互相套娃时无限递归。
_MAX_TEMPLATE_DEPTH = 4


def _compile_template(text):
    """把模板切成 (regex, 片段列表)；占位符位置在片段里用 None 标记。"""
    pattern = ['^']
    parts = []
    pos = 0
    for m in _PLACEHOLDER.finditer(text):
        lit = text[pos:m.start()]
        pattern.append(re.escape(lit))
        pattern.append('(.*?)')
        parts.append(lit)
        parts.append(None)
        pos = m.end()
    tail = text[pos:]
    pattern.append(re.escape(tail))
    parts.append(tail)
    pattern.append('$')
    return re.compile(''.join(pattern), re.S), parts


def _fill(template, groups):
    """把捕获到的片段填回目标模板的 ``{}`` 位置（其它花括号原样保留）。"""
    out = []
    it = iter(groups)
    i = 0
    n = len(template)
    while i < n:
        if template[i] == '{' and i + 1 < n and template[i + 1] == '}':
            try:
                out.append(next(it))
            except StopIteration:
                out.append('')
            i += 2
            continue
        out.append(template[i])
        i += 1
    return ''.join(out)


class _Catalog:
    """双向词表：中文↔英文，含模板表（模板按长短排序，长模板优先）。"""

    def __init__(self, table):
        self.zh2en = dict(table)
        self.en2zh = {}
        for zh, en in table.items():
            # 反向只登记首个译法，避免多条中文撞同一英文时来回抖动
            self.en2zh.setdefault(en, zh)
        self.tpl_zh2en = self._templates(table, True)
        self.tpl_en2zh = self._templates(table, False)
        self.cache = {}

    @staticmethod
    def _templates(table, forward):
        out = []
        for zh, en in table.items():
            src, dst = (zh, en) if forward else (en, zh)
            if not _PLACEHOLDER.search(src) or not _PLACEHOLDER.search(dst):
                continue
            if len(re.findall(r'[\u4e00-\u9fff]', zh)) < _MIN_TEMPLATE_CJK:
                continue
            rx, parts = _compile_template(src)
            out.append((rx, dst))
        out.sort(key=lambda t: -len(t[0].pattern))
        return out


_catalog = None


def catalog():
    """取（惰性构建的）词表对象。"""
    global _catalog
    if _catalog is None:
        _catalog = _Catalog(TRANSLATIONS)
    return _catalog


def _match(templates, text, depth=0):
    for rx, out_tpl in templates:
        m = rx.match(text)
        if m:
            groups = m.groups()
            if depth < _MAX_TEMPLATE_DEPTH:
                # 占位符里捕获到的片段可能还是中文（如状态栏把几段拼起来），
                # 先各自翻一遍，免得英文句子里夹着中文。
                groups = tuple(_translate_inner(g, depth + 1) for g in groups)
            return _fill(out_tpl, groups)
    return None


def _translate_inner(text, depth):
    # 不按「是否含汉字」短路：反方向（英文→中文）时占位符里捕获的片段是英文，
    # 同样需要再翻一层。模板都要求中文侧至少两个汉字，纯数字/纯符号的片段
    # 匹配不到任何模板，会原样返回，因此这里无条件递归是安全的。
    if not text:
        return text
    return _translate(text, depth)


def translate(text):
    """把一个中文原文（或已译英文）翻成当前语言；翻不了就原样返回。"""
    return _translate(text, 0)


def _translate(text, depth=0):
    """translate 的内部实现；depth > 0 表示这是模板占位符里的递归翻译。"""
    if not isinstance(text, str) or not text:
        return text
    cat = catalog()
    cached = depth == 0
    if cached:
        key = (_lang, text)
        hit = cat.cache.get(key)
        if hit is not None:
            return hit
    if _lang == LANG_EN:
        result = cat.zh2en.get(text)
        if result is None:
            result = _match(cat.tpl_zh2en, text, depth) or text
    else:
        result = cat.en2zh.get(text)
        if result is None:
            result = _match(cat.tpl_en2zh, text, depth) or text
    if cached and len(cat.cache) < 20000:
        cat.cache[key] = result
    return result


def tr(text):
    """显式翻译一条文案（一般用不着——界面文字会自动翻译）。"""
    return translate(text)


def tr_list(items):
    """翻译一组文案（表格表头等）。"""
    return [translate(s) for s in items]


def bind_cell_texts(window, table, texts, col=0):
    """把「写在表格单元格里的固定中文文案」接入翻译，并跟随语言切换。

    为什么需要这个函数
    ------------------
    `translate_widget()` 只翻 model 的**表头**，**不翻单元格**——主日志表有上万个
    单元格，逐个取值/回写会明显拖慢重建，所以不做全局扫描。而「新建日志 / 更多信息」
    这类窗口把**字段名**直接写在单元格里（不是表头），于是英文界面下那一列仍是中文。

    参数
    ----
    window : 承载该表格的顶层窗口（用于监听语言变化；可为 None 表示只翻译一次）
    table  : 表格对象（只需支持 ``item(row, col)``）
    texts  : ``{行号: 中文原文}``，或按行顺序排列的中文原文序列（从第 0 行起）
    col    : 文案所在列，默认 0

    每次都按**中文原文**重设，因此语言来回切换能正确还原（不依赖当前显示值）。
    """
    if table is None or not texts:
        return None
    if isinstance(texts, dict):
        pairs = list(texts.items())
    else:
        pairs = list(enumerate(texts))

    def apply():
        for row, src in pairs:
            try:
                item = table.item(row, col)
            except Exception:
                continue
            if item is None:
                continue
            new = translate(src)
            if item.text() != new:
                item.setText(new)

    apply()
    if window is not None:
        return watch_language(window, apply)
    return None


def clear_cache():
    """清翻译缓存（切语言时调用）。"""
    catalog().cache.clear()


# ---------------------------------------------------------------------------
#  控件翻译
# ---------------------------------------------------------------------------

def _set(getter, setter):
    try:
        old = getter()
    except Exception:
        return
    if not isinstance(old, str) or not old:
        return
    new = translate(old)
    if new != old:
        try:
            setter(new)
        except Exception:
            pass


def translate_widget(w):
    """翻译单个控件的显示文字（幂等，来回切语言可还原）。"""
    if w is None or getattr(w, '_i18n_skip', False):
        return
    try:
        if isinstance(w, QAction):
            _set(w.text, w.setText)
            return
        if isinstance(w, QLabel):
            _set(w.text, w.setText)
        elif isinstance(w, QGroupBox):
            _set(w.title, w.setTitle)
        elif isinstance(w, QAbstractButton):
            _set(w.text, w.setText)
        elif isinstance(w, QMenu):
            _set(w.title, w.setTitle)

        if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
            _set(w.placeholderText, w.setPlaceholderText)

        # 窗口标题（QWidget 通用；子控件没有标题，取到空串会被跳过）
        _set(w.windowTitle, w.setWindowTitle)

        if isinstance(w, QComboBox):
            for i in range(w.count()):
                _set(lambda i=i: w.itemText(i),
                     lambda t, i=i: w.setItemText(i, t))
        elif isinstance(w, QListWidget):
            for i in range(w.count()):
                _set(lambda i=i: w.item(i).text(),
                     lambda t, i=i: w.item(i).setText(t))
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                _set(lambda i=i: w.tabText(i),
                     lambda t, i=i: w.setTabText(i, t))
        elif isinstance(w, QTreeWidget):
            head = w.headerItem()
            if head is not None:
                for i in range(head.columnCount()):
                    _set(lambda i=i: head.text(i),
                         lambda t, i=i: head.setText(i, t))

        if isinstance(w, QTableView):
            model = w.model()
            if model is not None:
                for i in range(model.columnCount()):
                    _set(lambda i=i: model.headerData(
                             i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or '',
                         lambda t, i=i: model.setHeaderData(
                             i, Qt.Orientation.Horizontal, t,
                             Qt.ItemDataRole.DisplayRole))
                # 竖向表头（行标签）：只在行数很少时处理——上万行的主日志表若逐行
                # 取/设表头会明显变慢，而它本来也不需要翻译。
                rows = model.rowCount()
                if rows <= _MAX_VERTICAL_HEADER_ROWS:
                    for i in range(rows):
                        _set(lambda i=i: model.headerData(
                                 i, Qt.Orientation.Vertical,
                                 Qt.ItemDataRole.DisplayRole) or '',
                             lambda t, i=i: model.setHeaderData(
                                 i, Qt.Orientation.Vertical, t,
                                 Qt.ItemDataRole.DisplayRole))
    except Exception:
        pass


def translate_tree(root):
    """翻译一棵控件树（root 自身 + 所有后代控件与 QAction）。"""
    if root is None:
        return
    try:
        if isinstance(root, QAction):
            translate_widget(root)
            return
        translate_widget(root)
        for w in root.findChildren(QWidget):
            translate_widget(w)
        for a in root.findChildren(QAction):
            translate_widget(a)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  即时刷新 / 事件接入
# ---------------------------------------------------------------------------

def refresh_all(app=None, repaint=True):
    """把所有已打开窗口（含隐藏对话框与菜单动作）按当前语言重译一遍。"""
    app = app or QApplication.instance()
    if app is None:
        return
    try:
        widgets = app.allWidgets()
    except Exception:
        return
    for w in widgets:
        try:
            translate_widget(w)
            for a in w.actions():
                translate_widget(a)
            if repaint:
                # 自绘内容（如「更多」按钮）需要一次重绘才会更新文字
                w.update()
        except Exception:
            continue


class _LanguageFilter(QObject):
    """顶层窗口显示时 / 语言变化时，自动把控件树翻一遍。"""

    def eventFilter(self, obj, event):
        try:
            et = event.type()
        except Exception:
            return False
        if et == QEvent.Show:
            if isinstance(obj, QWidget):
                try:
                    if obj.isWindow():
                        translate_tree(obj)
                except Exception:
                    pass
        elif et == QEvent.LanguageChange:
            if isinstance(obj, QWidget):
                try:
                    translate_tree(obj)
                except Exception:
                    pass
        return False


_filter = None
_translator = None


def install(app=None):
    """装好语言支持：按设置里的语言起效 + Qt 自带翻译 + 顶层窗口自动翻译。

    重复调用无副作用。
    """
    global _filter, _lang
    app = app or QApplication.instance()
    if app is None:
        return False
    _lang = load_language()          # 启动时应用「设置」里保存的语言
    if _filter is None:
        _filter = _LanguageFilter(app)      # 保引用（父对象 app，随应用存活）
        app.installEventFilter(_filter)
    _apply_qt_translator(app)
    refresh_all(app)
    return True


def _apply_qt_translator(app):
    """按当前语言加载 Qt 自带翻译（标准按钮、右键菜单等）。"""
    global _translator
    if _translator is not None:
        try:
            app.removeTranslator(_translator)
        except Exception:
            pass
        _translator = None
    path = _qt_translation_path(_QT_QMS.get(_lang))
    if not path:
        return
    t = QTranslator(app)
    if t.load(path):
        app.installTranslator(t)
        _translator = t        # 保引用，否则被 GC 后翻译即失效


def _qt_translation_path(name):
    """在 PySide6 的 translations 目录里找翻译文件。"""
    if not name:
        return None
    try:
        import PySide6
        cand = os.path.join(os.path.dirname(PySide6.__file__),
                            'translations', name)
        if os.path.exists(cand):
            return cand
    except Exception:
        pass
    try:
        from PySide6.QtCore import QLibraryInfo
        cand = os.path.join(
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath), name)
        if os.path.exists(cand):
            return cand
    except Exception:
        pass
    return None


def _send_language_change(app):
    """显式向所有顶层窗口派发 LanguageChange（Qt 只在装载/卸载翻译器时自动派发，
    这里补一次，保证 `watch_language` 的回调与自绘内容一定收到通知）。"""
    try:
        widgets = app.topLevelWidgets()
    except Exception:
        return
    for w in widgets:
        try:
            app.sendEvent(w, QEvent(QEvent.LanguageChange))
        except Exception:
            continue


def set_language(lang, app=None):
    """切换语言（立即生效）：换 Qt 翻译 → 重译所有已打开窗口。

    是否落盘由调用方决定（见 `save_language`）。
    """
    global _lang
    lang = normalize_language(lang)
    _lang = lang
    clear_cache()
    app = app or QApplication.instance()
    if app is not None:
        _apply_qt_translator(app)      # 标准按钮/右键菜单跟随语言
        _send_language_change(app)     # 通知窗口（并顺带重译控件树）
        refresh_all(app)               # 兜底：隐藏的对话框与菜单动作也翻一遍
    return _lang


def watch_language(target, callback):
    """语言变化时调用 callback；target 销毁后监听器自动回收。

    回调触发前会先把 target 控件树按新语言重译一遍，因此在回调里量到的
    尺寸/文字就是新语言下的真实值（窗口自适应尺寸依赖这一点）。

    给**自绘内容与窗口尺寸自适应**用（`refresh_all` 已负责重绘，通常不必自己监听）。
    """
    class _LangWatcher(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.LanguageChange:
                try:
                    translate_tree(obj)     # 先重译，回调里量到的才是新语言尺寸
                    callback()
                except Exception:
                    pass
            return False

    watcher = _LangWatcher(target)
    target.installEventFilter(watcher)
    return watcher


def fit_window(window, base_w=None, base_h=None, pad_w=24, pad_h=8):
    """窗口尺寸跟随语言。

    中文：严格用基准尺寸（与历史版本**逐像素一致**，不做任何测量）。
    英文：取「基准尺寸」与「当前语言下文字不被截断所需的最小尺寸」中的较大者，
    按内容放宽，避免英文控件文字被截断。

    **必须在窗口 show() 之后调用**——顶层窗口的 Show 事件才会触发控件树翻译，
    先量后翻会按中文尺寸把窗口定死，英文界面照样被截断。
    """
    if window is None:
        return
    try:
        if not is_english():
            if base_w and base_h:
                window.setFixedSize(base_w, base_h)
            return
        cw = window.centralWidget()
        box = cw if cw is not None else window
        lay = box.layout()
        if lay is not None:
            lay.activate()                 # 重译后让布局重算最小尺寸
        hint = box.minimumSizeHint()
        w = max(base_w if base_w else window.width(), hint.width() + pad_w)
        h = max(base_h if base_h else window.height(), hint.height() + pad_h)
        window.setFixedSize(w, h)
    except Exception:
        pass


def fit_min_width(window, minimum=None):
    """窗口最小宽度跟随语言（窗口本身仍可自由缩放，如带画布的地图窗口）。

    只抬高最小宽度、不设固定尺寸，避免破坏窗口内画布的自适应缩放。
    """
    if window is None:
        return
    try:
        cw = window.centralWidget()
        box = cw if cw is not None else window
        lay = box.layout()
        if lay is not None:
            lay.activate()
        need = box.minimumSizeHint().width()
        window.setMinimumWidth(max(minimum or 0, need))
    except Exception:
        pass
