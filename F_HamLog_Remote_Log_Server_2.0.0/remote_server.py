# -*- coding: utf-8 -*-
"""F HamLog 多人日志 —— 服务端引擎（纯标准库，无 GUI 依赖）。

术语统一：本功能统一称为「多人日志」；两个角色统一称为「服务端」与「客户端」。
（协议字段里的 role=host/guest 沿用旧称，host 即服务端本机、guest 即其余客户端。）

设计目标：同一份服务端代码被两处复用，做到“只写一次”：
  1) 客户端内嵌服务端：F HamLog 进程内启动一个 LogServer（本机即服务端），
     自己再以客户端身份通过 127.0.0.1 连回本机，其他客户端通过局域网 IP:端口加入。
  2) 独立服务端 F_HamLog_Remote_Log_Server：单独的 exe/GUI，只负责托管多人日志。

通信协议（基于「类型\\n长度\\n正文」的定长帧，正文为 UTF-8）：

  传输加密（X25519 密钥交换 + AES-256-GCM，见 remote_crypto.py）：
    连接建立后服务端先发 HELLO 公开长期公钥；客户端回 HELLO_ACK，其中用 X25519 ECDH
    派生的密钥加密了「登录信息 + 本次连接随机会话密钥」。此后双方所有帧的正文都以
    ```<json>``` 形式放在 enc 字段里用会话密钥加密——抓包只能看到帧类型与密文长度。
    密码仅用于身份认证，不参与内容加密。

  客户端 -> 服务端（密文帧的正文统一为 {"enc": "<会话密钥加密后的密文 b64>"}）：
    HELLO_ACK\\n<json>          加密握手：{"ct": <登录blob密文>, "pub": <客户端临时公钥>}
    AUTH\\n<json>               登录鉴权（旧版明文路径）：{"password":..., "role":..., "ip":...}
                               兼容更旧版：正文直接为明文密码
    FETCH                       请求当前全部日志（客户端每秒拉取一次，实现持续同步）
    SAVE\\n<json>               提交全部日志（覆盖式保存）
    NEXT                        心跳保活（服务端回 PONG；新客户端已改用 FETCH 兼作保活）
    QUIT                        主动断开（客户端退出时发送；不发送则服务端按空闲超时清理）
  服务端 -> 客户端：
    HELLO\\n<json>              服务端长期公钥与指纹（明文，客户端据此校验身份）
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

import remote_crypto


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
       若连接上仍有数据在传输（例如日志较大，客户端正在慢慢发/收），
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


def make_enc_payload(cipher, plain_text):
    """把明文包成加密帧正文：{"enc": "<密文 b64>"}。

    cipher 为 None（未加密连接）时直接返回明文，使旧客户端仍可工作。
    """
    if cipher is None:
        return plain_text
    return json.dumps({'enc': remote_crypto.b64e(cipher.encrypt(plain_text))},
                      ensure_ascii=False)


def open_enc_payload(cipher, body):
    """从加密帧正文里取出明文。

    - cipher 不为 None：要求正文为 {"enc": ...} 并解密，失败抛 ValueError；
    - cipher 为 None：正文本身即明文（旧协议）。
    """
    if cipher is None:
        return body
    try:
        obj = json.loads(body)
        package = remote_crypto.b64d(obj['enc'])
    except Exception as e:
        raise ValueError(f'加密帧正文无法解析：{e}')
    return cipher.decrypt(package)


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
                 fhl_path=None, on_event=None, key_path=None, encrypt=True,
                 key_dir=None):
        """
        :param password: 多人日志密码（字符串），仅用于身份认证
        :param host: 监听地址，默认 0.0.0.0（所有网卡）
        :param port: 监听端口，传 0 表示自动找一个空闲端口
        :param fhl_path: 日志持久化文件路径（.fhl）；为 None 则不落盘
        :param on_event: 回调 (name, **kw)，用于通知 GUI（start/client/disconnect 等）
        :param key_path: 长期密钥文件路径；为 None 则按「key_dir(或日志目录)/keys/端口」定位
        :param encrypt: 是否启用传输加密（False 仅供排障与旧客户端兼容）
        :param key_dir: 长期密钥的存放根目录（实际落在其下的 keys/ 子目录）；
                        为 None 时退化为日志文件所在目录。「开放多人日志」传 file/，
                        使密钥统一集中在 file/keys/，不与各房间日志混在一起。
        """
        self.password = password
        self.host = host
        self.port = int(port)
        self.fhl_path = fhl_path
        self.key_dir = key_dir
        self.on_event = on_event
        self.encrypt = bool(encrypt)
        self._key_path = key_path
        self._file = []
        self._lock = threading.RLock()
        self._clients = []            # [(conn, addr), ...]
        self._clients_lock = threading.Lock()
        self._listener = None
        self._running = False
        self._actual_ip = ''
        self._actual_port = 0
        # 长期密钥对：进程启动前先建好，保证「服务端信息」能立刻展示指纹；
        # 端口为 0（自动分配）时用 default 文件名，start() 后若变了再迁移一次。
        self._private_key = None
        self._public_raw = b''
        self.port_status = 'ok'       # 'ok' | 'occupied'：构造期对显式端口做一次占用探测
        self._load_keys(self.port)
        # 调用方指定了具体端口时，先探测是否可用：占用则告知调用方（可改用 port=0 自动分配），
        # 避免 start() 阶段才因 bind 失败而中断。port=0 表示自动分配，无需探测。
        if self.port:
            self.port_status = 'occupied' if is_port_in_use(self.host, self.port) else 'ok'
        if fhl_path and os.path.exists(fhl_path):
            try:
                with open(fhl_path, 'r', encoding='utf-8') as f:
                    raw = f.read().strip()
                    if raw:
                        self._file = json.loads(raw)
            except Exception:
                self._file = []

    # ---- 长期密钥 ----
    def _key_path_endswith_default(self):
        """当前密钥文件是否还是按「default」定位（端口尚未确定时）。"""
        try:
            base = os.path.splitext(os.path.basename(self._key_path or ''))[0]
        except Exception:
            return False
        return base == 'server_default'

    def _reload_keys_for_port(self, port):
        """端口确定后，按端口重新定位长期密钥（找不到就沿用 default 那份）。"""
        path = remote_crypto.key_file_for_port(
            port, _data_dir(self.fhl_path, self.key_dir))
        if not os.path.exists(path):
            # 把 default 那份改名迁移过去，保留同一身份
            try:
                _ensure_dir(path)
                if self._key_path and os.path.exists(self._key_path):
                    os.replace(self._key_path, path)
            except Exception:
                pass
        self._key_path_explicit = True
        try:
            self._private_key, self._key_created = \
                remote_crypto.load_or_create_server_key(path)
        except Exception:
            self._private_key = remote_crypto.generate_server_key()
            self._key_created = True
        self._public_raw = remote_crypto.public_key_bytes(self._private_key)
        self._key_path = path

    def _load_keys(self, port):
        if not self.encrypt:
            return
        path = self._key_path or remote_crypto.key_file_for_port(
            port, _data_dir(self.fhl_path, self.key_dir))
        self._key_path_explicit = bool(self._key_path)
        try:
            self._private_key, created = remote_crypto.load_or_create_server_key(path)
        except Exception:
            # 极端情况（目录只读等）：退化为本次会话的临时密钥，至少不阻塞启动
            self._private_key = remote_crypto.generate_server_key()
            created = True
        self._public_raw = remote_crypto.public_key_bytes(self._private_key)
        self._key_path = path
        self._key_created = created

    @property
    def fingerprint(self):
        """服务端公钥指纹（32 个十六进制字符）；未启用加密时为空串。"""
        if not self._public_raw:
            return ''
        return remote_crypto.fingerprint(self._public_raw)

    @property
    def fingerprint_short(self):
        """便于人工核对的短码（如 A1B2-C3D4-...）。"""
        if not self._public_raw:
            return ''
        return remote_crypto.fingerprint_short(self._public_raw)

    @property
    def public_key(self):
        """服务端公钥原始字节（32 字节）；未启用加密时为空。"""
        return self._public_raw

    @property
    def key_path(self):
        """长期密钥文件路径（便于 GUI 提示/排障）。"""
        return self._key_path

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
        # 端口最终确定后，若长期密钥仍是按「default」定位的，则迁移到真正的端口文件名，
        # 使同一端口每次都复用同一个身份（指纹稳定，客户端记住后无需反复核对）。
        if (self.encrypt and self._private_key is not None
                and not getattr(self, '_key_path_explicit', False)):
            if self._key_path_endswith_default():
                self._reload_keys_for_port(self.port)
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
            # cipher：加密会话建立后写入 SessionCipher，之后该连接的收发都走密文。
            entry = {'conn': conn, 'addr': addr, 'role': 'guest', 'ip': str(addr[0]),
                     '_lock': threading.Lock(), 'cipher': None}
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

        payload 为**明文**：若该连接已建立会话加密（entry['cipher'] 存在），这里负责
        加密后发送；否则按旧协议明文发送。返回 True 表示发送成功。发送失败
        （对端已断开/缓冲区满等）不影响其它客户端。
        """
        conn = entry.get('conn') if isinstance(entry, dict) else None
        lock = entry.get('_lock') if isinstance(entry, dict) else None
        if conn is None or lock is None:
            return False
        cipher = entry.get('cipher') if isinstance(entry, dict) else None
        with lock:
            try:
                send_frame(conn, msg_type, make_enc_payload(cipher, payload))
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

    def _handshake(self, entry, reader, addr):
        """加密握手：服务端先发 HELLO，客户端回 HELLO_ACK，双方确定会话密钥。

        返回 True 表示加密会话已建立（entry['cipher'] 已就绪）；
        返回 False 表示应断开（已发 DENY 或对端无响应）。
        若对端是旧版客户端（收到 HELLO 后仍发 AUTH 明文帧），同样返回 False——
        调用方据 entry['_legacy_auth'] 判断是否改走明文兼容路径。
        """
        hello = remote_crypto.make_hello(self._private_key)
        if not self._send_entry(entry, 'HELLO', hello):
            return False
        frame = reader.read_frame(CLIENT_IDLE_TIMEOUT)
        if frame is None or frame is _IDLE:
            return False
        if frame[0] == 'AUTH':
            # 旧客户端会忽略 HELLO 直接发 AUTH：记为 legacy，交由调用方按明文处理
            entry['_legacy_frame'] = frame
            return False
        if frame[0] != 'HELLO_ACK':
            self._send_entry(entry, 'DENY', '')
            return False
        try:
            info, session_key = remote_crypto.parse_hello_ack(self._private_key,
                                                              frame[1])
        except ValueError:
            # 解不开说明对端没有正确的服务端公钥（可能是中间人/被篡改）
            self._send_entry(entry, 'DENY', '')
            return False
        password = str(info.get('password', ''))
        role = str(info.get('role', 'guest'))
        display_ip = str(info.get('ip', ''))
        if password != self.password:
            self._send_entry(entry, 'DENY', '')
            return False
        entry['cipher'] = remote_crypto.SessionCipher(session_key)
        self._finish_auth(entry, addr, role, display_ip)
        return True

    def _finish_auth(self, entry, addr, role, display_ip):
        """鉴权通过后的统一收尾：记录身份、回 LOGIN、通知在线列表。"""
        # 记录鉴权信息：服务端标记与展示用 IP。
        # 内嵌服务端（客户端自建）经 127.0.0.1 连回本机服务器时，用其上报的局域网 IP 作为展示地址。
        entry['role'] = role if role in ('host', 'guest') else 'guest'
        try:
            fallback = str(addr[0]) if addr else ''
        except Exception:
            fallback = ''
        entry['ip'] = display_ip or fallback
        self._send_entry(entry, 'LOGIN', '')
        self._emit('client', count=self.client_count)
        self._notify_peers()

    def _handle(self, conn, addr, entry):
        reader = _FrameReader(conn)
        try:
            cipher = None
            if self.encrypt and self._private_key is not None:
                # 加密路径：服务端必须先开口。客户端在收到 HELLO 之前不会发任何数据，
                # 若这里先 read_frame 等对端发话，双方会一直互等到空闲超时。
                # 先发 HELLO 公开长期公钥，再等客户端用密钥交换结果答复。
                if self._handshake(entry, reader, addr):
                    cipher = entry.get('cipher')
                else:
                    # 握手未成立：可能是旧客户端（忽略 HELLO 直接发 AUTH），
                    # 也可能是密码错误/载荷非法（此时已发 DENY，直接断开）。
                    legacy = entry.get('_legacy_frame')
                    if legacy is None:
                        return
                    if not self._auth_plain(entry, addr, legacy):
                        return
            else:
                # 明文路径（服务端显式关闭加密时的正常入口）
                frame = reader.read_frame(CLIENT_IDLE_TIMEOUT)
                if frame is None or frame is _IDLE:
                    return
                if not self._auth_plain(entry, addr, frame):
                    return
            while self._running:
                # 只有「连续 CLIENT_IDLE_TIMEOUT 秒一个字节都没收到」才判为已退出；
                # 大日志传输过程中的停顿不会被误判（旧实现用 socket 超时，
                # 只要在传输中停顿 2 秒就会被踢掉，客户端随即停止同步）。
                frame = reader.read_frame(CLIENT_IDLE_TIMEOUT)
                if frame is None or frame is _IDLE:
                    break
                if not self._dispatch(entry, frame, cipher, conn):
                    break
        except Exception:
            pass
        finally:
            self._remove_client(conn)
            try:
                conn.close()
            except Exception:
                pass

    def _auth_plain(self, entry, addr, frame):
        """明文 AUTH 鉴权（旧协议兼容路径）。返回 False 表示应断开。"""
        if frame[0] != 'AUTH':
            self._send_entry(entry, 'DENY', '')
            return False
        password, role, display_ip = parse_auth(frame[1])
        if password != self.password:
            self._send_entry(entry, 'DENY', '')
            return False
        entry['cipher'] = None
        self._finish_auth(entry, addr, role, display_ip)
        return True

    def _dispatch(self, entry, frame, cipher, conn):
        """处理一个已鉴权连接上的一帧。返回 False 表示应断开该连接。"""
        t, body = frame
        if t == 'QUIT':
            return False
        # 未加密的连接 cipher 恒为 None；加密连接则要求正文是密文包，
        # 解不开（被篡改/密钥不符/重放）直接断开。
        try:
            text = open_enc_payload(cipher, body)
        except ValueError:
            return False
        if t == 'FETCH':
            # 先回一份当前在线客户端列表（仅发给请求方），保证「新加入的客户端」
            # 无需等他人上下线即可立即看到；随后再回日志本体。
            self._send_entry(entry, 'PEERS', self._peers_json())
            with self._lock:
                data = json.dumps(self._file, ensure_ascii=False)
            return self._send_entry(entry, 'FILE', data)
        if t == 'SAVE':
            try:
                new_file = json.loads(text)
            except Exception:
                new_file = None
            if isinstance(new_file, list):
                with self._lock:
                    self._file = new_file
                self._persist()
                # 广播给“其他”客户端，保存方仅收 OK（避免回声）
                self._broadcast('SYNC', json.dumps(self._file, ensure_ascii=False),
                                exclude=conn)
                self._send_entry(entry, 'OK', '')
            return True
        if t == 'NEXT':
            self._send_entry(entry, 'PONG', '')
            return True
        return False


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d)


def _can_bind(host, port):
    """能否在 (host, port) 上 bind；True=可绑定（空闲），False=被占用。

    **不要在此 socket 上设 SO_REUSEADDR**：Windows 上它会让 bind 直接“劫持”同一地址
    上已有的监听（实测 reuse=True 时对着已被监听的 127.0.0.1:port bind 会成功），
    从而完全失去探测意义。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def is_port_in_use(host, port):
    """探测 (host, port) 是否已被占用（本机视角）。

    仅用于在「开放多人日志」前给出友好提示；真正能否监听仍以 start() 的 bind 为准。

    实现用 **bind 探测**（与 start() 的 bind 语义一致）。实测要点：

    1) connect 探测不可用：settimeout 后对空闲端口返回 WSAEWOULDBLOCK(10035)，
       与占用无法区分。
    2) 探测 socket **绝不能设 SO_REUSEADDR**，否则 Windows 允许 bind 到已被监听的
       同一地址，探测恒为「空闲」。
    3) Windows 绑定语义不对称：holder 在 127.0.0.1 时，绑 0.0.0.0 会成功；
       holder 在 0.0.0.0 时，绑 127.0.0.1 会成功。**只有试探“完全相同”的地址才准**。
       本项目的服务端一律以 0.0.0.0 监听，故按 0.0.0.0 探测即为正确口径。
    """
    if not port:
        return False
    bind_host = host if host and host != '::' else '0.0.0.0'
    return not _can_bind(bind_host, port)


def _data_dir(fhl_path=None, key_dir=None):
    """长期密钥的存放根目录。

    优先级：显式 key_dir > 日志文件所在目录 > 当前目录。
    「开放多人日志」的内嵌服务端会把 key_dir 指到 file/，使密钥统一落在 file/keys/；
    独立服务端则用默认行为（日志与密钥都在自己的程序目录下）。
    """
    if key_dir:
        return key_dir
    if fhl_path:
        d = os.path.dirname(os.path.abspath(fhl_path))
        if d:
            return d
    return os.getcwd()
