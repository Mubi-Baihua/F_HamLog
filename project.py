from PySide6.QtWidgets import *
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QEvent, QObject, QTimer, QThread, Signal, QRect  # 新增导入 Qt
from dialog_defaults import desktop_dir
import i18n
from functools import partial
import time as time_
import sys
import os
import re
import json
import socket
import threading
import subprocess
import webbrowser
import urllib.parse
import fhl_rw
import copy
import call_upper
import backup
import theme
import toast_tip
import remote_crypto
import remote_server
from remote_server import send_frame, recv_frame, LogServer, get_lan_ip

# 本机「开放多人日志」的默认端口：与「加入多人日志」对话框的默认端口保持一致，
# 便于同一局域网内不同客户端按默认值直接对接。
DEFAULT_ROOM_PORT = 8000

# 复制/粘贴使用的字段顺序（与表格列对应，英文键名作为剪贴板表头，便于跨窗口/跨软件解析）
COPY_FIELDS = ['date', 'time', 'm_call', 'o_call', 'freq', 'freq_rx', 'mode',
               'prop_mode', 'sat_name', 'm_rst', 'o_rst', 'm_qth', 'o_qth',
               'm_dig', 'o_dig', 'm_ant', 'o_ant', 'm_pow', 'o_pow', 'notes']
# 字段 -> 中文表头（粘贴时兼容中文表头）
FIELD_LABELS = {
    'date': '日期', 'time': '时间', 'm_call': '己方呼号', 'o_call': '对方呼号',
    'freq': '频率', 'freq_rx': '接收频率', 'mode': '调制模式', 'prop_mode': '传播方式',
    'sat_name': '卫星名称', 'm_rst': '己方接收信号', 'o_rst': '对方接收信号',
    'm_qth': '己方QTH', 'o_qth': '对方QTH', 'm_dig': '己方设备', 'o_dig': '对方设备',
    'm_ant': '己方天线', 'o_ant': '对方天线', 'm_pow': '己方功率', 'o_pow': '对方功率',
    'notes': '备注'
}

file = None
key = None
_open_windows = []  # 保持由本模块打开的卫星批量记录窗口引用，防止被回收
# “新建日志 / 更多信息”窗口引用：在 main() 内被 _on_sync 等引用，
# 必须先于任何使用初始化，否则首次打开项目时引用会抛 NameError。
project_others_window = None

# Qt 对象存活性判断：QMainWindow 的 destroyed 信号回调执行时，底层 C++ 对象已被删除，
# 此时任何 setWindowTitle / setVisible 等调用都会抛
#   RuntimeError: libshiboken: Internal C++ object ... already deleted
# 因此凡是可能在窗口销毁后被触发的清理逻辑，动界面之前必须先判活。
try:
    import shiboken6

    def _qt_alive(widget):
        """widget 非 None 且底层 C++ 对象仍然有效时返回 True。"""
        try:
            return widget is not None and shiboken6.isValid(widget)
        except Exception:
            return False
except Exception:  # pragma: no cover - 极端情况下退化为仅判 None
    def _qt_alive(widget):
        return widget is not None

def _ensure_log_keys(entry):
    # 确保单条记录包含新加的字段
    for k in ['freq_rx', 'prop_mode', 'sat_name']:
        if k not in entry:
            entry[k] = ''


def _upgrade_file_records(file_list):
    if not file_list:
        return
    for e in file_list:
        _ensure_log_keys(e)


# ---------------------------------------------------------------------------
# 长日志（上万条）表格优化：勾选列 / 「更多」按钮列改用「自绘委托」而非逐行
# QWidget（QCheckBox、QPushButton）。原因：10000 行若各塞 2 个真实控件，就是
# 2 万个 QWidget，仅创建与布局就要数秒，且全选/反选还要逐行 findChild 遍历控件。
# 改为委托后，勾选状态只存一份 set（O(1) 切换），绘制时才回调，行数再多也不卡。
# ---------------------------------------------------------------------------

# 勾选列（第 0 列）的委托：纯绘制 + 鼠标点击切换
_CHECK_ROLE = Qt.UserRole + 101


class CheckColumnDelegate(QStyledItemDelegate):
    """第 0 列「选择」：绘制一个居中复选框，点击即切换勾选状态。

    on_toggle(row, checked) 由外部注入：勾选状态的唯一权威是外部集合（_checked_rows），
    这里不直接改 model，避免「委托改了 item、集合没改」导致状态分叉。

    外观对齐旧实现：旧代码该列是 QCheckBox(setFixedSize(25, 20)) 居中放置，
    这里按同样的尺寸与对齐方式绘制「复选框指示器」，视觉与旧版一致。
    """

    # 与旧 QCheckBox 的 setFixedSize(25, 20) 保持一致，仅取指示器部分居中绘制
    BOX_W, BOX_H = 25, 20

    def __init__(self, parent=None, on_toggle=None):
        super().__init__(parent)
        self._on_toggle = on_toggle

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        checked = bool(index.data(_CHECK_ROLE) or False)
        # 指示器尺寸：交给样式按当前字体算出原生大小，与 QCheckBox 的绘制完全一致
        size = max(QApplication.style().pixelMetric(QStyle.PM_IndicatorWidth,
                                                    None, opt.widget), 13)
        rect = QRect(opt.rect.center().x() - size // 2,
                     opt.rect.center().y() - size // 2, size, size)
        state = QStyle.State_Enabled | (QStyle.State_On if checked else QStyle.State_Off)
        cb_opt = QStyleOptionButton()
        cb_opt.rect = rect
        cb_opt.state = state
        QApplication.style().drawPrimitive(QStyle.PE_IndicatorCheckBox, cb_opt, painter)

    def editorEvent(self, event, model, option, index):
        # 单击（鼠标左键抬起在单元格内）即切换勾选，与原生 QCheckBox 手感一致
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            checked = bool(index.data(_CHECK_ROLE) or False)
            if self._on_toggle is not None:
                self._on_toggle(index.row(), not checked)
            return True
        return super().editorEvent(event, model, option, index)


class MoreButtonDelegate(QStyledItemDelegate):
    """末列「更多」：绘制一个按钮外观，点击回调到指定函数。

    外观对齐旧实现：旧代码该列是 QPushButton("更多").setFixedHeight(26)，
    委托用样式绘制 CE_PushButton，尺寸取单元格内容区（上下留 3px 边距 → 高度约 26）。
    """

    def __init__(self, parent=None, text='更多'):
        super().__init__(parent)
        self._text = text
        self._click_cb = None  # callable(row) -> None，由使用者设置

    def set_click(self, cb):
        self._click_cb = cb

    def _btn_rect(self, rect):
        # 旧实现：QPushButton("更多").setFixedHeight(26) 直接 setCellWidget 铺满整格
        # （无 layout、无边距）→ 宽度占满列宽，高度 26 在格内居中。此处照搬该几何。
        btn_h = min(26, max(rect.height(), 12))
        top = rect.top() + (rect.height() - btn_h) // 2
        return QRect(rect.left(), top, rect.width(), btn_h)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        btn_opt = QStyleOptionButton()
        btn_opt.state = QStyle.State_Enabled
        if option.state & QStyle.State_MouseOver:
            btn_opt.state |= QStyle.State_MouseOver
        btn_opt.rect = self._btn_rect(opt.rect)
        btn_opt.text = i18n.tr(self._text)
        QApplication.style().drawControl(QStyle.CE_PushButton, btn_opt, painter)

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._btn_rect(option.rect).contains(event.pos()):
                if self._click_cb is not None:
                    self._click_cb(index.row())
                return True
        return super().editorEvent(event, model, option, index)


class LocateButtonDelegate(MoreButtonDelegate):
    """「定位到此条」列：外观与「更多」列一致，点击回调到定位函数。

    仅用于「搜索结果」窗口——把主窗口聚焦并将主表滚动/选中到该条日志。
    复用 MoreButtonDelegate 的绘制与命中判定，只改默认按钮文字。
    """

    def __init__(self, parent=None, text='定位'):
        super().__init__(parent, text=text)


# ---------------------------------------------------------------------------
# 多人日志客户端：与 remote_server 共用帧协议，作为「开放多人日志」/「加入多人日志」的
# 统一后端。远程模式下 project.main 的所有功能（表格/新建/搜索/导入导出/卫星记录等）
# 都直接操作内存中的 file 列表，仅落盘改为经此连接发送到服务端——因此无需重复编写。
# ---------------------------------------------------------------------------

def _fingerprint_verify_dialog(parent, host, port, short_fp, status):
    """服务端身份核对对话框：返回 True 表示用户确认继续连接。

    status：
      'new'      首次连接该地址 → 提示核对指纹；
      'mismatch' 指纹变了 → 强提示（可能是换了服务端，也可能遭中间人替换）。
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle('服务端身份核对')
    dlg.setMinimumWidth(430)
    lay = QVBoxLayout(dlg)

    if status == 'mismatch':
        warn = QLabel('服务端密钥指纹与上次记录不一致！')
        warn.setStyleSheet(theme.warn_css('font-weight: bold;'))
        lay.addWidget(warn)
        tip = QLabel(
            '这可能意味着服务端重装/更换了机器（正常），\n'
            '也可能是局域网内有人冒名顶替（中间人攻击）。\n\n'
            '请向服务端持有者当面确认下面这串指纹后再继续。')
    else:
        tip = QLabel(
            '这是首次连接该服务端，请向服务端持有者核对下面这串指纹。\n'
            '核对通过后会被记住，以后同一地址自动校验。')
    tip.setWordWrap(True)
    lay.addWidget(tip)

    fp_label = QLabel(short_fp)
    f = fp_label.font()
    f.setPointSize(f.pointSize() + 3)
    f.setBold(True)
    f.setFamily('Consolas')
    fp_label.setFont(f)
    fp_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    fp_label.setAlignment(Qt.AlignCenter)
    # 指纹框：底色/边框跟随主题（写死 #f0f0f0 在深色模式下会与白色文字撞底）
    fp_label.setStyleSheet('padding: 8px; background: %s; border: 1px solid %s;'
                           % (theme.subtle_bg(dlg).name(),
                              theme.border_color(dlg).name()))
    lay.addWidget(fp_label)

    host_label = QLabel(f'服务端：{host}:{port}')
    host_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(host_label)

    if status == 'mismatch':
        btn_ok = QPushButton('确认已核对，继续连接')
        btn_cancel = QPushButton('取消连接')
    else:
        btn_ok = QPushButton('指纹一致，继续连接')
        btn_cancel = QPushButton('取消')
    row = QHBoxLayout()
    row.addWidget(btn_cancel)
    row.addWidget(btn_ok)
    lay.addLayout(row)

    result = {'ok': False}
    btn_ok.clicked.connect(lambda: (result.update(ok=True), dlg.accept()))
    btn_cancel.clicked.connect(dlg.reject)
    dlg.exec()
    return result['ok']


def make_fingerprint_verifier(parent, host, port):
    """构造 RemoteConnection 用的指纹核对回调。

    首次连接：弹窗请用户核对，确认后记住该地址的公钥；
    指纹一致：静默通过（不打扰用户）；
    指纹变化：强提示，用户确认则更新记录，否则拒绝连接。
    """
    def _verify(short_fp, raw_pub):
        status, _old = remote_crypto.check_known_key(host, port, raw_pub)
        if status == 'match':
            return True
        ok = _fingerprint_verify_dialog(parent, host, port, short_fp, status)
        if ok:
            remote_crypto.remember_key(host, port, raw_pub)
        return ok
    return _verify


class RemoteConnection:
    """到多人日志服务端的连接（客户端侧）。

    传输加密（见 remote_crypto.py）：connect() 先与服务端做 X25519 密钥交换，程序自主
    生成一个随机会话密钥并用密钥交换结果加密后交给服务端；此后所有帧正文都是密文。
    密码只用于身份认证，不参与内容加密。
    """

    def __init__(self, host, port, password, role='guest', display_ip='',
                 verify_fingerprint=None):
        """
        :param verify_fingerprint: 指纹核对回调 (指纹短码, 是否已知且一致) -> bool。
            返回 False 表示用户拒绝连接。为 None 时不做核对（供 headless 测试使用）。
        """
        self.host = host
        self.port = int(port)
        self.password = password
        # role：'host' 表示本机即为服务端（开放多人日志者）；其余均为 'guest'（普通客户端）
        self.role = role
        # display_ip：内嵌服务端经 127.0.0.1 连回本机服务器时，向服务端上报的局域网展示地址
        self.display_ip = display_ip
        self.sock = None
        self.initial_file = []
        # 握手期间收到的 PEERS（在线客户端列表），用于给同步线程播种，
        # 保证新加入的客户端立刻能看到在线客户端（无需等他人上下线）。
        self.initial_peers = []
        self._sync = None
        # 发送锁：主线程（保存）、后台同步线程与心跳线程共用同一 socket，必须串行发送，
        # 否则两条帧的字节会在 TCP 层交错导致解析失败。
        self._send_lock = threading.Lock()
        # 心跳线程：见 _start_heartbeat 的说明。
        self._hb_thread = None
        self._hb_stop = threading.Event()
        # 加密会话状态
        self.verify_fingerprint = verify_fingerprint
        self.server_key = b''          # 服务端长期公钥（32 字节）
        self.server_fingerprint = ''   # 服务端指纹短码
        self.encrypted = False         # 本次连接是否已启用传输加密
        self.cipher = None             # 会话加解密器（SessionCipher）

    def _locked_send(self, msg_type, payload=''):
        """发送一帧。加密会话建立后自动把正文加密（与旧协议兼容）。"""
        with self._send_lock:
            if self.cipher is not None:
                payload = remote_server.make_enc_payload(self.cipher, payload)
            send_frame(self.sock, msg_type, payload)

    def _recv(self):
        """收一帧。返回 (type, plain_body)；连接关闭返回 None。"""
        resp = recv_frame(self.sock)
        if resp is None:
            return None
        t, body = resp
        # HELLO / DENY 是握手期的明文帧；其余在加密会话下都是密文包。
        if t in ('HELLO', 'DENY'):
            return (t, body)
        if self.cipher is not None:
            try:
                body = remote_server.open_enc_payload(self.cipher, body)
            except ValueError as e:
                raise RuntimeError(f'收到无法解密的帧（{t}）：{e}')
        return (t, body)

    def connect(self):
        """完成「密钥交换 + 鉴权」并拉取初始日志列表；失败抛出 RuntimeError。"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        try:
            self.sock.connect((self.host, self.port))
        except Exception as e:
            self.sock = None
            raise RuntimeError(f'无法连接到服务端 {self.host}:{self.port}（{e}）')
        try:
            self._handshake()
        except RuntimeError:
            raise
        except Exception as e:
            self._abort_connect()
            raise RuntimeError(f'密钥交换失败：{e}')
        self._locked_send('FETCH', '')
        # 服务端在 LOGIN 后可能立刻下发 PEERS 广播帧，FETCH 与 FILE 之间可能夹着它，
        # 因此循环读取，跳过 PEERS / SYNC 等广播帧，直到拿到 FILE。
        # 同时把途中收到的 PEERS 记下来，供同步线程首次刷新在线客户端使用。
        while True:
            resp = self._recv()
            if resp is None:
                self._abort_connect()
                raise RuntimeError('获取日志数据失败。')
            if resp[0] == 'FILE':
                break
            if resp[0] == 'PEERS':
                try:
                    self.initial_peers = json.loads(resp[1])
                except Exception:
                    self.initial_peers = []
            # 其它广播帧（SYNC / OK / PONG）忽略，继续读下一个
        try:
            self.initial_file = json.loads(resp[1])
        except Exception:
            self.initial_file = []
        _upgrade_file_records(self.initial_file)
        return True

    def _abort_connect(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.sock = None
        self.cipher = None
        self.encrypted = False

    def _handshake(self):
        """与（新）服务端做加密握手；对方是旧版明文服务端时自动回退。

        流程：
          1. 服务端发 HELLO（长期公钥 + 指纹）；
          2. 本地核对指纹（首次/变更由 verify_fingerprint 决定是否继续）；
          3. 程序生成随机会话密钥，与登录信息一起用 X25519 派生的密钥加密后回 HELLO_ACK；
          4. 服务端回 LOGIN 表示握手与鉴权都通过。
        若首帧不是 HELLO（旧服务端在等 AUTH），则退回明文 AUTH，保证向后兼容。
        """
        first = self._recv()
        if first is None:
            self._abort_connect()
            raise RuntimeError('服务端未响应。')
        if first[0] == 'LOGIN':
            # 极端情况：旧服务端直接认了（不会发生，但别崩）
            self.encrypted = False
            return
        if first[0] != 'HELLO':
            self._abort_connect()
            raise RuntimeError('服务端响应异常，无法建立连接。')
        try:
            pub, raw_pub, short = remote_crypto.parse_hello(first[1])
        except ValueError as e:
            self._abort_connect()
            raise RuntimeError(f'服务端公钥无效：{e}')
        self.server_key = raw_pub
        self.server_fingerprint = short
        # 指纹核对：回调返回 False 表示用户拒绝（或指纹与记录不符且用户选择中止）
        if self.verify_fingerprint is not None:
            if not self.verify_fingerprint(short, raw_pub):
                self._abort_connect()
                raise RuntimeError('已取消连接：未通过服务端身份核对。')
        session_key = remote_crypto.new_session_key()
        client_priv = remote_crypto.generate_server_key()   # 每次连接一对临时密钥
        ack, _ = remote_crypto.make_hello_ack(raw_pub, client_priv, session_key,
                                             self.password, self.role, self.display_ip)
        self._locked_send('HELLO_ACK', ack)
        # cipher 必须在收到 LOGIN 之前挂上：服务端在 LOGIN 之后发的帧都是密文
        self.cipher = remote_crypto.SessionCipher(session_key)
        self.encrypted = True
        resp = self._recv()
        if resp is None or resp[0] != 'LOGIN':
            self._abort_connect()
            raise RuntimeError('登录失败：密码错误或服务端拒绝连接。')

    def send_save(self, file_list):
        """把当前全部日志覆盖式保存到服务端。"""
        data = json.dumps(file_list, ensure_ascii=False)
        try:
            self._locked_send('SAVE', data)
        except Exception as e:
            raise RuntimeError(f'保存失败：{e}')

    def start_sync(self, on_sync, on_disconnect):
        """启动后台同步线程：每秒向服务端拉取一次最新日志。"""
        self._start_heartbeat()
        self._sync = _SyncThread(self, on_sync, on_disconnect)
        # 信号跨线程投递到 GUI 线程执行，保证表格刷新/弹窗线程安全
        self._sync.sync_signal.connect(on_sync)
        self._sync.disconnect_signal.connect(on_disconnect)
        self._sync.start()

    def _start_heartbeat(self, interval=1.0):
        """启动轻量心跳：每 interval 秒补发一帧 NEXT，让服务端始终在空闲阈值内收到本客户端数据。

        必要性：同步方式是「发 FETCH → 读取整份日志」。日志较大时（例如包含大量历史条目，
        base64 数据），读取会占用较长时间，期间同步线程发不出 FETCH；服务端按
        「2 秒未收到任何信息即视为退出」的规则就会把客户端踢掉，客户端随之中止同步
        （表现为「日志无法同步」）。心跳线程独立于日志传输，可避免这种误判。
        """
        if self._hb_thread is not None and self._hb_thread.is_alive():
            return
        self._hb_stop.clear()

        def _loop():
            while not self._hb_stop.wait(interval):
                if self.sock is None:
                    return
                try:
                    self._locked_send('NEXT', '')
                except Exception:
                    return

        self._hb_thread = threading.Thread(target=_loop, daemon=True)
        self._hb_thread.start()

    def _stop_heartbeat(self):
        self._hb_stop.set()

    def stop_sync(self, wait_ms=3000):
        """停止后台同步线程并等待其真正退出（避免 QThread 在运行中被销毁）。"""
        sync = self._sync
        if sync is None:
            return
        sync.stop()
        try:
            if sync.isRunning():
                sync.wait(wait_ms)
        except Exception:
            pass

    def _close_socket(self):
        """给服务端发 QUIT 退出指令并关闭 socket（幂等）。"""
        self._stop_heartbeat()
        if self.sock is not None:
            try:
                self._locked_send('QUIT', '')
            except Exception:
                pass
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def close(self):
        """退出多人日志：先给服务端发 QUIT 退出指令，再关闭连接。

        即使 QUIT 未能送达（如网络已断），服务端也会在 CLIENT_IDLE_TIMEOUT（2 秒）
        内因收不到本客户端任何信息而自动清理，因此无需强依赖 QUIT。
        """
        self._close_socket()

    def shutdown(self):
        """完整退出多人日志（客户端退出 / 关闭窗口 / 切换连接时使用）。

        顺序很关键：必须**先**把同步线程标记为停止，再关闭 socket、最后 join 线程。
        否则线程会因 socket 被关闭而走「连接断开」分支，向已经离开会话的窗口误报断开提示。
        """
        sync = self._sync
        if sync is not None:
            sync.stop()          # 先置位：线程后续不再上报「连接断开」
        self._close_socket()     # 关闭连接会立刻解除 recv 阻塞，使线程尽快退出
        if sync is not None:
            try:
                if sync.isRunning():
                    sync.wait(3000)
            except Exception:
                pass


class _SyncThread(QThread):
    """后台线程：每秒向服务端拉取一次最新日志（FETCH→FILE，拉取式同步），
    同时接收 PEERS 广播以刷新在线客户端列表。"""
    sync_signal = Signal(list)
    disconnect_signal = Signal()
    peers_signal = Signal(list)

    def __init__(self, conn, on_sync, on_disconnect):
        super().__init__()
        self.conn = conn
        self._on_sync = on_sync
        self._on_disconnect = on_disconnect
        self._running = True
        # 用握手期收到的在线客户端列表播种，新加入的客户端立即可见
        self.last_peers = list(getattr(conn, 'initial_peers', []) or [])

    def run(self):
        import time as _t
        fails = 0
        while self._running:
            t0 = _t.monotonic()
            try:
                # 每秒向服务端拉取一次最新日志（拉取式同步；FETCH 也兼作保活心跳）
                self.conn._locked_send('FETCH', '')
                self.conn.sock.settimeout(10.0)
                while self._running:
                    resp = self.conn._recv()
                    if resp is None:
                        # 对端已关闭连接（服务端结束/被断开）：明确上报断开。
                        # 主动退出（关闭窗口 / 关闭多人日志）已把 _running 置 False，
                        # 此处不得再上报断开提示。
                        if self._running:
                            self._running = False
                            self.disconnect_signal.emit()
                        return
                    t, body = resp
                    if t == 'FILE':
                        fails = 0
                        try:
                            self.sync_signal.emit(json.loads(body))
                        except Exception:
                            pass
                        break
                    elif t == 'PEERS':
                        try:
                            self.last_peers = json.loads(body)
                        except Exception:
                            self.last_peers = []
                        try:
                            self.peers_signal.emit(self.last_peers)
                        except Exception:
                            pass
                    # SYNC / OK / PONG 忽略：下一次 FETCH 会拉到最新
            except socket.timeout:
                # 本次拉取超时：跳过，稍后重试
                pass
            except Exception:
                # 发送/接收瞬时异常（网络抖动等）：先连续重试几次，避免一次抖动就
                # 永久中止同步（表现为「日志无法同步」且窗口看不出异常）。
                fails += 1
                if fails >= 3:
                    if self._running:
                        self._running = False
                        self.disconnect_signal.emit()
                    return
            # 固定 1 秒周期：把「传输耗时」计入周期，避免日志较大时周期被拉长到
            # 服务端的空闲阈值（2 秒）之上而被判为退出。
            _t.sleep(max(0.0, 1.0 - (_t.monotonic() - t0)))

    def stop(self):
        self._running = False


def main(window, filee='', save_path='', key_=None, quick_poject=False, recovered=False,
         remote=None, is_host=False, server=None):
    global file,key
    key = key_
    if isinstance(filee, list):
        file = filee
        _upgrade_file_records(file)
        # 打开项目时自动校验所有呼号（己方 m_call 与对方 o_call），统一转为大写
        for _rec in file:
            if 'm_call' in _rec:
                _rec['m_call'] = _rec['m_call'].upper()
            if 'o_call' in _rec:
                _rec['o_call'] = _rec['o_call'].upper()
    else:
        file = []

    # 远程后端状态：运行时可经「多人日志管理」动态挂载/卸载（避免新建窗口即可联机）
    window._remote = remote
    window._is_host = False
    window._remote_sync = None
    window._is_host = is_host
    window._server = server
    window._aes_action = None
    window._local_title = ''
    def _rc():
        return window._remote

    # ---------- 未保存内容自动备份（project_backup.fhl） ----------
    # 以「已持久化内容」快照为基准，任何偏离（未保存更改）都会周期性写入备份；
    # 正常保存后清空备份。window 关闭时若有未保存更改则弹『保存/不保存/取消』。
    #
    # 多人日志下「已持久化」的含义不同：内容由服务端持续持有并落盘，所以基线跟随服务端
    # 内容走（每次同步即视为已保存），本机不再写“未保存”备份；退出多人日志后，持久化
    # 责任回到本机文件，再以「最近一次写入本机文件的内容」为基线重新判断——只有内容相对
    # 本机文件确有变化才算未保存，避免把会话期间他人造成的变化误报成本机的未保存更改。
    def _bk_json():
        return json.dumps(file, ensure_ascii=False, sort_keys=True)

    _bk_init = _bk_json()
    _bk_state = {
        'last': _bk_init,    # 当前“已持久化”基线（多人日志下 = 服务端已持有的内容）
        'local': _bk_init,   # 最近一次写入本机文件的内容（退出多人日志后作基线）
    }
    # 本会话最近一次「真正写到本机文件」的路径与内容：用于跳过重复的整份重写，
    # 又不会误跳过首次保存（详见 save() 内注释）。
    _last_written = {'path': None, 'json': None}

    def _bk_snapshot(snap=None):
        """把当前内容记为「已持久化」。

        单人模式：内容已写入本机文件 → 同时更新“本机文件基线”。
        多人日志：内容已由服务端持有（本次同步 / 已推送）→ 只更新“已持久化”基线，
        不动本机文件基线（退出会话后靠它判断内容相对本机文件是否有变化）。

        snap：可传入已算好的 _bk_json() 结果，避免同一份内容被重复序列化。
        """
        if snap is None:
            snap = _bk_json()
        _bk_state['last'] = snap
        if _rc() is None:
            _bk_state['local'] = snap
        _refresh_title()   # 内容已持久化 → 去掉标题里的未保存标记

    def _bk_is_dirty():
        try:
            return _bk_json() != _bk_state['last']
        except Exception:
            return False

    def _bk_on_remote_exit():
        """退出多人日志后重算基线：持久化责任回到本机文件。

        只有「内容相对最近一次写入本机文件确有变化」才标记为未保存（哨兵值 ''）；
        无变化则保持干净，关闭窗口时不会无端提示保存。
        """
        try:
            snap = _bk_json()
        except Exception:
            return
        _bk_state['last'] = snap if snap == _bk_state.get('local', '') else ''
        _refresh_title()   # 基线变了 → 同步标题上的未保存标记

    def _bk_write(force=False):
        # 多人日志：内容由服务端持有并落盘，本机不写“未保存”备份——否则下次启动会误报
        # “恢复未保存的内容”，把共享会话日志当成未保存内容恢复、覆盖本机项目。
        # force=True 仅由关闭守卫的「不保存」分支使用（确有未同步内容时才需要留备份）。
        if _rc() is not None and not force:
            return
        if not file:
            backup.clear_backup(backup.PROJECT_BACKUP)
            return
        backup.write_backup(backup.PROJECT_BACKUP, file, key)

    def _bk_clear():
        backup.clear_backup(backup.PROJECT_BACKUP)

    # ---------- 窗口标题的「未保存」标记 ----------
    # 约定：标题最前面加一个 '*' 表示当前内容相对「已持久化」有未保存更改。
    # 标题由「前缀（* 或空）+ 基标题」组成；基标题 = 多人日志标题 或 window._local_title。
    # 所有 setWindowTitle 都经 _set_title 走，保证 * 在任何标题下都统一、且保存后能自动去掉。
    def _title_base():
        """当前应展示的「基标题」（不含 * 前缀）。"""
        if _rc() is not None:
            _role = '服务端' if window._is_host else '客户端'
            return f'F HamLog 2 - 多人日志（{_role}） {window._remote.host}:{window._remote.port}'
        return window._local_title or 'F HamLog 2'

    def _set_title(base=None):
        """设置窗口标题，并按当前是否有未保存更改加上 '*' 前缀。

        base：显式传入基标题（如断开后的「... - 多人日志已断开」）；
              不传则按 _title_base() 推导（多人日志 / 本地项目标题）。
        """
        try:
            dirty = _bk_is_dirty()
        except Exception:
            dirty = False
        title = _title_base() if base is None else base
        window.setWindowTitle(('*' if dirty else '') + i18n.tr(title))

    def _refresh_title():
        """重算并应用标题（内容变化 / 保存完成后调用，用于同步 * 标记）。"""
        if not _qt_alive(window):
            return
        try:
            _set_title()
        except Exception:
            pass

    def _bk_close_texts():
        """关闭守卫文案：多人日志下「保存」实为「同步到服务端」。"""
        if _rc() is not None:
            return {
                'title': '未同步到服务端',
                'text': '有内容尚未同步到服务端，是否立即同步？',
                'save': '同步',
                'discard': '不同步',
            }
        return {}

    table = None
    undo_stack = []   # 撤销栈：保存 file 的完整深拷贝快照
    redo_stack = []   # 重做栈
    # 勾选行的行号集合（O(1) 全选/反选/查询；上万行时不再逐行遍历控件）
    _checked_rows = set()

    def _sync_check_items(tbl, rows, checked):
        """把行号集合的勾选状态批量写回表格 item。

        冻结刷新，避免上万次 setData 触发重绘。
        """
        if tbl is None:
            return
        prev = tbl.updatesEnabled()
        tbl.setUpdatesEnabled(False)
        for r in rows:
            it = tbl.item(r, 0)
            if it is not None:
                it.setData(_CHECK_ROLE, bool(checked))
        tbl.setUpdatesEnabled(prev)

    def _row_checked(r):
        """读取某行当前勾选状态（以集合为准，集合缺失时回退读 item）。"""
        if r in _checked_rows:
            return True
        if table is not None:
            it = table.item(r, 0)
            if it is not None:
                return bool(it.data(_CHECK_ROLE))
        return False

    def _tbl_check_toggle(row, checked):
        """勾选单元格被点击时触发：同步更新集合与 item（委托只回调、不直接改 model）。"""
        if checked:
            _checked_rows.add(row)
        else:
            _checked_rows.discard(row)
        if table is not None:
            it = table.item(row, 0)
            if it is not None:
                it.setData(_CHECK_ROLE, bool(checked))

    # ---------- 撤销 / 重做 / 复制 / 粘贴 ----------
    def snapshot_before():
        # 在修改 file 之前调用，记录当前完整状态到撤销栈（深拷贝，避免后续修改污染快照）
        undo_stack.append(copy.deepcopy(file))
        if len(undo_stack) > 300:
            undo_stack.pop(0)
        redo_stack.clear()

    def undo():
        global file
        if not undo_stack:
            toast_tip.show_toast("没有可撤销的操作。", window)
            return
        redo_stack.append(copy.deepcopy(file))
        file = undo_stack.pop()
        table_update()

    def redo():
        global file
        if not redo_stack:
            toast_tip.show_toast("没有可重做的操作。", window)
            return
        undo_stack.append(copy.deepcopy(file))
        file = redo_stack.pop()
        table_update()

    def get_selected_row_indexes():
        # 优先返回“选择”列勾选的行；若都没有勾选，则回退到表格当前选中的行
        result = []
        if table is None:
            return result
        if _checked_rows:
            return [r for r in sorted(_checked_rows) if 0 <= r < table.rowCount()]
        for idx in table.selectionModel().selectedRows():
            result.append(idx.row())
        return result

    def copy_records_to_clipboard(records):
        if not records:
            return False
        lines = ['\t'.join(COPY_FIELDS)]
        for rec in records:
            lines.append('\t'.join(str(rec.get(k, '')) for k in COPY_FIELDS))
        QApplication.clipboard().setText('\n'.join(lines))
        return True

    def copy_from_main():
        rows = get_selected_row_indexes()
        if not rows:
            toast_tip.show_toast("请先勾选或选中要复制的行。", window)
            return
        records = [file[r] for r in rows]
        if copy_records_to_clipboard(records):
            toast_tip.show_toast(f"已复制 {len(records)} 条日志到剪贴板。", window)

    def paste_to_main():
        text = QApplication.clipboard().text()
        if not text or not text.strip():
            toast_tip.show_toast("剪贴板为空或不是文本。", window)
            return
        lines = [ln for ln in text.replace('\r\n', '\n').split('\n') if ln != '']
        if not lines:
            return
        header = [h.strip() for h in lines[0].split('\t')]
        label_to_field = {v: k for k, v in FIELD_LABELS.items()}
        field_index = {}
        for i, h in enumerate(header):
            if h in COPY_FIELDS:
                field_index[h] = i
            elif h in label_to_field:
                field_index[label_to_field[h]] = i
        if not field_index:
            toast_tip.show_toast("剪贴板内容无法识别为日志数据。", window, kind='warning')
            return
        new_records = []
        for ln in lines[1:]:
            cells = ln.split('\t')
            rec = {k: '' for k in COPY_FIELDS}
            for fld, idx in field_index.items():
                if idx < len(cells):
                    rec[fld] = cells[idx]
            new_records.append(rec)
        if not new_records:
            return
        snapshot_before()
        file.extend(new_records)
        table_update()
        toast_tip.show_toast(f"已粘贴 {len(new_records)} 条日志。", window)


    def table_context_menu(pos):
        menu = QMenu(window)
        a1 = QAction('全选', window); a1.triggered.connect(lambda: set_all_rows_checked(True)); menu.addAction(a1)
        a2 = QAction('反选', window); a2.triggered.connect(invert_rows_checked); menu.addAction(a2)
        a3 = QAction('取消选择', window); a3.triggered.connect(lambda: set_all_rows_checked(False)); menu.addAction(a3)
        menu.addSeparator()
        a4 = QAction('复制', window); a4.triggered.connect(copy_from_main); menu.addAction(a4)
        a5 = QAction('粘贴', window); a5.triggered.connect(paste_to_main); menu.addAction(a5)
        menu.addSeparator()
        a6 = QAction('撤销', window); a6.triggered.connect(undo); menu.addAction(a6)
        a7 = QAction('重做', window); a7.triggered.connect(redo); menu.addAction(a7)
        menu.exec(table.viewport().mapToGlobal(pos))

    # 表格列定义：(表头, 取值函数)。取值函数直接读 file 里的记录 dict。
    # 注意：表头顺序与宽度必须与「搜索结果」窗口保持一致（下方 table_r 亦复用本常量）。
    _TABLE_HEADERS = ["选择", "日期", "时间", "己方呼号", "对方呼号", "频率",
                      "调制模式", "传播模式", "卫星名称", "己方接收信号", "对方接收信号",
                      "己方QTH", "对方QTH", "更多"]
    _TABLE_COL_WIDTHS = [45, 80, 70, 90, 90, 70, 80, 90, 90, 80, 80, 120, 120, 80]
    # 数据列（1..12）对应的记录字段；列 0 = 勾选、列 13 = 更多按钮，不走文本
    _TABLE_FIELDS = ['date', 'time', 'm_call', 'o_call', 'freq', 'mode', 'prop_mode',
                     'sat_name', 'm_rst', 'o_rst', 'm_qth', 'o_qth']
    # 行数达到该值以上时，重建表格期间显示等待光标（几百毫秒的操作有明显感知）
    _BUSY_CURSOR_THRESHOLD = 2000

    def _new_table(rows, parent=None, on_toggle=None):
        """按统一列定义创建一个已配好列宽/委托的表格（主表与搜索结果表共用）。

        on_toggle(row, checked)：勾选单元格被点击时的回调。主表用 _tbl_check_toggle
        （同步 _checked_rows）；搜索结果窗口传入自己的处理函数（同步到主表）。

        关键性能点：先冻结刷新、批量填充、最后统一解冻，避免每 setItem 都触发重绘。
        UI 与旧实现保持一致：不使用 stretchLastSection，14 列全部显式设宽（含末列），
        行高沿用 Qt 默认（旧代码的 setDefaultSectionSize 本就是注释掉的）。
        """
        tbl = QTableWidget(rows, len(_TABLE_HEADERS))
        if parent is not None:
            tbl.setParent(parent)
        tbl.setHorizontalHeaderLabels(_TABLE_HEADERS)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        tbl.setUpdatesEnabled(False)        # 填充期间冻结重绘
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        # 勾选列与「更多」列用委托绘制，避免上万行各建真实控件
        if on_toggle is None:
            on_toggle = _tbl_check_toggle
        tbl.setItemDelegateForColumn(0, CheckColumnDelegate(tbl, on_toggle=on_toggle))
        tbl.setItemDelegateForColumn(len(_TABLE_HEADERS) - 1, MoreButtonDelegate(tbl))
        return tbl

    def _fill_rows(tbl, rows, more_cb):
        """把 rows（每条为 (记录 dict, ...)）批量填进表格。

        more_cb(row) 接收行号——「更多」委托按点击到的 index.row() 回调，无需逐行设回调。
        """
        more_item = tbl.itemDelegateForColumn(len(_TABLE_HEADERS) - 1)
        if more_item is not None and more_cb is not None:
            more_item.set_click(more_cb)
        fields = _TABLE_FIELDS
        last_col = len(_TABLE_HEADERS) - 1
        set_item = tbl.setItem       # 局部绑定，省去 14 万次属性查找
        for r, pair in enumerate(rows):
            rec = pair[0]
            # 勾选列：用 item 承载勾选状态（_CHECK_ROLE），由 CheckColumnDelegate 绘制/切换
            chk = QTableWidgetItem()
            chk.setData(_CHECK_ROLE, False)
            set_item(r, 0, chk)
            # 数据列：按字段顺序逐个建 item；缺字段用 ''（str(None) 会得到 'None'，需排除）
            for c, field in enumerate(fields, start=1):
                val = rec.get(field, '')
                set_item(r, c, QTableWidgetItem('' if val is None else str(val)))
            # 末列「更多」：委托绘制按钮，点击按行号回调
            set_item(r, last_col, QTableWidgetItem())
        # 列宽：与旧实现完全一致（14 列全部显式设宽，末列也是 80）
        for c, w in enumerate(_TABLE_COL_WIDTHS):
            tbl.setColumnWidth(c, w)

    def table_update(delete=True, persist=True, scroll_to_bottom=False):
        """重建主表格。

        scroll_to_bottom：仅「首次打开项目」时传 True（打开后自动跳到最后一条记录）。
        其余场景（排序、编辑、删除、导入、撤销、远程同步、点「更多」保存等）重建后会
        把垂直滚动位置恢复到重建前的像素偏移——行高统一，像素偏移可精确还原，
        避免每次重建都把视图甩回顶部（用户点「更多」保存后应停在原来那几行附近）。
        """
        nonlocal table
        # 重建前先记住当前滚动位置（旧表格即将被销毁）；行高统一，像素偏移可精确还原
        prev_scroll = None
        if table is not None:
            prev_scroll = table.verticalScrollBar().value()
        if delete:
            # 只有先把旧表格从布局移除并销毁，重建后界面才只会剩一个表格。
            # （历史上远程同步曾用 delete=False，导致旧表格残留在布局里 → 出现两个表格）
            if table is not None:
                layout.removeWidget(table)
                table.deleteLater()
            table = None
            if persist:
                list_time(message=False)
                save(message=False)

        file_length = len(file)
        # 上万行重建需数百毫秒；期间显示等待光标，避免用户以为界面卡死
        if file_length >= _BUSY_CURSOR_THRESHOLD:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            table = _new_table(file_length)
            table.customContextMenuRequested.connect(table_context_menu)
            # 重建时保持原有的勾选状态（勾选集合由 _checked_rows 承载，见 set_all_rows_checked）
            prev_checked = {i for i in _checked_rows if 0 <= i < file_length}

            # 批量填充（冻结刷新期间进行）
            rows = [(file[i],) for i in range(file_length)]
            _fill_rows(table, rows, project_others)
            _checked_rows.clear()
            _checked_rows.update(prev_checked)
            _sync_check_items(table, sorted(prev_checked), True)

            layout.addWidget(table)
            table.setUpdatesEnabled(True)   # 解冻，一次性重绘
            if scroll_to_bottom:
                # 延到事件循环下一轮，等布局算好视口高度再跳，确保真正落到最后一行
                QTimer.singleShot(0, table.scrollToBottom)
            elif prev_scroll:
                # 恢复重建前的滚动位置。延到事件循环下一轮再设，等 Qt 按新布局算好
                # 视口尺寸与滚动范围，避免设完后被布局过程重置回顶部。
                # 行数变少时 setValue 会按新的最大值自动收敛，无需手动 clamp。
                _bar = table.verticalScrollBar()
                _target = prev_scroll
                QTimer.singleShot(0, lambda: _bar.setValue(_target))
        finally:
            if file_length >= _BUSY_CURSOR_THRESHOLD:
                QApplication.restoreOverrideCursor()

    def new(preset=None):
            with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
                xml_dict = eval(f.read())
            global project_others_window,file
            index = len(file)
            date = time_.strftime("%Y-%m-%d", time_.localtime())
            time = time_.strftime("%H:%M", time_.localtime())
            file_app = {
                'date': date,
                'time': time,
                'm_call': xml_dict.get('m_call', '').upper(),
                'o_call': '',
                'freq': '',
                'freq_rx': '',
                'mode': '',
                'prop_mode': '',
                'sat_name': '',
                'm_rst': '59',
                'o_rst': '59',
                'm_qth': xml_dict.get('m_qth', ''),
                'o_qth': '',
                "m_dig": xml_dict.get('m_dig', ''),
                'o_dig': '',
                'm_ant': '',
                'o_ant': '',
                'm_pow': '',
                'o_pow': '',
                'notes': ''
            }
            if preset:
                for k in ('date', 'time', 'm_call', 'o_call', 'freq', 'freq_rx',
                          'mode', 'prop_mode', 'sat_name'):
                    v = preset.get(k)
                    if v not in (None, ''):
                        file_app[k] = v
            
            project_others_window = QMainWindow()
            project_others_window.resize(410, 680)
            project_others_window.setWindowTitle('新建日志')
            translation_dict = {
                'date': '日期',
                'time': '时间',
                'm_call': '己方呼号',
                'o_call': '对方呼号',
                'freq': '频率',
                'freq_rx': '接收频率',
                'prop_mode': '传播方式',
                'sat_name': '卫星名称',
                'mode': '调制模式',
                'm_rst': '己方接收信号','o_rst': '对方接收信号',
                'm_qth': '己方QTH','o_qth': '对方QTH',
                "m_dig": '己方设备','o_dig': '对方设备',
                'm_ant': '己方天线','o_ant': '对方天线',
                'm_pow': '己方功率','o_pow': '对方功率',
                'notes': '备注'
            }
            rows = len(translation_dict)
            table_others = QTableWidget(rows, 2)
            table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
            table_others.setColumnWidth(1, 250)
            table_others.setHorizontalHeaderLabels(["项目", "内容"])

            row = 0
            for i in translation_dict.keys():
                item = QTableWidgetItem(translation_dict[i])
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
                table_others.setItem(row, 0, item)
                item2 = QTableWidgetItem(file_app[i])  # 第2列可以编辑
                table_others.setItem(row, 1, item2)
                row += 1
            # 己方呼号(行2)与对方呼号(行3)单元格编辑时实时转大写
            _call_del = call_upper.UpperCallDelegate()
            table_others.setItemDelegateForRow(2, _call_del)
            table_others.setItemDelegateForRow(3, _call_del)
            table_others._upper_call_delegate = _call_del  # 保持引用，防止被回收
            # 字段名写在「单元格」里（不是表头），translate_widget 只翻表头不会翻它，
            # 故显式接入翻译；每次按中文原文重设，中英来回切都能正确还原。
            i18n.bind_cell_texts(project_others_window, table_others,
                                 list(translation_dict.values()), col=0)
            central_widget = QWidget()
            project_others_window.setCentralWidget(central_widget)
            layout_others = QVBoxLayout(central_widget)
            layout_others.addWidget(table_others)

            def save_changes():
                # 获取表格数据并更新到 file 结构
                keys_list = list(translation_dict.keys())
                for row in range(len(keys_list)):
                    key = keys_list[row]

                    if key == 'date':
                        if not re.search(r'^\d{4}-\d{2}-\d{2}$', table_others.item(row, 1).text()):
                                QMessageBox.warning(project_others_window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                                return
                    elif key == 'time':
                        if not re.search(r'^\d{2}:\d{2}?$', table_others.item(row, 1).text()):
                            QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                            return
                    elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                        if table_others.item(row, 1).text() == '':
                            QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                            return

                    item = table_others.item(row, 1)  # 第二列是可编辑的内容
                    if item!=None:
                        file_app[key] = item.text()
                project_others_window.close()

                snapshot_before()
                file.append(file_app)

                table_update(scroll_to_bottom=True)   # 新建日志追加在末尾 → 跳到最后一条，便于查看
            save_button = QPushButton("新建日志")
            save_button.clicked.connect(save_changes)
            layout_others.addWidget(save_button)
            
            project_others_window.show()

    def project_others(index):
        global project_others_window,file
        project_others_window = QMainWindow()
        project_others_window.resize(410, 690)
        project_others_window.setWindowTitle('更多信息')
        translation_dict = {
            'date': '日期',
            'time': '时间',
            'm_call': '己方呼号',
            'o_call': '对方呼号',
            'freq': '频率',
            'freq_rx': '接收频率',
            'prop_mode': '传播方式',
            'sat_name': '卫星名称',
            'mode': '调制模式',
            'm_rst': '己方接收信号','o_rst': '对方接收信号',
            'm_qth': '己方QTH','o_qth': '对方QTH',
            "m_dig": '己方设备','o_dig': '对方设备',
            'm_ant': '己方天线','o_ant': '对方天线',
            'm_pow': '己方功率','o_pow': '对方功率',
            'notes': '备注'
        }
        rows = len(translation_dict)
        table_others = QTableWidget(rows, 2)
        table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
        table_others.setColumnWidth(1, 250)
        table_others.setHorizontalHeaderLabels(["项目", "内容"])

        row = 0
        for i in translation_dict.keys():
            item = QTableWidgetItem(translation_dict[i])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
            table_others.setItem(row, 0, item)
            item2 = QTableWidgetItem(file[index][i])  # 第2列可以编辑
            table_others.setItem(row, 1, item2)
            row += 1
        # 己方呼号(行2)与对方呼号(行3)单元格编辑时实时转大写
        _call_del = call_upper.UpperCallDelegate()
        table_others.setItemDelegateForRow(2, _call_del)
        table_others.setItemDelegateForRow(3, _call_del)
        table_others._upper_call_delegate = _call_del  # 保持引用，防止被回收
        # 字段名写在「单元格」里（不是表头），translate_widget 只翻表头不会翻它，
        # 故显式接入翻译；每次按中文原文重设，中英来回切都能正确还原。
        i18n.bind_cell_texts(project_others_window, table_others,
                             list(translation_dict.values()), col=0)
        central_widget = QWidget()
        project_others_window.setCentralWidget(central_widget)
        layout_others = QVBoxLayout(central_widget)
        layout_others.addWidget(table_others)
        def save_changes():
            # 获取表格数据并更新到 file 结构
            keys_list = list(translation_dict.keys())
            # 先校验所有字段，校验不通过则不记录撤销点
            for row in range(len(keys_list)):
                key = keys_list[row]
                cell = table_others.item(row, 1)
                if cell is None:
                    continue  # 该行由 cell widget 承载（非文本单元格），跳过校验与写回
                text = cell.text()
                if key == 'date':
                    if not re.search(r'^\d{4}-\d{2}-\d{2}$', text):
                        QMessageBox.warning(project_others_window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                        return
                elif key == 'time':
                    if not re.search(r'^\d{2}:\d{2}$', text):
                        QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                        return
                elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                    if text == '':
                        QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                        return
            # 校验通过，记录撤销点后再写入
            snapshot_before()
            for row in range(len(keys_list)):
                key = keys_list[row]
                item = table_others.item(row, 1)  # 第二列是可编辑的内容
                if item!=None:
                    file[index][key] = item.text()
            project_others_window.close()
            table_update()
        def del_log(index):
            # 不做二次确认：直接删除，删除后以悬浮提示反馈（删除前已记撤销点，Ctrl+Z 可恢复）
            snapshot_before()
            file.pop(index)
            # 被删行之后的勾选行号需整体前移 1（并丢弃该行本身），
            # 否则重建表格时勾选状态会错位到相邻的其它日志上。
            shifted = {r - 1 if r > index else r for r in _checked_rows if r != index}
            _checked_rows.clear()
            _checked_rows.update(shifted)
            project_others_window.close()
            table_update()
            toast_tip.show_toast("已删除 1 条日志。", window)

        qrz_button = QPushButton("查看对方QRZ主页")
        def open_qrz():
            call = file[index].get('o_call','').strip()
            if call == '':
                QMessageBox.warning(project_others_window, 'QRZ', '对方呼号为空，无法打开 QRZ。')
                return
            url = f"https://www.qrz.com/db/{urllib.parse.quote_plus(call)}"
            webbrowser.open(url)
        qrz_button.clicked.connect(open_qrz)

        del_button = QPushButton("删除日志")
        del_button.clicked.connect(lambda:del_log(index))

        button_row_layout = QHBoxLayout()
        button_row_layout.setSpacing(10)
        button_row_layout.addWidget(qrz_button)
        button_row_layout.addWidget(del_button)

        layout_others.addLayout(button_row_layout)

        save_button = QPushButton("保存更改")
        save_button.clicked.connect(save_changes)
        layout_others.addWidget(save_button)
        
        
        project_others_window.show()

    def _save_recovered_as():
        # 恢复进来的项目没有原始项目文件：弹“保存恢复的文件”让用户把恢复内容
        # 另存为真实项目文件；写入后把 save_path 指向该文件并复位快照
        # （消除“未保存”标记）。之后若再次编辑，定时器会因 file 偏离快照而
        # 重新标记“未保存”。
        nonlocal save_path
        sp, _ = QFileDialog.getSaveFileName(
            window,
            i18n.tr("保存恢复的文件"),
            os.path.join(desktop_dir(), '恢复的项目.fhl'),
            "F HamLog项目 (*.fhl)")
        if sp == '':
            return False
        global key
        snap = _write_project_file(sp)
        backup.clear_backup(backup.PROJECT_BACKUP)
        save_path = sp
        _bk_snapshot(snap)  # 复位快照 → 消除“未保存”标记
        window._local_title = f'F HamLog 2 - {os.path.basename(save_path)}'
        _set_title()        # 经统一入口落标题（_bk_snapshot 已复位基线 → 不带 *）
        toast_tip.show_toast("已保存恢复的内容。", window)
        return True

    def save(message=True):
        # 多人日志模式：直接把内存中的 file 覆盖式发送到服务端，由服务端落盘/广播
        rc = _rc()
        if rc is not None:
            try:
                rc.send_save(file)
            except Exception as e:
                toast_tip.show_toast(f"无法保存到服务端：{e}", window, kind='warning')
                return False
            _bk_snapshot()
            if message:
                toast_tip.show_toast("已保存到服务端！", window)
            return True

        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())

        aouto_save_b = xml_dict['aouto_save']

        if (not(message) and aouto_save_b) or message:
            global key
            # 无保存路径：恢复项目弹“保存恢复的文件”，普通新建项目弹“另存为”。
            # 只有用户显式保存（message=True）才允许弹对话框；静默自动保存（message=False，
            # 由 table_update 等触发）没有目标文件可写，直接跳过——绝不能弹界面，否则
            # 恢复项目一打开就会自己弹出“保存恢复的文件”，随后关闭时再提示一次保存
            # （即“保存了两遍”）。静默保存失败不影响状态，仍由「未保存更改」流程兜底。
            if save_path == '':
                if not message:
                    return False
                if recovered:
                    return _save_recovered_as()
                return osave()
            # 内容未变化时跳过整份重写：table_update 每次都会静默调用 save()，
            # 上万条日志时「重建表格 + 重写整份文件」会各花一秒左右。
            # 注意：只跳过「本会话已把同样内容写到同一路径」的重复保存——首次保存
            # 仍必须执行（磁盘上的文件可能与内存不同，打开时需对齐），否则会破坏
            # 「普通项目打开即自动保存一次」的既有行为。
            _cur = _bk_json()
            if not message and _last_written.get('path') == save_path \
                    and _last_written.get('json') == _cur:
                return True
            snap = _write_project_file(save_path)
            backup.clear_backup(backup.PROJECT_BACKUP)
            _bk_snapshot(snap)
            if message:
                toast_tip.show_toast("保存成功！", window)
        return True

    def _write_project_file(path):
        """把当前 file 写到 path，并记录「本会话已写入」的路径与内容（供 save() 跳过重复写）。"""
        global key
        fhl_rw.write_fhl_file(path, file, key)
        # 顺手算一次内容快照，既记录“已写入内容”，也供调用方的 _bk_snapshot 复用
        _last_written['path'] = path
        _last_written['json'] = _bk_json()
        return _last_written['json']

    def osave():
        import json
        sp, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            i18n.tr("另存为文件"),  # 对话框标题
            desktop_dir(),  # 初始目录：桌面，默认文件名为空
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if sp == '':
            return False
        snap = _write_project_file(sp)
        backup.clear_backup(backup.PROJECT_BACKUP)
        _bk_snapshot(snap)
        toast_tip.show_toast("另存成功！", window)
        return True

    def esave():
        rc = _rc()
        if rc is not None:
            try:
                rc.send_save(file)
                toast_tip.show_toast("已保存到服务端，多人日志已关闭。", window)
            except Exception as e:
                toast_tip.show_toast("保存失败：" + str(e), window, kind='warning')
            window.close()
            return
        import json
        global key
        if save_path == '':
            # 无保存路径（恢复项目 / 新建后尚未落盘）：交给统一的保存流程
            # （恢复场景弹「保存恢复的文件」）；用户取消则保持窗口打开，
            # 避免以空路径写文件（open('') 会直接抛 FileNotFoundError）。
            if not _do_save():
                return
        else:
            # 显式「保存并退出」：无条件落盘（不做未变更跳过），确保用户意图被执行
            snap = _write_project_file(save_path)
            backup.clear_backup(backup.PROJECT_BACKUP)
            _bk_snapshot(snap)
            toast_tip.show_toast("保存成功！", window)
        sys.exit()

    def input_HAM_tolls_():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import input_HAM_tolls
        snapshot_before()
        file = input_HAM_tolls.main(file)
        table_update()
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return

    def import_from_ADI():
        global file
        old_file = file.copy()
        import input_adi
        try:
            snapshot_before()
            file = input_adi.main(file)
        except Exception as e:
            QMessageBox.warning(window, "导入失败", f"导入 ADI 失败：{e}")
            return
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return
        table_update()

    def input_fhl():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import input_fhl
        snapshot_before()
        file = input_fhl.main(file)
        table_update()
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return

    def output_adi(file):
        import output_adi

        output_adi.main(file)

    def output_excel(file):
        import output_excel
        output_excel.main(file)

    def get_selected_records():
        if table is None:
            QMessageBox.warning(window, "导出失败", "当前未加载日志表。")
            return None
        selected_records = [file[r] for r in get_selected_row_indexes()
                            if 0 <= r < len(file)]
        if not selected_records:
            QMessageBox.warning(window, "导出失败", "请先勾选要导出的日志行。")
            return None
        return selected_records

    def _get_main_checkbox(orig_index):
        # 兼容旧接口：返回布尔「是否勾选」而非控件（勾选列已改为委托绘制）
        if table is None:
            return None
        if orig_index < 0 or orig_index >= table.rowCount():
            return None
        return _row_checked(orig_index)

    def set_main_checkbox(orig_index, checked):
        # 将搜索结果的勾选状态同步到主页面对应行（只更新集合 + 单个 item）
        if table is None or orig_index < 0 or orig_index >= table.rowCount():
            return
        if checked:
            _checked_rows.add(orig_index)
        else:
            _checked_rows.discard(orig_index)
        it = table.item(orig_index, 0)
        if it is not None:
            it.setData(_CHECK_ROLE, bool(checked))

    def output_selected_fhl():
        selected_records = get_selected_records()
        if not selected_records:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            window,
            i18n.tr("导出选中日志为FHL文件"),
            desktop_dir(),
            "F HamLog项目 (*.fhl)"
        )
        if not save_path:
            return
        global key
        fhl_rw.write_fhl_file(save_path,selected_records,key)

            
        QMessageBox.information(window, "导出成功", f"已导出 {len(selected_records)} 条记录到：\n{save_path}")

    def output_selected_adi():
        selected_records = get_selected_records()
        if not selected_records:
            return
        import output_adi
        output_adi.main(selected_records)

    def output_selected_excel():
        selected_records = get_selected_records()
        if not selected_records:
            return
        import output_excel
        output_excel.main(selected_records)

    # 恢复场景：不弹“新建文件”对话框（否则一打开就逼用户选路径）。
    # 待用户真正点击“保存”时，再由 save()/_do_save 弹出“保存恢复的文件”。
    # 多人日志模式（本机开放服务端 / 加入他人多人日志）不需要本地项目文件，跳过选择。
    if save_path == '' and not recovered and remote is None:
        save_path, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            i18n.tr("新建文件"),  # 对话框标题
            desktop_dir(),  # 初始目录：桌面，默认文件名为空
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if save_path == '':
            return
    print(save_path)
    window.resize(1350, 700)
    if _rc() is not None:
        # 断并多人日志后恢复用的本地标题（而非多人日志标题本身）
        window._local_title = 'F HamLog 2'
    elif quick_poject:
        window._local_title = 'F HamLog 2 - 通联日志'
    elif save_path:
        window._local_title = f'F HamLog 2 - {os.path.basename(save_path)}'
    else:
        window._local_title = 'F HamLog 2 - 恢复的项目'
    # 统一由 _set_title 落标题（按未保存状态决定是否带 * 前缀）；
    # 此刻 _bk_state 尚未按打开内容复位，先按「当前内容」占位，
    # 稍后 _bk_snapshot()/recovered 分支会再刷新一次。
    _set_title()
    # window.showMaximized()
    # 创建菜单栏
    menu_bar = window.menuBar()

    # 创建"文件"菜单
    file_menu = menu_bar.addMenu('文件')

    save_action = QAction('保存', window)
    save_action.setShortcut('Ctrl+S')
    save_action.triggered.connect(lambda: save())
    file_menu.addAction(save_action)

    osave_action = QAction('另存为', window)
    osave_action.setShortcut('Ctrl+Shift+S')
    osave_action.triggered.connect(lambda: osave())
    file_menu.addAction(osave_action)

    file_menu.addSeparator()

    def aes_open_():
        global key
        QMessageBox.information(window,'加密项目','F HamLog 将使用AES加密项目，\n请牢记你的密钥！若密钥丢失则无法恢复日志数据。')
        key = fhl_rw.get_user_key_dialog()
        list_time(message=False)
        save(message=False)
        QMessageBox.information(window,'加密项目','加密成功！\n请重新打开此项目。')
        window.close()
    def aes_close_():
        global key
        input_key = fhl_rw.get_user_key_dialog()
        if input_key == key:
            key = None
            list_time(message=False)
            save(message=False)
            QMessageBox.information(window,'解密项目','解密成功！\n请重新打开此项目。')
            window.close()
        else:
            QMessageBox.warning(window,'解密项目','密钥错误！')

    aes_action = None
    if key is None and _rc() is None:
        aes_action = QAction('加密此项目', window)
        aes_action.setShortcut('Ctrl+Alt+E')
        aes_action.triggered.connect(aes_open_)
        file_menu.addAction(aes_action)
    elif key is not None:
        aes_action = QAction('不再加密此项目', window)
        aes_action.setShortcut('Ctrl+Alt+E')
        aes_action.triggered.connect(aes_close_)
        file_menu.addAction(aes_action)
    # 多人日志模式：不显示加密菜单（与服务端后端互斥）
    window._aes_action = aes_action


    '''file_menu.addSeparator()

    def open_main_page():
        # 打开主页面：启动 main.py 启动器窗口（与程序入口一致）
        import subprocess, sys, os
        main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
        try:
            subprocess.Popen([sys.executable, main_py])
        except Exception as e:
            QMessageBox.warning(window, '打开主页面失败', str(e))

    open_main_action = QAction('打开主页面', window)
    open_main_action.setShortcut('Ctrl+Shift+M')
    open_main_action.triggered.connect(open_main_page)
    file_menu.addAction(open_main_action)'''

    file_menu.addSeparator()

    sexit_action = QAction('保存并退出', window)
    sexit_action.triggered.connect(lambda: esave())
    file_menu.addAction(sexit_action)

    zexit_action = QAction('退出', window)
    zexit_action.triggered.connect(lambda: sys.exit())
    file_menu.addAction(zexit_action)

    def delete_selected_logs():
        '''删除主表格中选中的日志：优先删除“选择”列已勾选的行；
        若未勾选任何行，则回退删除当前高亮选中的行。不做二次确认（直接删除），
        删除前记撤销点（Ctrl+Z 可恢复），删除后自动重建表格、落盘并悬浮提示。'''
        if table is None:
            toast_tip.show_toast("当前未加载日志表。", window, kind='warning')
            return
        # 1) 优先收集“选择”列（第0列）中已勾选的行
        checked_rows = [r for r in sorted(_checked_rows) if 0 <= r < table.rowCount()]
        # 2) 若未勾选任何行，回退到当前高亮选中的行
        if not checked_rows:
            rows = set()
            for rng in table.selectedRanges():
                for r in range(rng.topRow(), rng.bottomRow() + 1):
                    rows.add(r)
            checked_rows = sorted(rows)
        if not checked_rows:
            toast_tip.show_toast(
                "没有可删除的日志：请先在“选择”列勾选要删除的行，或直接选中（高亮）这些行。",
                window, kind='warning')
            return
        # 不做二次确认：直接删除，删除后以悬浮提示反馈（删除前已记撤销点，Ctrl+Z 可恢复）
        count = len(checked_rows)
        # 记撤销点，随后按行号从大到小删除，避免索引错位
        snapshot_before()
        for row in sorted(checked_rows, reverse=True):
            del file[row]
        # 删除后必须清空勾选集合：_checked_rows 里存的是「删除前」的行号，
        # 若不清空，table_update() 重建时会把这些旧行号当作勾选状态套用到
        # 剩余日志上，表现为「删完之后勾选跑到了别的日志上」。
        _checked_rows.clear()
        table_update()
        toast_tip.show_toast(f"已删除 {count} 条日志。", window)

    # 创建"编辑"菜单（撤销/重做/复制/粘贴/删除选中）
    edit_menu = menu_bar.addMenu('编辑')

    undo_action = QAction('撤销', window)
    undo_action.setShortcut('Ctrl+Z')
    undo_action.triggered.connect(undo)
    edit_menu.addAction(undo_action)

    redo_action = QAction('重做', window)
    redo_action.setShortcut('Ctrl+Y')
    redo_action.triggered.connect(redo)
    edit_menu.addAction(redo_action)

    edit_menu.addSeparator()

    copy_action = QAction('复制', window)
    copy_action.setShortcut('Ctrl+C')
    copy_action.triggered.connect(copy_from_main)
    edit_menu.addAction(copy_action)

    paste_action = QAction('粘贴', window)
    paste_action.setShortcut('Ctrl+V')
    paste_action.triggered.connect(paste_to_main)
    edit_menu.addAction(paste_action)

    edit_menu.addSeparator()

    delete_selected_action = QAction('删除选中的日志', window)
    delete_selected_action.setShortcut('Ctrl+D')
    delete_selected_action.triggered.connect(delete_selected_logs)
    edit_menu.addAction(delete_selected_action)

    def set_all_rows_checked(checked):
        # 全选/取消选择：只改内存中的勾选集合 + 一次性写回 item，O(n) 但不建控件、不逐行重绘
        if table is None:
            return
        n = table.rowCount()
        if checked:
            _checked_rows.clear()
            _checked_rows.update(range(n))
        else:
            _checked_rows.clear()
        _sync_check_items(table, range(n), checked)

    def invert_rows_checked():
        # 反选：集合补集运算，O(n)；写回 item 期间冻结刷新
        if table is None:
            return
        n = table.rowCount()
        inverted = set(range(n)) - _checked_rows
        _checked_rows.clear()
        _checked_rows.update(inverted)
        prev = table.updatesEnabled()
        table.setUpdatesEnabled(False)
        for r in range(n):
            it = table.item(r, 0)
            if it is not None:
                it.setData(_CHECK_ROLE, r in inverted)
        table.setUpdatesEnabled(prev)

    select_menu = menu_bar.addMenu('选择')

    select_all_action = QAction('全选', window)
    select_all_action.setShortcut('Ctrl+A')
    select_all_action.triggered.connect(lambda: set_all_rows_checked(True))
    select_menu.addAction(select_all_action)

    invert_action = QAction('反选', window)
    invert_action.setShortcut('Ctrl+I')
    invert_action.triggered.connect(invert_rows_checked)
    select_menu.addAction(invert_action)

    deselect_action = QAction('取消选择', window)
    deselect_action.setShortcut('Ctrl+Shift+A')
    deselect_action.triggered.connect(lambda: set_all_rows_checked(False))
    select_menu.addAction(deselect_action)


    import_menu = menu_bar.addMenu('导入/导出')

    import_from_ADI_action = QAction('从ADI导入日志', window)
    import_from_ADI_action.triggered.connect(lambda: import_from_ADI())
    import_menu.addAction(import_from_ADI_action)

    input_fhl_action = QAction('从 F HamLog 导入日志', window)
    input_fhl_action.triggered.connect(lambda: input_fhl())
    import_menu.addAction(input_fhl_action)

    input_HAM_tolls_action = QAction('从 旧版 HAM个人工具 导入日志', window)
    input_HAM_tolls_action.triggered.connect(lambda: input_HAM_tolls_())
    import_menu.addAction(input_HAM_tolls_action)

    import_menu.addSeparator()

    export_adi_action = QAction('导出ADI文件', window)
    export_adi_action.triggered.connect(lambda: output_adi(file))
    import_menu.addAction(export_adi_action)

    export_excel_action = QAction('导出为表格', window)
    export_excel_action.triggered.connect(lambda: output_excel(file))
    import_menu.addAction(export_excel_action)

    import_menu.addSeparator()
    export_selected_menu = import_menu.addMenu('导出选中的日志')

    export_selected_adi_action = QAction('导出选中的日志为ADI', window)
    export_selected_adi_action.triggered.connect(output_selected_adi)
    export_selected_menu.addAction(export_selected_adi_action)

    export_selected_excel_action = QAction('导出选中的日志为表格', window)
    export_selected_excel_action.triggered.connect(output_selected_excel)
    export_selected_menu.addAction(export_selected_excel_action)

    export_selected_fhl_action = QAction('导出选中的日志为 F HamLog 项目文件', window)
    export_selected_fhl_action.triggered.connect(output_selected_fhl)
    export_selected_menu.addAction(export_selected_fhl_action)

    # ---------- 选择菜单：全选 / 反选 / 取消选择 ----------
    

    def list_time(message=True):
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())
        
        aouto_list_b = xml_dict['aouto_list']
        if (not(message) and aouto_list_b) or message:
            try:
                file.sort(key=lambda x: (x.get('date', ''), x.get('time', '')))
                
                if message:
                    table_update()
                    QMessageBox.information(window, "排序完成", "按时间排序完成。")
            except Exception as e:
                QMessageBox.warning(window, "排序失败", str(e))

    def research_call(file_param=None):
        global research_window
        # 弹出高级搜索对话：选择字段 + 关键词 + 匹配方式
        dlg = QDialog(window)
        dlg.resize(320, 180)
        dlg.setWindowTitle('搜索')
        dlg_layout = QVBoxLayout(dlg)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('字段：'))
        combo = QComboBox()
        choices = [
            ('o_call', '对方呼号'),
            ('m_call', '己方呼号'),
            ('date', '日期'),
            ('time', '时间'),
            ('freq', '频率'),
            ('mode', '调制模式'),
            ('m_dig', '己方设备'),
            ('o_dig', '对方设备'),
            ('m_qth', '己方QTH'),
            ('o_qth', '对方QTH'),
            ('m_ant', '己方天线'),
            ('o_ant', '对方天线'),
            ('m_pow', '己方功率'),
            ('o_pow', '对方功率'),
            ('notes', '备注')
        ]
        for k, v in choices:
            combo.addItem(v, k)
        h1.addWidget(combo)
        dlg_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('关键词：'))
        edit = QLineEdit()
        # 选中的字段为己方/对方呼号时，关键词输入实时转大写
        call_upper.connect_callsign_upper(edit, lambda: combo.currentData())
        h2.addWidget(edit)
        dlg_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('匹配方式：'))
        match_combo = QComboBox()
        match_combo.addItems(['包含', '完全匹配'])
        h3.addWidget(match_combo)
        dlg_layout.addLayout(h3)

        h_scope = QHBoxLayout()
        h_scope.addWidget(QLabel('范围：'))
        scope_combo = QComboBox()
        scope_combo.addItems(['全部通联记录', '仅选中的行'])
        h_scope.addWidget(scope_combo)
        dlg_layout.addLayout(h_scope)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo.currentData()
        q = edit.text().strip().casefold()
        if q == '':
            QMessageBox.information(window, '搜索', '请输入关键词。')
            return
        exact = (match_combo.currentText() == '完全匹配')
        scope = scope_combo.currentText()

        def record_text(record, name):
            value = record.get(name, '')
            return '' if value is None else str(value)

        matches = []
        for i, rec in enumerate(file):
            val = record_text(rec, field).casefold()
            if (exact and val == q) or (not exact and q in val):
                matches.append((i, rec))

        # 范围：仅选中的行 → 仅保留主页面勾选（或当前选中）的记录
        if scope == '仅选中的行':
            selected = set(get_selected_row_indexes())
            matches = [(i, rec) for i, rec in matches if i in selected]

        if not matches:
            QMessageBox.information(window, "搜索结果", "未找到任何匹配记录。")
            return

        research_window = QMainWindow()
        # 宽度 1300 → 1350：为新增的「定位到此条」列留出空间
        research_window.resize(1350, 600)
        research_window.setWindowTitle(f"搜索结果：{edit.text().strip()}")
        central = QWidget()
        research_window.setCentralWidget(central)
        lay = QVBoxLayout(central)

        search_checkboxes = []  # [(table_row, orig_index), ...] 在下方填写
        # 搜索结果勾选状态（性能优化，与主表 _checked_rows 同思路）：
        #   _sr_checked_rows     —— 已勾选行对应的「原始索引」集合（统计/导出/同步判定的权威）
        #   _sr_checked_rows_idx —— 已勾选行对应的「搜索结果行号」集合（绘制/全选反选用）
        # 两者同步维护；委托只回调、不直接改 model，统一由下面几个函数写回 item。
        _sr_checked_rows = set()
        _sr_checked_rows_idx = set()

        # 搜索结果窗口的勾选状态：以集合为准，O(1) 查询
        def _sr_set_row(row, checked):
            """写单行勾选状态：同时更新两个集合与 item，并同步到主表。"""
            it = table_r.item(row, 0) if table_r is not None else None
            if it is not None:
                it.setData(_CHECK_ROLE, bool(checked))
            if 0 <= row < len(search_checkboxes):
                orig = search_checkboxes[row][1]
                if checked:
                    _sr_checked_rows.add(orig)
                    _sr_checked_rows_idx.add(row)
                else:
                    _sr_checked_rows.discard(orig)
                    _sr_checked_rows_idx.discard(row)
                set_main_checkbox(orig, checked)

        def _sr_set_all(checked):
            """全选 / 取消选择：集合整体赋值（O(n) 但只做集合运算），
            写回 item 期间冻结刷新，避免上万次 setData 触发重绘。"""
            if table_r is None:
                return
            if checked:
                _sr_checked_rows_idx.clear()
                _sr_checked_rows_idx.update(range(table_r.rowCount()))
                _sr_checked_rows.clear()
                for _row, orig in search_checkboxes:
                    _sr_checked_rows.add(orig)
            else:
                _sr_checked_rows_idx.clear()
                _sr_checked_rows.clear()
            prev = table_r.updatesEnabled()
            table_r.setUpdatesEnabled(False)
            try:
                for r in range(table_r.rowCount()):
                    it = table_r.item(r, 0)
                    if it is not None:
                        it.setData(_CHECK_ROLE, checked)
            finally:
                table_r.setUpdatesEnabled(prev)
            # 一次写回主表（避免逐行 _row_checked 的重复遍历）
            for _row, orig in search_checkboxes:
                set_main_checkbox(orig, checked)

        # 选择逻辑：与 project.py 主窗口一致（全选 / 反选 / 取消选择）
        def _search_select_all():
            _sr_set_all(True)

        def _search_select_none():
            _sr_set_all(False)

        def _search_invert():
            """反选：集合补集运算，O(n)，不逐行读 item。"""
            if table_r is None:
                return
            n = table_r.rowCount()
            new_idx = set(range(n)) - _sr_checked_rows_idx
            _sr_checked_rows_idx.clear()
            _sr_checked_rows_idx.update(new_idx)
            _sr_checked_rows.clear()
            for r in new_idx:
                if 0 <= r < len(search_checkboxes):
                    _sr_checked_rows.add(search_checkboxes[r][1])
            prev = table_r.updatesEnabled()
            table_r.setUpdatesEnabled(False)
            try:
                for r in range(n):
                    it = table_r.item(r, 0)
                    if it is not None:
                        it.setData(_CHECK_ROLE, r in new_idx)
            finally:
                table_r.setUpdatesEnabled(prev)
            for r, orig in search_checkboxes:
                set_main_checkbox(orig, r in new_idx)

        # 仅针对当前搜索结果（matches）的统计与导出
        def _search_records():
            return [rec for _, rec in matches]

        # 搜索结果统计的范围解析：全部通联记录 / 全部搜索结果 / 仅选中的行（搜索窗口勾选的行）
        def _stat_scope_resolver(scope):
            if scope == '全部通联记录':
                return file
            if scope == '仅选中的行':
                return [file[orig] for orig in sorted(_sr_checked_rows)]
            return [rec for _, rec in matches]  # 全部搜索结果

        def _export_search_fhl():
            recs = _search_records()
            if not recs:
                QMessageBox.warning(research_window, "导出失败", "没有可导出的搜索结果。")
                return
            save_path, _ = QFileDialog.getSaveFileName(
                research_window, i18n.tr("导出搜索结果为FHL文件"), desktop_dir(), i18n.tr("F HamLog项目 (*.fhl)"))
            if not save_path:
                return
            fhl_rw.write_fhl_file(save_path, recs, key)
            QMessageBox.information(research_window, "导出成功", f"已导出 {len(recs)} 条记录到：\n{save_path}")

        def _export_search_adi():
            recs = _search_records()
            if not recs:
                return
            import output_adi
            output_adi.main(recs)

        def _export_search_excel():
            recs = _search_records()
            if not recs:
                return
            import output_excel
            output_excel.main(recs)

        # 菜单栏“选择”：快捷键与主窗口一致（Ctrl+A 全选 / Ctrl+I 反选 / Ctrl+D 取消选择）
        _mb = research_window.menuBar()
        _sel_menu = _mb.addMenu('选择')
        _sel_all = QAction('全选', research_window)
        _sel_all.setShortcut('Ctrl+A')
        _sel_all.triggered.connect(_search_select_all)
        _sel_menu.addAction(_sel_all)
        _sel_inv = QAction('反选', research_window)
        _sel_inv.setShortcut('Ctrl+I')
        _sel_inv.triggered.connect(_search_invert)
        _sel_menu.addAction(_sel_inv)
        _sel_none = QAction('取消选择', research_window)
        _sel_none.setShortcut('Ctrl+Shift+A')
        _sel_none.triggered.connect(_search_select_none)
        _sel_menu.addAction(_sel_none)

        # 功能：统计图（仅统计当前搜索结果），与主窗口“功能”菜单一致
        _func_menu = _mb.addMenu('功能')
        _stat_act = QAction('统计图', research_window)
        _stat_act.setShortcut('Ctrl+Shift+P')
        _stat_act.triggered.connect(lambda: show_statistics(
            parent=research_window,
            scope_labels=['全部通联记录', '全部搜索结果', '仅选中的行'],
            scope_resolver=_stat_scope_resolver,
            default_scope='全部搜索结果'))
        _func_menu.addAction(_stat_act)

        # 导入/导出：与主窗口“导入/导出”菜单完全一致
        # 导入项复用主窗口函数（导入进主项目）；导出项仅限当前搜索结果
        _imp_menu = _mb.addMenu('导入/导出')
        _imp_adi = QAction('从ADI导入日志', research_window)
        _imp_adi.triggered.connect(lambda: import_from_ADI())
        _imp_menu.addAction(_imp_adi)
        _imp_fhl = QAction('从 F HamLog 导入日志', research_window)
        _imp_fhl.triggered.connect(lambda: input_fhl())
        _imp_menu.addAction(_imp_fhl)
        _imp_ham = QAction('从 旧版 HAM个人工具 导入日志', research_window)
        _imp_ham.triggered.connect(lambda: input_HAM_tolls_())
        _imp_menu.addAction(_imp_ham)
        _imp_menu.addSeparator()
        _exp_adi = QAction('导出ADI文件', research_window)
        _exp_adi.triggered.connect(_export_search_adi)
        _imp_menu.addAction(_exp_adi)
        _exp_xls = QAction('导出为表格', research_window)
        _exp_xls.triggered.connect(_export_search_excel)
        _imp_menu.addAction(_exp_xls)
        _imp_menu.addSeparator()
        _exp_sel_menu = _imp_menu.addMenu('导出选中的日志')
        _exp_sel_adi = QAction('导出选中的日志为ADI', research_window)
        _exp_sel_adi.triggered.connect(_export_search_adi)
        _exp_sel_menu.addAction(_exp_sel_adi)
        _exp_sel_xls = QAction('导出选中的日志为表格', research_window)
        _exp_sel_xls.triggered.connect(_export_search_excel)
        _exp_sel_menu.addAction(_exp_sel_xls)
        _exp_sel_fhl = QAction('导出选中的日志为 F HamLog 项目文件', research_window)
        _exp_sel_fhl.triggered.connect(_export_search_fhl)
        _exp_sel_menu.addAction(_exp_sel_fhl)

        # 顶部提示栏（已取消 全选 / 全不选 按钮）
        top_row = QHBoxLayout()
        hint = QLabel('勾选下方记录，选择结果会自动同步到主页面的选择框（Ctrl+A 全选 / Ctrl+I 反选 / Ctrl+D 取消选择）')
        hint.setStyleSheet(theme.hint_css())
        top_row.addWidget(hint)
        top_row.addStretch(1)
        lay.addLayout(top_row)

        # 新增"选择"列（列0），其余列整体右移一列；复用统一表格定义（委托绘制，支持上万行）
        # search_checkboxes 在下方填表时按行号预分配（[(row, orig_index), ...]）

        def _sr_toggle(row, checked):
            """搜索结果窗口勾选被点击：更新集合/item，并同步到主表对应行。"""
            _sr_set_row(row, checked)

        def _search_more_cb(row):
            # 「更多」按搜索结果行号 → 映射回主 file 的原始索引
            project_others(matches[row][0])

        def _locate_in_main(row):
            """定位到此条：聚焦主窗口，把主表滚动到该条并选中高亮。

            按搜索结果行号 → 映射回主 file 的原始索引 → 主表行号（两者当前一一对应）。
            主表被重建过（如编辑后）时原始索引仍与行号一致（file 未做重排），
            但仍做一次边界校验，避免越界。
            """
            if not (0 <= row < len(matches)):
                return
            orig = matches[row][0]
            if table is None or not (0 <= orig < table.rowCount()):
                toast_tip.show_toast("主窗口日志表尚未就绪，无法定位。", window, kind='warning')
                return
            # 1) 聚焦主窗口（还原最小化/置于最前并激活）
            try:
                if window.isMinimized():
                    window.showNormal()
                window.raise_()
                window.activateWindow()
            except Exception:
                pass
            # 2) 滚动到该行并选中高亮
            item = table.item(orig, 0)
            if item is not None:
                table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
            table.clearSelection()
            table.selectRow(orig)
            table.setCurrentCell(orig, 0)

        table_r = _new_table(len(matches), on_toggle=_sr_toggle)
        # 搜索结果表在主表列定义之后追加一列「定位到此条」（仅搜索结果窗口有），
        # 故需在创建后覆盖表头与列宽，并给该列挂上定位委托。
        _SR_HEADERS = _TABLE_HEADERS + ["定位到此条"]
        _SR_COL_WIDTHS = _TABLE_COL_WIDTHS + [80]
        table_r.setColumnCount(len(_SR_HEADERS))
        table_r.setHorizontalHeaderLabels(_SR_HEADERS)
        locate_col = len(_SR_HEADERS) - 1
        _locate_delegate = LocateButtonDelegate(table_r)
        _locate_delegate.set_click(_locate_in_main)
        table_r.setItemDelegateForColumn(locate_col, _locate_delegate)
        # 性能优化（与主表 _fill_rows 同思路）：填充期间由 _new_table 冻结刷新，
        # 循环内不再逐行解冻；最后统一解冻一次性重绘。
        # 局部绑定 setItem 与常量，省去数万次属性查找；search_checkboxes 预分配，
        # 按行号索引写回，避免逐行 append 的重复扩容。
        _set_item = table_r.setItem
        _fields = _TABLE_FIELDS
        last_col = len(_TABLE_HEADERS) - 1
        search_checkboxes = [None] * len(matches)
        clear_sr = _sr_checked_rows.clear
        clear_sr_idx = _sr_checked_rows_idx.clear
        clear_sr()
        clear_sr_idx()
        for row, (orig_index, rec) in enumerate(matches):
            # 初始勾选状态与主页面保持一致（以主表勾选集合为准，O(1)）
            checked = bool(_row_checked(orig_index))
            if checked:
                _sr_checked_rows.add(orig_index)
                _sr_checked_rows_idx.add(row)
            it = QTableWidgetItem()
            it.setData(_CHECK_ROLE, checked)
            _set_item(row, 0, it)
            for c, field in enumerate(_fields, start=1):
                val = rec.get(field, '')
                _set_item(row, c, QTableWidgetItem('' if val is None else str(val)))
            _set_item(row, last_col, QTableWidgetItem())
            _set_item(row, locate_col, QTableWidgetItem())
            search_checkboxes[row] = (row, orig_index)
        # 列宽与旧实现一致（14 列全部显式设宽，末列也是 80），末列后追加「定位到此条」
        for c, w in enumerate(_SR_COL_WIDTHS):
            table_r.setColumnWidth(c, w)
        table_r.itemDelegateForColumn(last_col).set_click(_search_more_cb)
        table_r.setUpdatesEnabled(True)
        lay.addWidget(table_r)
        table_r.scrollToBottom()

        # 搜索结果表格右键菜单：定位到此条 / 复制选中行 / 全选 / 反选 / 取消选择
        # （复制的记录可粘贴到主窗口或 Excel）
        def _search_context_menu(pos):
            menu = QMenu(window)
            # 右键所在行（无有效行时禁用「定位」）；定位多行时取第一行
            _r = table_r.indexAt(pos).row()
            act_locate = QAction('定位到此条', window)
            act_locate.triggered.connect(lambda: _locate_in_main(_r))
            act_locate.setEnabled(_r >= 0)
            menu.addAction(act_locate)
            menu.addSeparator()
            act_copy = QAction('复制选中行', window)
            def do_copy():
                # 勾选集合为先（O(1) 判定），未勾选时回退到表格高亮选中行
                recs = [file[orig] for orig in sorted(_sr_checked_rows)]
                if not recs:
                    for idx in table_r.selectionModel().selectedRows():
                        recs.append(file[matches[idx.row()][0]])
                if not recs:
                    toast_tip.show_toast("请先勾选要复制的行。", window)
                    return
                if copy_records_to_clipboard(recs):
                    toast_tip.show_toast(f"已复制 {len(recs)} 条日志到剪贴板。", window)
            act_copy.triggered.connect(do_copy)
            menu.addAction(act_copy)
            menu.addSeparator()
            act_all = QAction('全选', window); act_all.triggered.connect(_search_select_all); menu.addAction(act_all)
            act_inv = QAction('反选', window); act_inv.triggered.connect(_search_invert); menu.addAction(act_inv)
            act_none = QAction('取消选择', window); act_none.triggered.connect(_search_select_none); menu.addAction(act_none)
            menu.exec(table_r.viewport().mapToGlobal(pos))

        table_r.setContextMenuPolicy(Qt.CustomContextMenu)
        table_r.customContextMenuRequested.connect(_search_context_menu)

        # 双击任意非勾选/非按钮单元格 → 同样定位到主窗口该条（与「定位到此条」按钮等价）
        def _search_double_click(index):
            if index is None or not index.isValid():
                return
            if index.column() in (0, last_col, locate_col):
                return
            _locate_in_main(index.row())

        table_r.cellDoubleClicked.connect(_search_double_click)

        research_window.show()

    def find_replace():
        # 按字段查找替换：选择字段 + 查找文本 + 替换文本 + 匹配方式 + 范围，批量替换
        dlg = QDialog(window)
        dlg.setWindowTitle('查找替换')
        dlg.resize(300, 200)
        dlg_layout = QVBoxLayout(dlg)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('字段：'))
        combo = QComboBox()
        choices = [
            ('o_call', '对方呼号'),
            ('m_call', '己方呼号'),
            ('date', '日期'),
            ('time', '时间'),
            ('freq', '频率'),
            ('mode', '调制模式'),
            ('prop_mode', '传播方式'),
            ('sat_name', '卫星名称'),
            ('m_dig', '己方设备'),
            ('o_dig', '对方设备'),
            ('m_qth', '己方QTH'),
            ('o_qth', '对方QTH'),
            ('m_ant', '己方天线'),
            ('o_ant', '对方天线'),
            ('m_pow', '己方功率'),
            ('o_pow', '对方功率'),
            ('notes', '备注')
        ]
        for k, v in choices:
            combo.addItem(v, k)
        h1.addWidget(combo)
        dlg_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('查找：'))
        find_edit = QLineEdit()
        # 选中的字段为己方/对方呼号时，查找与替换输入实时转大写
        call_upper.connect_callsign_upper(find_edit, lambda: combo.currentData())
        h2.addWidget(find_edit)
        dlg_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('替换为：'))
        replace_edit = QLineEdit()
        call_upper.connect_callsign_upper(replace_edit, lambda: combo.currentData())
        h3.addWidget(replace_edit)
        dlg_layout.addLayout(h3)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel('匹配方式：'))
        match_combo = QComboBox()
        match_combo.addItems(['包含', '完全匹配'])
        h4.addWidget(match_combo)
        dlg_layout.addLayout(h4)

        h5 = QHBoxLayout()
        h5.addWidget(QLabel('范围：'))
        scope_combo = QComboBox()
        scope_combo.addItems(['全部通联记录', '仅选中的行'])
        h5.addWidget(scope_combo)
        dlg_layout.addLayout(h5)

        def compute_matches():
            # 返回 (匹配行索引列表, 预计替换处数)；匹配不区分大小写，与“搜索”一致
            field = combo.currentData()
            q = find_edit.text()
            exact = (match_combo.currentText() == '完全匹配')
            scope = scope_combo.currentText()
            if q == '':
                return [], 0
            qlow = q.lower()
            matches = []
            for i, rec in enumerate(file):
                val = str(rec.get(field, ''))
                if (exact and val.lower() == qlow) or (not exact and qlow in val.lower()):
                    matches.append(i)
            if scope == '仅选中的行':
                selected = set(get_selected_row_indexes())
                matches = [i for i in matches if i in selected]
            change_count = 0
            for i in matches:
                val = str(file[i].get(field, ''))
                change_count += 1 if exact else len(re.findall(re.escape(q), val, re.IGNORECASE))
            return matches, change_count

        btns = QDialogButtonBox()
        replace_btn = QPushButton('替换')
        replace_btn.setDefault(True)
        replace_btn.clicked.connect(dlg.accept)
        btns.addButton(replace_btn, QDialogButtonBox.AcceptRole)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(dlg.reject)
        btns.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo.currentData()
        q = find_edit.text()
        rep = replace_edit.text()
        exact = (match_combo.currentText() == '完全匹配')
        scope = scope_combo.currentText()

        if q == '':
            QMessageBox.information(window, '查找替换', '请输入查找内容。')
            return

        matches, change_count = compute_matches()
        if not matches:
            QMessageBox.information(window, '查找替换', '没有找到匹配的记录。')
            return

        snapshot_before()
        affected = 0
        total = 0
        for i in matches:
            val = str(file[i].get(field, ''))
            if exact:
                if val.lower() == q.lower():
                    file[i][field] = rep
                    affected += 1
                    total += 1
            else:
                if q.lower() in val.lower():
                    file[i][field] = re.sub(re.escape(q), rep, val, flags=re.IGNORECASE)
                    affected += 1
                    total += len(re.findall(re.escape(q), val, re.IGNORECASE))
        table_update()
        QMessageBox.information(window, '查找替换',
                                f'替换完成：影响 {affected} 条记录，共 {total} 处替换。')

    def show_statistics(records=None, parent=None, scope_labels=None, scope_resolver=None, default_scope=None):
        global file
        owner = parent if parent is not None else window
        dlg = QDialog(owner)
        dlg.setWindowTitle('统计图')  # 窗口标题
        dlg.resize(320,100)
        dlg_layout = QVBoxLayout(dlg)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('字段：'))
        combo_stat = QComboBox()
        stat_choices = [
            ('o_call', '对方呼号'),  # 添加对方呼号统计
            ('mode', '调制模式'),
            ('freq', '频率'),
            ('prop_mode', '传播方式'),
            ('sat_name', '卫星名称'),
            ('m_qth', '己方QTH'),
            ('o_qth', '对方QTH'),
            ('m_dig', '己方设备'),
            ('o_dig', '对方设备'),
            ('notes', '备注')
        ]
        for k, v in stat_choices:
            combo_stat.addItem(v, k)
        h1.addWidget(combo_stat)
        dlg_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('图表类型：'))
        chart_combo = QComboBox()
        chart_combo.addItems(['条形图', '扇形图'])
        h2.addWidget(chart_combo)
        dlg_layout.addLayout(h2)

        # 范围：自定义（如搜索结果按 全部搜索结果/仅选中的行）或默认（主窗口 全部通联记录/仅选中的行）
        if scope_labels is not None:
            label_list = scope_labels
        elif records is None:
            label_list = ['全部通联记录', '仅选中的行']
        else:
            label_list = None
        if label_list is not None:
            h_scope = QHBoxLayout()
            h_scope.addWidget(QLabel('范围：'))
            scope_combo = QComboBox()
            scope_combo.addItems(label_list)
            if default_scope is not None:
                scope_combo.setCurrentText(default_scope)
            h_scope.addWidget(scope_combo)
            dlg_layout.addLayout(h_scope)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo_stat.currentData()
        chart_type = chart_combo.currentText()

        # 数据来源
        if scope_labels is not None:
            data = scope_resolver(scope_combo.currentText())
        elif records is not None:
            data = records
        else:
            scope = scope_combo.currentText()
            if scope == '仅选中的行':
                selected = set(get_selected_row_indexes())
                data = [file[i] for i in selected]
            else:
                data = file

        # 统计各项出现次数
        counts = {}
        for rec in data:
            val = str(rec.get(field, '')).strip()
            if val == '':
                val = '<空>'
            counts[val] = counts.get(val, 0) + 1

        if not counts:
            QMessageBox.information(owner, '统计', '没有可统计的数据。')
            return

        # 绘图
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            # 设置中文字体
            matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
            matplotlib.rcParams['axes.unicode_minus'] = False  # 正常显示负号
        except Exception:
            QMessageBox.warning(owner, '缺少依赖', '未安装 matplotlib，请运行: pip install matplotlib')
            return

        labels = list(counts.keys())
        values = list(counts.values())

        plt.figure(figsize=(8, 6))
        if chart_type == '条形图':
            plt.bar(labels, values)
            plt.xticks(rotation=45, ha='right')
            plt.ylabel('次数')
        else:
            plt.pie(values, labels=labels, autopct='%1.1f%%')

        # 使用自定义标题或默认标题
        display_map = {k: v for k, v in stat_choices}
        plt.title(f"{display_map.get(field, field)} 统计")
        plt.tight_layout()
        plt.show()

    tool_menu = menu_bar.addMenu('功能')

    list_action = QAction('按时间排序', window)
    list_action.setShortcut('Ctrl+L')
    list_action.triggered.connect(lambda: list_time())
    tool_menu.addAction(list_action)

    tool_menu.addSeparator()

    stats_action = QAction('统计图', window)
    stats_action.setShortcut('Ctrl+Shift+P')
    stats_action.triggered.connect(lambda: show_statistics())
    tool_menu.addAction(stats_action)

    research_call_action = QAction('搜索', window)
    research_call_action.setShortcut('Ctrl+R')
    research_call_action.triggered.connect(lambda: research_call(file))
    tool_menu.addAction(research_call_action)

    find_replace_action = QAction('查找替换', window)
    find_replace_action.setShortcut('Ctrl+H')
    find_replace_action.triggered.connect(lambda: find_replace())
    tool_menu.addAction(find_replace_action)


    # ---------- 记录功能菜单 ----------
    sat_menu = menu_bar.addMenu('记录')

    def append_to_project(records):
        """复用卫星过境窗口“记录”按钮的保存逻辑：把记录（一条或多条）直接追加到
        当前打开的项目文件并落盘（不再弹出保存方式选择）。"""
        snapshot_before()
        for rec in records:
            file.append(rec)
        table_update(scroll_to_bottom=True)   # 新记录追加在末尾 → 跳到最后一条，便于查看
        # 直接落盘到当前项目文件（不依赖自动保存开关，也不弹“保存成功”）
        global key
        if _rc() is not None:
            # 多人日志：追加即同步到服务端
            try:
                _rc().send_save(file)
            except Exception as e:
                toast_tip.show_toast('保存失败：' + str(e), window, kind='warning')
        else:
            if save_path:
                fhl_rw.write_fhl_file(save_path, file, key)
            else:
                # 恢复项目 / 尚未落盘的新建项目：没有目标文件可写 → 交给统一的保存流程
                # （恢复场景弹「保存恢复的文件」）；用户取消则提前返回，内容继续以
                # 「未保存」状态留在内存与备份中，不清空备份也不复位快照。
                if not _do_save():
                    return
        # 追加即落盘：视为已保存，清空备份并更新快照
        backup.clear_backup(backup.PROJECT_BACKUP)
        _bk_snapshot()

    def quick_log(preset):
        """由卫星过境窗口“记录”按钮回调：打开批量记录窗口并预填卫星信息。"""
        import batch_project
        bw = QMainWindow()
        bw.setWindowTitle('批量记录 - ' + str(preset.get('sat_name', '')))
        batch_project.main(bw, preset=preset, on_saved=append_to_project)
        _open_windows.append(bw)

    def open_batch_record():
        """菜单“批量记录”：直接打开批量记录窗口（不预填卫星信息），
        保存逻辑与卫星过境预测中的“记录”按钮完全一致。"""
        import batch_project
        bw = QMainWindow()
        bw.setWindowTitle('批量记录')
        batch_project.main(bw, preset=None, on_saved=append_to_project)
        _open_windows.append(bw)

    def open_satellite_window():
        import satellite_window
        satellite_window.main(window, quick_log_callback=quick_log,
                              title='卫星通联记录')

    sat_predict_action = QAction('卫星通联记录', window)
    sat_predict_action.setShortcut('Ctrl+W')
    sat_predict_action.triggered.connect(open_satellite_window)
    sat_menu.addAction(sat_predict_action)

    sat_menu.addSeparator()

    batch_action = QAction('批量记录', window)
    batch_action.setShortcut('Ctrl+B')
    batch_action.triggered.connect(open_batch_record)
    sat_menu.addAction(batch_action)
    # 通联预测入口统一收归「卫星通联记录」窗口内的「通联预测」按钮，
    # 不再在菜单单独列出。

    # ---------- 多人日志 菜单（位于“记录”与“插件”之间） ----------
    multi_menu = menu_bar.addMenu('多人日志')
    multi_action = QAction('多人日志管理', window)
    multi_action.triggered.connect(lambda: open_multiplayer_manager())
    multi_menu.addAction(multi_action)


    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    button_new = QPushButton("新建日志（Ctrl+N）", window)
    button_new.setShortcut('Ctrl+N')
    button_new.clicked.connect(lambda: new())
    layout.addWidget(button_new)

    # 暴露给外部（如主页“卫星过境”记录按钮）调用，实现快速记录
    window._new_qso = new          # 弹出预填的“新建日志”窗口
    window._quick_add = quick_log  # 直接把预填记录追加到当前项目（不弹窗）

    pack_menu = menu_bar.addMenu('插件')
    with open('file/pack_list.txt', 'r', encoding='utf-8') as f:
        pack_list = eval(f.read())
    # 在菜单栏上显示插件状态（若无插件则显示“未安装插件”）
    plugin_label = QLabel()
    plugin_label.setStyleSheet(theme.hint_css('padding: 4px;'))
    # 主题变化时重刷插件状态标签颜色（写死 gray 在深色底上偏暗）
    theme.watch_theme(window, lambda: plugin_label.setStyleSheet(
        theme.hint_css('padding: 4px;')))
    plugin_label.setAlignment(Qt.AlignCenter)
    plugin_action = QWidgetAction(window)
    plugin_action.setDefaultWidget(plugin_label)
    pack_menu.addAction(plugin_action)
    if len(pack_list) == 0:
        plugin_label.setText(i18n.tr("未安装插件，请前往 设置 安装插件"))
    else:
            plugin_action.setVisible(False)
    
    def run_pack(pack_name):
        """返回一个 QAction，触发时执行插件文件夹下的 main.py 或 run.py（使用 runpy）。"""
        action = QAction(pack_name, window)

        def handler():
            global file,key
            if key != None:
                QMessageBox.information(window,'加密项目','F HamLog 会将项目解密后提供给插件，\n请确保插件来自可信的开发者。')
            import json
            with open(f'file/pypack/{pack_name}/input.fhl','w',encoding='utf-8') as f:
                json.dump(file, f, ensure_ascii=False, indent=2)
            subprocess.run(['python', f'file/pypack/{pack_name}/main.py'])
            try:
                with open(f'file/pypack/{pack_name}/output.fhl','r',encoding='utf-8') as f:
                    snapshot_before()
                    file = json.load(f)
            except FileNotFoundError:
                QMessageBox.warning(window, "插件错误", f"插件 {pack_name} 未正确生成输出文件！")
            table_update()
            if _rc() is not None:
                # 插件修改了日志，同步回服务端
                try:
                    _rc().send_save(file)
                except Exception:
                    pass
            os.remove(f'file/pypack/{pack_name}/input.fhl')
            os.remove(f'file/pypack/{pack_name}/output.fhl')

        action.triggered.connect(handler)
        return action

    for pack in pack_list:
        pack_menu.addAction(run_pack(pack))

    table_update(delete=False)
    table_update(scroll_to_bottom=True)   # 首次打开项目：跳到最后一条记录

    # ---------- 未保存内容自动备份 / 关闭守卫 ----------
    # 打开项目时：把当前（已保存）内容写入备份作为基线；若为空则清空。
    # 恢复场景例外：恢复进来的内容尚未落盘到真实项目文件，必须保持「未保存更改」状态
    # （快照置为永不等的哨兵值，使 _bk_is_dirty() 恒为 True，关闭时会提示保存/不保存/取消），
    # 且**不回写备份**——内容本就来自备份文件；若在此回写，即便用户刚刚已把恢复内容保存
    # 成项目文件，后面的哨兵仍会把状态判脏，关闭时又被要求保存一次（即“保存了两遍”），
    # 并让下次启动再次提示恢复同一份内容。
    _bk_snapshot()
    if recovered:
        _bk_state['last'] = ''
        _bk_state['local'] = ''
    elif file:
        _bk_write()
    else:
        _bk_clear()
    _refresh_title()   # 基线复位后再刷一次标题（恢复项目保持 * 未保存；普通项目去掉 *）

    # 周期定时器：存在未保存更改时即时备份，覆盖意外关闭/崩溃场景
    def _bk_tick():
        # 多人日志：内容由服务端持续持有并落盘，本机不参与“未保存”备份
        if _rc() is not None:
            return
        if _bk_is_dirty():
            _bk_write()
        _refresh_title()   # 每次 tick 都同步标题 * 标记（内容变干净时也要去掉 *）

    _bk_timer = QTimer(window)
    _bk_timer.setInterval(1500)
    _bk_timer.timeout.connect(_bk_tick)
    _bk_timer.start()

    def _do_save():
        # 多人日志：关闭守卫中的“保存”即保存到服务端（不再弹“另存为”）
        rc = _rc()
        if rc is not None:
            return save(message=True)
        # 已有保存路径（已“保存恢复的文件”或普通项目）→ 直接保存
        if save_path:
            save(message=True)
            return True
        # 恢复场景且尚未保存：弹“保存恢复的文件”（而非“新建文件”）
        if recovered:
            return _save_recovered_as()
        # 普通新建项目（无路径）→ 弹“另存为”
        return bool(osave())

    def _on_window_close():
        """项目窗口确实关闭时调用（不含「取消」分支）。

        Qt 关闭窗口默认只是隐藏、不触发 destroyed，因此必须在此主动退多人日志：
        断开同步连接、发 QUIT；若本机是服务端，则一并停掉内嵌服务端。
        否则窗口关掉后连接仍然活着，之后服务端结束时会向已关闭的窗口误弹「连接断开」。
        """
        srv = getattr(window, '_server', None)
        if window._remote is not None or srv is not None:
            _detach_remote()
        if srv is not None:
            try:
                srv.stop()
            except Exception:
                pass

    backup.install_close_guard(window, {
        'is_dirty': _bk_is_dirty,
        # 「不保存」分支需要留一份备份以便下次恢复，故 force=True 绕过多人日志的免备份逻辑
        'write_backup': lambda: _bk_write(force=True),
        'clear_backup': _bk_clear,
        'do_save': _do_save,
        'on_close': _on_window_close,
        'texts': _bk_close_texts,
    })

    # ---------- 远程模式：挂载/卸载后端（运行时也可经「多人日志管理」动态调用） ----------
    def _attach_remote(conn, is_host=False, server=None):
        """把当前项目窗口挂载到远程后端：标题、加密菜单、后台同步一并接管。"""
        # 若已挂载其它连接（如再次「开放多人日志」），先断开旧连接，避免服务端/线程泄漏
        old = window._remote
        if old is not None and old is not conn:
            try:
                old.shutdown()
            except Exception:
                pass
        window._remote = conn
        window._is_host = is_host
        window._server = server
        window._remote_dc_shown = False
        # 仅在尚未记录时补一个本地标题，避免覆盖正常项目的原标题（断开后要恢复它）
        if not window._local_title:
            window._local_title = 'F HamLog 2'
        _set_title()   # 切到多人日志标题（基标题由 _title_base 按 _remote 推导）
        if window._aes_action is not None:
            window._aes_action.setVisible(False)
        # 进入多人日志：内容改由服务端持有（本机开放时，当前内容已作为房间初始内容），
        # 因此把当前内容记为“已持久化”。此后本机不再写“未保存”备份（见 _bk_write），
        # 避免下次启动把共享会话日志误当成未保存内容恢复、覆盖本机项目。
        try:
            _bk_snapshot()
        except Exception:
            pass

        def _on_sync(new_list):
            global file, project_others_window
            # 窗口已销毁时不再刷新表格（避免操作已删除的 C++ 对象）
            if not _qt_alive(window):
                return
            # 正在编辑“更多信息/新建日志”窗口时跳过刷新，避免覆盖正在编辑的行索引
            if project_others_window is not None and project_others_window.isVisible():
                return
            try:
                same = (json.dumps(new_list, ensure_ascii=False, sort_keys=True) ==
                        json.dumps(file, ensure_ascii=False, sort_keys=True))
            except Exception:
                same = False
            if same:
                # 本地内容与服务端一致 ⇒ 已持久化。这里也要补一次基线：本地编辑恰好等于
                # 服务端内容时（如他人先改成了同样的内容），否则会一直被判为“有未保存更改”。
                _bk_snapshot()
                return
            file = new_list
            # 沿用原有表格刷新逻辑：先移除并销毁旧表格再重建，界面始终只有一个表格。
            # persist=False 避免把刚拉取到的内容立刻再回写服务端（否则会来回同步）。
            table_update(persist=False)
            # 服务端内容即“已保存内容”：同步基线，避免把他人造成的变化误判为本机未保存更改
            # （这也是多人日志下不再无端弹「未保存的更改」、不再写本地备份的前提）。
            _bk_snapshot()

        def _on_disconnect():
            # 已主动退出（关闭窗口 / 关闭多人日志）时不再提示
            if window._remote is None:
                return
            if getattr(window, '_remote_dc_shown', False):
                return
            window._remote_dc_shown = True
            window._remote = None
            window._is_host = False
            window._server = None
            window._remote_sync = None
            # 被动断开：持久化责任回到本机文件，重算“是否有未保存更改”的基线，
            # 让会话期间累积的内容在关闭窗口时有机会被保存下来。
            _bk_on_remote_exit()
            # 窗口可能已随关闭一起销毁，触碰界面元素前先判活
            if not _qt_alive(window):
                return
            try:
                QMessageBox.warning(window, '多人日志已断开',
                                    '与多人日志服务端的连接已断开，之后的修改将不再同步到服务端。\n'
                                    '需要继续同步请重新加入多人日志。')
                if window._local_title:
                    # 标题上留标记：断线后窗口看起来仍像在会话中，容易误以为「日志没同步」
                    _set_title(f'{window._local_title} - 多人日志已断开')
                if window._aes_action is not None:
                    window._aes_action.setVisible(True)
            except Exception:
                pass

        try:
            conn.start_sync(_on_sync, _on_disconnect)
        except Exception as e:
            if _qt_alive(window):
                QMessageBox.warning(window, '同步失败', f'无法启动与服务端的同步：{e}')
        # 同步线程在 start_sync 内创建并存入 conn._sync，须在之后取用（用于读取在线客户端列表）
        window._remote_sync = getattr(conn, '_sync', None)

        # 关闭项目窗口时的统一清理：断开同步连接（客户端退出）；若本机是服务端，
        # 同时停掉内嵌服务端（多人日志随之关闭，其他客户端会被断开）。只挂一次。
        if not getattr(window, '_remote_cleanup_hooked', False):
            window._remote_cleanup_hooked = True

            def _cleanup_remote(*_a):
                # 此回调由 QMainWindow.destroyed 触发，此时 C++ 对象已被删除，
                # 只能做后端清理（restore_ui=False），绝不能再操作窗口界面。
                srv = getattr(window, '_server', None)
                _detach_remote(restore_ui=False)
                if srv is not None:
                    try:
                        srv.stop()
                    except Exception:
                        pass

            window.destroyed.connect(_cleanup_remote)

    def _detach_remote(restore_ui=True):
        """关闭多人日志 / 客户端退出：断开同步连接、发退出指令、恢复标题与加密菜单。

        restore_ui=False 用于窗口销毁（destroyed）回调：此时窗口的 C++ 对象已删除，
        必须跳过所有界面操作，否则会抛 libshiboken ... already deleted。
        """
        conn = window._remote
        if conn is not None:
            try:
                conn.shutdown()
            except Exception:
                pass
        window._remote = None
        window._is_host = False
        window._server = None
        window._remote_sync = None
        # 退出多人日志：内容不再由服务端持有，按“相对本机文件是否有变化”重算未保存基线
        _bk_on_remote_exit()
        if restore_ui and _qt_alive(window):
            if window._local_title:
                _set_title(window._local_title)   # 恢复本地项目标题（按未保存状态带 *）
            if window._aes_action is not None:
                window._aes_action.setVisible(True)

    if _rc() is not None:
        _attach_remote(remote, is_host, server)

    # ---------- 多人日志管理：类 Minecraft 的「开放 / 加入」控制窗口 ----------
    def open_multiplayer_manager():
        # 复用单例对话框：重复点击菜单只聚焦已打开的窗口，避免多实例
        dlg = getattr(window, '_mp_dialog', None)
        if _qt_alive(dlg):
            dlg.showNormal()
            dlg.raise_()
            dlg.activateWindow()
            # 窗口曾被关闭期间的连接变化（如被动断开）需在重新打开时立即反映
            cb = getattr(dlg, '_refresh_cb', None)
            if cb is not None:
                try:
                    cb()
                except Exception:
                    pass
            return
        dlg = QDialog(window)
        dlg.setWindowTitle('多人日志管理')
        # 窗口比初版加宽、加高：服务端信息里的「局域网地址 / 密钥指纹」在 470 宽时容易被折行，
        # 「已连接的设备」列表也只有几行可见；放宽后分组信息与在线用户列表都能完整展示。
        dlg.resize(640, 640)
        # 标准可最小化窗口（非模态，可最小化到任务栏）
        dlg.setWindowModality(Qt.NonModal)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowMinMaxButtonsHint)
        window._mp_dialog = dlg
        layout = QVBoxLayout(dlg)

        status = QLabel('状态：未连接')
        layout.addWidget(status)

        # ===== 服务端：开放 / 关闭多人日志 =====
        box_srv = QGroupBox('服务端')
        sv = QVBoxLayout(box_srv)
        pw_lan = QLineEdit()
        pw_lan.setEchoMode(QLineEdit.Password)
        pw_lan.setPlaceholderText('密码（可留空）')
        btn_tgl_lan = QPushButton('显示/隐藏')
        def _tgl_lan():
            if pw_lan.echoMode() == QLineEdit.Password:
                pw_lan.setEchoMode(QLineEdit.Normal)
            else:
                pw_lan.setEchoMode(QLineEdit.Password)
        btn_tgl_lan.clicked.connect(_tgl_lan)
        hl = QHBoxLayout(); hl.addWidget(QLabel('密码：')); hl.addWidget(pw_lan, 1); hl.addWidget(btn_tgl_lan)
        sv.addLayout(hl)
        btn_open = QPushButton('开放多人日志')
        sv.addWidget(btn_open)
        layout.addWidget(box_srv)

        # ===== 服务端信息（IP / 端口 / 密码）：直接显示，分别可复制；
        #        作为「服务端」分组的内容，随服务端分组一起显隐 =====
        info_w = QWidget()
        iv = QVBoxLayout(info_w)
        iv.setContentsMargins(0, 0, 0, 0)
        lbl_ip = QLabel(''); lbl_port = QLabel(''); lbl_pw = QLabel('')
        for _l in (lbl_ip, lbl_port, lbl_pw):
            _l.setTextInteractionFlags(Qt.TextSelectableByMouse)
            _l.setWordWrap(True)
        def _do_copy(lbl, btn):
            QApplication.clipboard().setText(lbl.text())
            btn.setText(i18n.tr('已复制'))
            QTimer.singleShot(800, lambda: btn.setText(i18n.tr('复制')))
        def _make_row(label_text, lbl):
            h = QHBoxLayout()
            h.addWidget(QLabel(label_text))
            h.addWidget(lbl, 1)
            b = QPushButton('复制')
            b.clicked.connect(lambda *_: _do_copy(lbl, b))
            h.addWidget(b)
            return h
        iv.addLayout(_make_row('局域网地址：', lbl_ip))
        iv.addLayout(_make_row('端口：', lbl_port))
        iv.addLayout(_make_row('密码：', lbl_pw))
        # 服务端密钥指纹：客户端首次加入时需与这串短码核对，确认没有中间人
        lbl_fp = QLabel('')
        lbl_fp.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl_fp.setWordWrap(True)
        iv.addLayout(_make_row('密钥指纹：', lbl_fp))
        fp_note = QLabel('加密传输已启用：客户端加入时请核对上面这串指纹。')
        fp_note.setWordWrap(True)
        fp_note.setStyleSheet(theme.hint_css('font-size: 11px;'))
        iv.addWidget(fp_note)
        info_w.setVisible(False)
        # 服务端信息归属于「服务端」分类：放进服务端分组内直接显示（不再单独成栏）
        sv.addWidget(info_w)

        # ===== 在线用户（服务端与客户端均可查看） =====
        box_peers = QGroupBox('已连接的设备')
        pv = QVBoxLayout(box_peers)
        list_peers = QListWidget()
        pv.addWidget(list_peers)
        lbl_peer_count = QLabel('在线用户：0')
        pv.addWidget(lbl_peer_count)
        layout.addWidget(box_peers)

        # 注意：按需求「客户端的多人日志管理不提供退出功能」，客户端本窗口只用于查看
        # 在线用户；服务端则通过上面同一个按钮「关闭多人日志」来结束。

        def _refresh():
            rc = window._remote
            is_guest = (rc is not None and not window._is_host)
            # 作为客户端加入时，本窗口仅用于查看在线用户，隐藏「服务端」分栏
            box_srv.setVisible(not is_guest)
            if rc is None:
                status.setText(i18n.tr('状态：未连接'))
                btn_open.setText(i18n.tr('开放多人日志'))
                info_w.setVisible(False)
                pw_lan.setEnabled(True)
            elif window._is_host:
                status.setText(i18n.tr(f'状态：服务端 {rc.host}:{rc.port}'))
                btn_open.setText(i18n.tr('关闭多人日志'))
                pw_lan.setEnabled(False)
                pw_lan.setText(rc.password)
                # 重新打开管理窗口时，按当前连接恢复连接信息
                lbl_ip.setText(rc.display_ip or get_lan_ip())
                lbl_port.setText(str(rc.port))
                lbl_pw.setText(rc.password or i18n.tr('（无）'))
                srv_obj = getattr(window, '_server', None)
                if srv_obj is not None and getattr(srv_obj, 'fingerprint_short', ''):
                    lbl_fp.setText(srv_obj.fingerprint_short)
                else:
                    lbl_fp.setText('（未启用加密）')
                info_w.setVisible(True)
            else:
                status.setText(f'状态：客户端 {rc.host}:{rc.port}')
                info_w.setVisible(False)

        def _update_peers():
            peers = []
            sync = getattr(window, '_remote_sync', None)
            if sync is not None:
                peers = getattr(sync, 'last_peers', []) or []
            list_peers.clear()
            if not peers:
                list_peers.addItem('（暂无其他用户）')
            else:
                for p in peers:
                    if isinstance(p, dict):
                        ip = str(p.get('ip', '?'))
                        is_srv = bool(p.get('host'))
                    else:
                        ip, is_srv = str(p), False
                    # 服务端单独标记，便于客户端区分
                    list_peers.addItem(f'{ip}（服务端）' if is_srv else ip)
            lbl_peer_count.setText(f'在线用户：{len(peers)}')

        # 定时刷新在线用户列表：无论何时重连都自动生效，无需重新绑定信号
        timer = QTimer(dlg)
        timer.setInterval(1500)
        timer.timeout.connect(_update_peers)
        timer.start()

        def _open_lan():
            import time as _t
            password = pw_lan.text()
            rooms_dir = os.path.join('file', 'remote_rooms')
            os.makedirs(rooms_dir, exist_ok=True)
            name = '多人日志_' + _t.strftime('%Y%m%d_%H%M%S')
            fhl_path = os.path.join(rooms_dir, f'{name}.fhl')
            # 以当前日志作为多人日志初始内容（见下方 start(seed_list=...) 的深拷贝）。
            # 长期密钥统一放在 file/keys/（与各房间的会话日志分开），便于查找与清理；
            # 端口默认 8000（与「加入多人日志」对话框的默认端口一致，便于相互对接）；
            # 若 8000 已被占用，则自动更换一个空闲端口，保证开放多日志不会因此失败。
            srv = LogServer(password=password, port=DEFAULT_ROOM_PORT,
                            fhl_path=fhl_path, key_dir='file')
            if srv.port_status == 'occupied':
                srv = LogServer(password=password, port=0,
                                fhl_path=fhl_path, key_dir='file')
            try:
                srv.start(seed_list=copy.deepcopy(file))
            except Exception as e:
                QMessageBox.warning(dlg, '开放失败', f'无法启动服务端：{e}')
                return
            ip, real_port = srv.address
            lan = get_lan_ip()
            # 本机即服务端：以 role=host 连回本机，并上报局域网 IP 作为对外展示地址。
            # 这是自己刚启动的服务端，无需（也不应）弹指纹核对；仍会记住公钥，
            # 以便日后以客户端身份连同一地址时能自动校验。
            def _self_verify(short_fp, raw_pub):
                remote_crypto.remember_key('127.0.0.1', real_port, raw_pub)
                return True
            conn = RemoteConnection('127.0.0.1', real_port, password,
                                    role='host', display_ip=lan,
                                    verify_fingerprint=_self_verify)
            try:
                conn.connect()
            except Exception as e:
                srv.stop()
                QMessageBox.warning(dlg, '开放失败', f'无法连接本机服务端：{e}')
                return
            _attach_remote(conn, True, srv)
            _refresh()
            _update_peers()

        def _close_lan():
            srv = window._server
            _detach_remote()
            if srv is not None:
                try:
                    srv.stop()
                except Exception:
                    pass
            lbl_ip.setText(''); lbl_port.setText(''); lbl_pw.setText('')
            info_w.setVisible(False)
            _refresh()
            _update_peers()

        def _toggle_open():
            # 本机已作为服务端开放 → 关闭；否则开放
            if window._remote is not None and window._is_host:
                _close_lan()
            else:
                _open_lan()

        btn_open.clicked.connect(_toggle_open)
        dlg._refresh_cb = _refresh   # 复用对话框重新打开时用它立即刷新状态
        _refresh()
        _update_peers()
        dlg.show()

    # 暴露内部闭包给离屏冒烟/基准脚本（不影响正常使用）
    window._perf_api = {
        'table_update': table_update,
        'set_all_rows_checked': set_all_rows_checked,
        'invert_rows_checked': invert_rows_checked,
        'get_selected_row_indexes': get_selected_row_indexes,
        'get_selected_records': get_selected_records,
        'delete_selected_logs': delete_selected_logs,
        'undo': undo,      # 供删除（已取消二次确认）的「删后仍可 Ctrl+Z 撤销」离屏验证
        'redo': redo,
        'project_others': project_others,
        'append_to_project': append_to_project,
        'new': new,
        'checked_rows': _checked_rows,
        'get_table': lambda: table,
        'research_call': research_call,   # 供搜索相关离屏冒烟脚本驱动
        '_set_title': _set_title,         # 供标题 * 标记冒烟脚本驱动
        '_bk_is_dirty': _bk_is_dirty,
        '_bk_tick': _bk_tick,
        'save': save,
    }

    window.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    i18n.install(app)
    win = QMainWindow()
    main(win)
    app.exec()