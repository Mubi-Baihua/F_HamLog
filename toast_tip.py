"""悬浮提示框（toast）：取代部分「无需用户点击确认」的 QMessageBox 提示。

特点：
- 非模态、无边框、置顶、不抢焦点（不会打断主表格的输入）；
- 默认显示 1 秒后自动关闭（带轻微淡入淡出，避免突兀）；
- 跟随当前主题（浅色/深色）取 ToolTip 配色，警告类用语义红；
- 多个提示**原地堆叠**在屏幕上方中央（新提示覆盖在旧提示之上，不上下挪动），不会一路往下排；
- 父窗口销毁时随之一并销毁，不残留；
- **宽度按文案自适应**：以文字单行完整显示所需的宽度为准——比当前宽度窄的文案保持当前宽度（不缩窄，
  下限 `_MIN_W`），比当前宽度宽的文案**自动加宽**（上限为屏幕可用宽度的 80%，至少 `_MAX_W`）；
  只有超过上限的长文案才折行成多行并增加高度。

典型用法（取代 QMessageBox.information/warning 的结果反馈）::

    import toast_tip
    toast_tip.show_toast('已复制 3 条日志到剪贴板。', window)
    toast_tip.show_toast('剪贴板内容无法识别为日志数据。', window, kind='warning')
"""
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPalette, QColor, QPainter, QPen, QFontMetrics
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QWidget, QLabel, QApplication

# 当前在屏的提示，用于堆叠偏移与关闭时回收
_ACTIVE = []
_DEFAULT_TIMEOUT = 1000      # 默认显示时长（毫秒）
_FADE_MS = 200              # 退场淡出时长

# ---- 宽度口径（改这里就等于改所有悬浮提示的宽度）----
_PAD_X = 12                 # QLabel 左右内边距（与下面 QSS 的 padding 保持一致）
_PAD_Y = 6                  # QLabel 上下内边距（同上）
_SLACK_X = 22               # 沿用的额外余量：文案两侧再留白，避免贴着卡片边缘
_MIN_W = 96                 # 最小宽度：文案很短时也不缩窄
_MAX_W = 440                # 上限基数：实际上限取「屏幕可用宽度的 80%」与此值的较大者
_MAX_RATIO = 0.8
_MAX_ABS = 900              # 绝对上限：再长也不超过这个宽度（避免提示横贯整屏），超过才折行
_H_EXTRA = 12               # 高度额外余量（沿用旧实现：卡片高 = label 高 + 12）


def _label_css(fg):
    """label 样式（字体/内边距集中在这里，宽度口径与 _PAD_X/_PAD_Y 保持一致）。"""
    return ('QLabel{background:transparent; color:%s; font-size:9pt; padding:%dpx %dpx;}'
            % (fg.name(), _PAD_Y, _PAD_X))


def _max_toast_width():
    """宽度上限：屏幕可用宽度的 80%，再收敛到 [_MAX_W, _MAX_ABS]。超过上限的长文案才折行。"""
    scr = QApplication.primaryScreen()
    if scr is None:
        return _MAX_W
    ratio_w = int(scr.availableGeometry().width() * _MAX_RATIO)
    return max(_MAX_W, min(ratio_w, _MAX_ABS))



def _toast_bg_fg(kind):
    """按当前主题取底色与文字色。"""
    pal = QApplication.palette()
    bg = pal.color(QPalette.ToolTipBase)
    if kind in ('warning', 'error'):
        try:
            import theme
            fg = theme.warn_color()
        except Exception:
            fg = QColor('#c0392b')
    else:
        fg = pal.color(QPalette.ToolTipText)
    return bg, fg


class _Toast(QWidget):
    def __init__(self, text, timeout, kind, parent):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # 不抢焦点：避免打断主表格的输入/编辑
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self._timeout = timeout
        self._kind = kind

        bg, fg = _toast_bg_fg(kind)
        self._bg = bg
        self._fg = fg

        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(_label_css(fg))
        label.adjustSize()

        # 宽度自适应：
        #   1) need_w = 文字单行完整显示所需的宽度（文字宽 + 左右内边距 + 额外余量）；
        #   2) 需要的宽度 < 当前宽度（短文案，落到 _MIN_W 下限）→ 保持当前宽度，不缩窄；
        #      需要的宽度 > 当前宽度 → 自动加宽；
        #   3) 只有超过上限（_max_toast_width()：屏幕宽 80%，且限制在 440~900）才折行。
        fm = QFontMetrics(label.font())
        need_w = fm.horizontalAdvance(text) + _PAD_X * 2 + _SLACK_X
        w = min(max(need_w, _MIN_W), _max_toast_width())
        # 高度按最终宽度重排后取真实所需：单行文案结果与旧实现一致（label 高 24 + 12 = 36），
        # 折行文案则随行数自动长高，不会再被压扁截断。
        h = label.heightForWidth(w) + _H_EXTRA
        self.setFixedSize(w, h)
        label.setGeometry(0, 0, w, h)
        self._w, self._h = w, h
        self._label = label

        # 说明：不使用 QGraphicsDropShadowEffect —— 无边框半透明（分层）窗口上，
        # 阴影会把绘制脏矩形扩展到窗口负偏移区，导致 Windows 报
        # “UpdateLayeredWindowIndirect failed (参数错误。)”。改用细边框体现卡片感。

        # 主题变化时重刷配色（提示存活仅约 1 秒，概率极低，但保持正确）
        try:
            import theme
            theme.watch_theme(self, self._refresh_colors)
        except Exception:
            pass

    def _refresh_colors(self):
        bg, fg = _toast_bg_fg(self._kind)
        self._bg, self._fg = bg, fg
        if self._label is not None:
            self._label.setStyleSheet(_label_css(fg))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = 8
        rect = QRectF(0.5, 0.5, self._w - 1, self._h - 1)
        # 底色圆角卡片
        p.setPen(Qt.NoPen)
        p.setBrush(self._bg)
        p.drawRoundedRect(rect, r, r)
        # 细边框体现“悬浮卡片”观感（替代阴影，避免分层窗口负偏移报错）
        dark = self._bg.lightness() < 128
        pen = QPen(QColor(255, 255, 255, 38) if dark else QColor(0, 0, 0, 38))
        pen.setWidthF(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, r, r)
        super().paintEvent(ev)

    def show_toast(self):
        self.show()
        # 入场淡入
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b'windowOpacity', self)
        anim.setDuration(120)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._fade_anim = anim
        # 临近超时先淡出再关闭
        QTimer.singleShot(max(0, self._timeout - _FADE_MS), self._begin_fade)

    def _begin_fade(self):
        anim = QPropertyAnimation(self, b'windowOpacity', self)
        anim.setDuration(_FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(self.close)
        anim.start()
        self._fade_anim = anim

    def closeEvent(self, ev):
        global _ACTIVE
        try:
            _ACTIVE.remove(self)
        except ValueError:
            pass
        super().closeEvent(ev)


def _anchor(parent):
    # 固定在屏幕上方中央，不随父窗口位置移动
    scr = QApplication.primaryScreen()
    if scr is not None:
        g = scr.availableGeometry()
        cx = g.x() + g.width() // 2
        top = g.y() + 24
    else:
        cx, top = 400, 24
    return cx, top


def show_toast(text, parent=None, timeout=_DEFAULT_TIMEOUT, kind='info'):
    """弹出一个悬浮提示，timeout 毫秒后自动关闭（默认 1000，即 1 秒）。

    kind 仅影响语义色：``'warning'`` / ``'error'`` 用警告红，其余用常规文字色。
    返回创建的提示控件（或环境无 QApplication 时返回 None）。
    """
    app = QApplication.instance()
    if app is None:
        return None
    t = _Toast(text, timeout, kind, parent)
    ax, ay = _anchor(parent)
    # 原地堆叠：新提示直接盖在屏幕上方同一位置，旧提示不挪动
    t.move(ax - t.width() // 2, ay)
    _ACTIVE.append(t)
    t.show_toast()
    t.raise_()
    return t
