# -*- coding: utf-8 -*-
"""F HamLog 多人日志 —— 服务端引擎（纯标准库，无 GUI 依赖）。

术语统一：本功能统一称为「多人日志」；两个角色统一称为「服务端」与「客户端」。
（协议字段里的 role=host/guest 沿用旧称，host 即服务端本机、guest 即其余客户端。）

设计目标：同一份服务端代码被两处复用，做到“只写一次”：
  1) 客户端内嵌服务端：F HamLog 进程内启动一个 LogServer（本机即服务端），
     自己再以客户端身份通过 127.0.0.1 连回本机，其他客户端通过局域网 IP:端口加入。
  2) 独立服务端 F_HamLog_Remote_Log_Server：单独的 exe/GUI，只负责托管多人日志。

通信协议（基于「类型\\n长度\\n正文」的定长帧，正文为 UTF-8）：
  客户端 -> 服务端：
    AUTH\\n<json>               登录鉴权（首帧）：{"password":..., "role":"host"/"guest", "ip":"..."}
                               兼容旧版：正文直接为明文密码
    FETCH                       请求当前全部日志（客户端每秒拉取一次，实现持续同步）
    SAVE\\n<json>               提交全部日志（覆盖式保存）
    NEXT                        心跳保活（服务端回 PONG；新客户端已改用 FETCH 兼作保活）
    QUIT                        主动断开（客户端退出时发送；不发送则服务端按空闲超时清理）
  服务端 -> 客户端：
    LOGIN                       鉴权通过
    DENY                        鉴权失败（随后关闭连接）
    FILE\\n<json>                FETCH 的响应：当前全部日志
    OK                          SAVE 已被接收
    SYNC\\n<json>               广播：有其他人保存了新日志，请刷新
    PEERS\\n<json>             在线客户端列表 [{"ip":"...", "host": bool}, ...]
                               （连接/断开时广播给所有人；每次 FETCH 也会单独回给请求方，
                                 使新加入的客户端立即能看到列表）
    PONG                       NEXT 的回应

多人协作：任一客户端 SAVE 后，服务端更新内存中的日志并落盘，然后向“其他”所有在线
客户端广播 SYNC；保存方只收到 OK，避免回声循环。客户端侧每秒 FETCH 拉取最新日志
（拉取式同步），并监听 PEERS 以刷新在线客户端列表。服务端超过 CLIENT_IDLE_TIMEOUT
（2 秒）未收到某客户端任何信息即认为其已退出并清理。
"""

import socket
import select
import threading
import json
import os
import time


# ---------------------------------------------------------------------------
# 帧读写工具（客户端与服务端共用）
# ---------------------------------------------------------------------------

def _recv_line(sock):
    """从 sock 读取一行（以 \\n 结尾），返回去掉换行符的 bytes；连接关闭返回 None。"""
    buf = b''
    while True:
        ch = sock.recv(1)
        if not ch:
            return None
        if ch == b'\n':
            return buf
        buf += ch


def recv_frame(sock):
    """读取一个完整帧，返回 (type:str, body:str)；连接关闭或协议错误返回 None。"""
    t = _recv_line(sock)
    if t is None:
        return None
    l = _recv_line(sock)
    if l is None:
        return None
    try:
        n = int(l.decode('ascii'))
    except Exception:
        return None
    body = b''
    while len(body) < n:
        chunk = sock.recv(min(65536, n - len(body)))
        if not chunk:
            return None
        body += chunk
    return (t.decode('utf-8', 'replace'), body.decode('utf-8', 'replace'))


def send_frame(sock, msg_type, payload=''):
    """发送一个帧：type\\n<len(bytes)>\\n<body>。"""
    data = payload.encode('utf-8')
    header = (msg_type + '\n' + str(len(data)) + '\n').encode('utf-8')
    sock.sendall(header + data)


# 空闲超时的专用哨兵：与「连接关闭(None)」「正常帧(tuple)」区分开
_IDLE = object()
# 协议错误哨兵（帧头解析失败）
_BAD = object()


class _FrameReader:
    """带缓冲、面向连接的按帧读取器（服务端每个客户端连接一个）。

    相比 recv_frame 的「按需精确读」，这里用大块 recv + 自行缓冲，并额外解决两个问题：

    1) **空闲判定**：只有「连续 idle 秒内一个字节都没收到」才算客户端空闲退出；
       若连接上仍有数据在传输（例如日志较大、base64 录音很长，客户端正在慢慢发/收），
       读取过程中偶尔的停顿不会被误判为「已退出」。
    2) 读操作使用 select 等待可读，socket 始终保持阻塞模式（不设 settimeout），
       因此其它线程（广播 PEERS/SYNC）可以安全地并发 send，不会互相干扰超时设置。
    """

    def __init__(self, sock):
        self.sock = sock
        self.buf = b''
        self.eof = False

    def read_frame(self, idle):
        """读取一帧。

        返回 (type, body)：读到完整帧；
              _IDLE        ：idle 秒内没有任何字节到达（视为客户端空闲/已退出）；
              None         ：连接已关闭或协议错误。
        """
        deadline = time.monotonic() + idle
        while True:
            parsed = self._parse()
            if parsed is _BAD:
                return None
            if parsed is not None:
                frame, used = parsed
                self.buf = self.buf[used:]
                return frame
            if self.eof:
                return None
            remain = deadline - time.monotonic()
            if remain <= 0:
                return _IDLE
            try:
                ready, _, _ = select.select([self.sock], [], [], min(remain, 1.0))
            except (OSError, ValueError):
                return None
            if not ready:
                continue
            try:
                chunk = self.sock.recv(65536)
            except (OSError, ValueError):
                return None
            if not chunk:
                self.eof = True
                return None
            self.buf += chunk
            # 收到数据 → 重新开始计算空闲时间（正在传输不算空闲）
            deadline = time.monotonic() + idle

    def _parse(self):
        """尝试从缓冲区头部解析一个完整帧。

        返回 ((type, body), 已消耗字节数)；数据不足返回 None；协议错误返回 _BAD。
        """
        buf = self.buf
        i = buf.find(b'\n')
        if i < 0:
            # 头部行异常长（>64KB）说明对端协议不对，直接判错
            return _BAD if len(buf) > 65536 else None
        j = buf.find(b'\n', i + 1)
        if j < 0:
            return None
        try:
            n = int(buf[i + 1:j].decode('ascii'))
        except Exception:
            return _BAD
        if n < 0:
            return _BAD
        if len(buf) < j + 1 + n:
            return None
        t = buf[:i].decode('utf-8', 'replace')
        body = buf[j + 1:j + 1 + n].decode('utf-8', 'replace')
        return ((t, body), j + 1 + n)


def parse_auth(payload):
    """解析 AUTH 正文，返回 (password, role, display_ip)。

    优先按 JSON 解析 {"password":..., "role":"host"/"guest", "ip":"..."}；
    解析失败则视为旧版明文密码（role 默认 guest、无 display_ip）。
    """
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict):
            return (str(obj.get('password', '')), str(obj.get('role', 'guest')),
                    str(obj.get('ip', '')))
    except Exception:
        pass
    return (payload, 'guest', '')


def get_lan_ip():
    """返回本机用于局域网互通的 IPv4 地址（无法获取时回退 127.0.0.1）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


# ---------------------------------------------------------------------------
# 服务端
# ---------------------------------------------------------------------------

DEFAULT_PORT = 8000
DEFAULT_PASSWORD = '000000'

# 客户端空闲超时（秒）：客户端每秒都会 FETCH 一次，若超过该时间未收到该客户端
# 的任何信息，即认为其已退出，服务端主动断开并清理（无需依赖显式 QUIT）。
CLIENT_IDLE_TIMEOUT = 2.0


class LogServer:
    """轻量级多人日志服务端：内存持有日志列表，可选落盘到 .fhl。"""

    def __init__(self, password=DEFAULT_PASSWORD, host='0.0.0.0', port=0,
                 fhl_path=None, on_event=None):
        """
        :param password: 多人日志密码（字符串）
        :param host: 监听地址，默认 0.0.0.0（所有网卡）
        :param port: 监听端口，传 0 表示自动找一个空闲端口
        :param fhl_path: 日志持久化文件路径（.fhl）；为 None 则不落盘
        :param on_event: 回调 (name, **kw)，用于通知 GUI（start/client/disconnect 等）
        """
        self.password = password
        self.host = host
        self.port = int(port)
        self.fhl_path = fhl_path
        self.on_event = on_event
        self._file = []
        self._lock = threading.RLock()
        self._clients = []            # [(conn, addr), ...]
        self._clients_lock = threading.Lock()
        self._listener = None
        self._running = False
        self._actual_ip = ''
        self._actual_port = 0
        if fhl_path and os.path.exists(fhl_path):
            try:
                with open(fhl_path, 'r', encoding='utf-8') as f:
                    raw = f.read().strip()
                    if raw:
                        self._file = json.loads(raw)
            except Exception:
                self._file = []

    # ---- 只读属性 ----
    @property
    def file(self):
        with self._lock:
            return self._file

    @property
    def address(self):
        """返回 (ip, port)，未启动时为 ('', 0)。"""
        return (self._actual_ip, self._actual_port)

    @property
    def client_count(self):
        with self._clients_lock:
            return len(self._clients)

    # ---- 生命周期 ----
    def start(self, seed_list=None):
        """启动服务端。seed_list 为可选初始日志（list），传入则作为多人日志初始内容并落盘。"""
        if self._running:
            return
        if isinstance(seed_list, list):
            with self._lock:
                self._file = seed_list
            self._persist()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.port == 0:
            self.port = self._find_free_port()
        self._listener.bind((self.host, self.port))
        self._listener.listen(16)
        self._actual_port = self.port
        try:
            self._actual_ip = get_lan_ip()
        except Exception:
            self._actual_ip = '127.0.0.1'
        self._running = True
        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()
        self._emit('start', ip=self._actual_ip, port=self._actual_port)

    def stop(self):
        if not self._running:
            return
        self._running = False
        with self._clients_lock:
            for entry in self._clients:
                try:
                    entry['conn'].close()
                except Exception:
                    pass
            self._clients = []
        try:
            self._listener.close()
        except Exception:
            pass
        self._emit('stop')

    @staticmethod
    def _find_free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('0.0.0.0', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    # ---- 内部 ----
    def _emit(self, name, **kw):
        if self.on_event:
            try:
                self.on_event(name, **kw)
            except Exception:
                pass

    def _accept_loop(self):
        while self._running:
            try:
                self._listener.settimeout(1.0)
                conn, addr = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            # 每个客户端条目用 dict 保存，便于在鉴权后补写 role / 展示用 IP；
            # _lock 用于串行化对该连接的发送：应答（_handle 线程）与广播（其它客户端
            # 的 SAVE/上下线线程）可能同时往同一个 socket 写，不加锁会让帧字节交错、
            # 对端解析失败后直接断开——表现为「日志不再同步」。
            entry = {'conn': conn, 'addr': addr, 'role': 'guest', 'ip': str(addr[0]),
                     '_lock': threading.Lock()}
            with self._clients_lock:
                self._clients.append(entry)
            t = threading.Thread(target=self._handle, args=(conn, addr, entry), daemon=True)
            t.start()

    def _remove_client(self, conn):
        with self._clients_lock:
            self._clients = [e for e in self._clients if e['conn'] is not conn]
        self._emit('client', count=self.client_count)
        self._notify_peers()

    def _peers_json(self):
        """当前在线客户端列表的 JSON 文本。

        每项为 {"ip": <展示用地址>, "host": <是否服务端本机>}；host 由客户端鉴权时的
        role=host 决定（独立服务端没有内嵌服务端客户端时，全部 host=False）。
        """
        peers = []
        with self._clients_lock:
            for e in self._clients:
                peers.append({'ip': str(e.get('ip', '')), 'host': e.get('role') == 'host'})
        return json.dumps(peers)

    def _notify_peers(self):
        """向所有在线客户端广播当前在线客户端列表（PEERS 帧）。"""
        self._broadcast('PEERS', self._peers_json())

    def _send_entry(self, entry, msg_type, payload=''):
        """向单个客户端发送一帧（按条目加锁，避免多线程写同一 socket 时字节交错）。

        返回 True 表示发送成功。发送失败（对端已断开/缓冲区满等）不影响其它客户端。
        """
        conn = entry.get('conn') if isinstance(entry, dict) else None
        lock = entry.get('_lock') if isinstance(entry, dict) else None
        if conn is None or lock is None:
            return False
        with lock:
            try:
                send_frame(conn, msg_type, payload)
                return True
            except Exception:
                return False

    def _broadcast(self, msg_type, payload, exclude=None):
        with self._clients_lock:
            targets = [e for e in self._clients if e['conn'] is not exclude]
        for entry in targets:
            self._send_entry(entry, msg_type, payload)

    def _persist(self):
        if not self.fhl_path:
            return
        try:
            with self._lock:
                data = json.dumps(self._file, ensure_ascii=False, indent=2)
            _ensure_dir(self.fhl_path)
            with open(self.fhl_path, 'w', encoding='utf-8') as f:
                f.write(data)
        except Exception:
            pass

    def _handle(self, conn, addr, entry):
        reader = _FrameReader(conn)
        try:
            frame = reader.read_frame(CLIENT_IDLE_TIMEOUT)
            if frame is None or frame is _IDLE:
                return
            if frame[0] != 'AUTH':
                self._send_entry(entry, 'DENY', '')
                return
            password, role, display_ip = parse_auth(frame[1])
            if password != self.password:
                self._send_entry(entry, 'DENY', '')
                return
            # 记录鉴权信息：服务端标记与展示用 IP。
            # 内嵌服务端（客户端自建）经 127.0.0.1 连回本机服务器时，用其上报的局域网 IP 作为展示地址。
            entry['role'] = role if role in ('host', 'guest') else 'guest'
            entry['ip'] = display_ip or (str(addr[0]) if addr else '')
            self._send_entry(entry, 'LOGIN', '')
            self._emit('client', count=self.client_count)
            self._notify_peers()
            while self._running:
                # 只有「连续 CLIENT_IDLE_TIMEOUT 秒一个字节都没收到」才判为已退出；
                # 大日志/大录音传输过程中的停顿不会被误判（旧实现用 socket 超时，
                # 只要在传输中停顿 2 秒就会被踢掉，客户端随即停止同步）。
                frame = reader.read_frame(CLIENT_IDLE_TIMEOUT)
                if frame is None or frame is _IDLE:
                    break
                t, body = frame
                if t == 'FETCH':
                    # 先回一份当前在线客户端列表（仅发给请求方），保证「新加入的客户端」
                    # 无需等他人上下线即可立即看到；随后再回日志本体。
                    self._send_entry(entry, 'PEERS', self._peers_json())
                    with self._lock:
                        data = json.dumps(self._file, ensure_ascii=False)
                    if not self._send_entry(entry, 'FILE', data):
                        break
                elif t == 'SAVE':
                    try:
                        new_file = json.loads(body)
                    except Exception:
                        new_file = None
                    if isinstance(new_file, list):
                        with self._lock:
                            self._file = new_file
                        self._persist()
                        # 广播给“其他”客户端，保存方仅收 OK（避免回声）
                        self._broadcast('SYNC',
                                        json.dumps(self._file, ensure_ascii=False),
                                        exclude=conn)
                        self._send_entry(entry, 'OK', '')
                elif t == 'NEXT':
                    self._send_entry(entry, 'PONG', '')
                elif t == 'QUIT':
                    break
                else:
                    break
        except Exception:
            pass
        finally:
            self._remove_client(conn)
            try:
                conn.close()
            except Exception:
                pass


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d)
