# -*- coding: utf-8 -*-
"""多人日志 —— 传输加密层（服务端与客户端共用，纯 cryptography，无 GUI 依赖）。

设计目标（与 remote_server 的帧协议解耦，只负责密码学）：

    1) 密码只用于身份认证，不参与内容加密；
    2) 每次连接由客户端生成一个随机的对称会话密钥（AES-256-GCM）；
    3) 会话密钥用非对称加密（X25519 ECDH + HKDF）安全地分发给服务端；
    4) 之后的全部协议帧都走该会话密钥加密。

握手时序（服务端在鉴权通过后发起，避免密码错误时泄漏任何密文）：

    S -> C   HELLO\\n<json>        {"pub": <服务端长期公钥 b64>, "fingerprint": "<短码>"}
    C -> S   HELLO_ACK\\n<json>    {"ct": <login_blob b64>, "pub": <客户端临时公钥 b64>,
                                   "nonce": <登录 blob 的 AES-GCM nonce b64>}
    S -> C   ENC_OK\\n<json>       {"enc": <会话密钥确认密文 b64>}（可省略，用于确认链路可用）

其中 login_blob 的明文为 JSON：
    {"password": "...", "role": "host"/"guest", "ip": "<展示地址>", "key": "<会话密钥 b64>"}
即：**密码与对称密钥打包在同一段密文里**，只有持有服务端长期私钥的一方能解开——
中间人既拿不到密码，也拿不到会话密钥。

会话密钥派生：
    共享秘密 = X25519(客户端临时私钥, 服务端长期公钥)
             = X25519(服务端长期私钥, 客户端临时公钥)
    key = HKDF-SHA256(ikm=共享秘密, salt=服务端公钥||客户端公钥, info="fhl-remote-v1")

之所以是「临时密钥 + 长期密钥」的组合，是因为 X25519 双方各出一半：
客户端出临时密钥对（每次连接随机），服务端出长期密钥对（由指纹固定身份）。
这样既做到了每次连接会话密钥不同（前向安全），又能用指纹校验服务端身份。

帧体加密（AES-256-GCM）：
    密文包 = nonce(12) || tag(16) || ciphertext
    每帧独立随机 nonce（96 bit 随机值，碰撞概率可忽略），随包一起发送。
    **不把帧序号绑进 AAD**：服务端会随时向客户端插入 PEERS/SYNC 广播，客户端也可能
    跳过某些帧，一旦绑定序号，任何一次跳过都会让后续所有帧解不开。重放防护改由
    「已用 nonce 滑动窗口」承担：重复出现的 nonce 直接拒绝。
"""

import base64
import collections
import hashlib
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# 密钥派生用的上下文串：换版本时可改，双方必须一致
HKDF_INFO = b'fhl-remote-v1'
NONCE_LENGTH = 12
TAG_LENGTH = 16

# 服务端长期密钥文件的后缀（内容为 base64 的 32 字节原始私钥）
KEY_FILE_SUFFIX = '.fhlkey'


# ---------------------------------------------------------------------------
# 编解码小工具
# ---------------------------------------------------------------------------

def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def b64d(text: str) -> bytes:
    return base64.b64decode(text or '')


# ---------------------------------------------------------------------------
# 服务端长期密钥对：生成 / 持久化 / 指纹
# ---------------------------------------------------------------------------

def generate_server_key() -> X25519PrivateKey:
    """生成一对新的服务端长期密钥。"""
    return X25519PrivateKey.generate()


def private_key_bytes(priv: X25519PrivateKey) -> bytes:
    """导出私钥的 32 字节原始表示（用于落盘）。"""
    return priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())


def public_key_bytes(priv: X25519PrivateKey) -> bytes:
    """导出公钥的 32 字节原始表示（用于握手与指纹）。"""
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


def load_private_key(raw: bytes) -> X25519PrivateKey:
    """从 32 字节原始私钥恢复密钥对象。"""
    return X25519PrivateKey.from_private_bytes(raw)


def load_or_create_server_key(path):
    """加载服务端长期私钥；不存在或损坏则新建并写盘。

    返回 (私钥对象, 是否新建)。文件内容为 base64 的 32 字节私钥，权限按需收紧。
    """
    if path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                raw = b64d(f.read().decode('ascii').strip())
            if len(raw) == 32:
                return load_private_key(raw), False
        except Exception:
            pass
    priv = generate_server_key()
    if path:
        try:
            d = os.path.dirname(path)
            if d and not os.path.exists(d):
                os.makedirs(d)
            with open(path, 'w', encoding='ascii') as f:
                f.write(b64e(private_key_bytes(priv)))
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
        except Exception:
            pass
    return priv, True


def key_file_for_port(port, base_dir=None):
    """按端口生成长期密钥文件路径（同一端口固定身份，换端口即换身份）。

    端口为 0（自动分配）时退化为 default，避免把随机端口写成一堆密钥文件。
    """
    base_dir = base_dir or os.getcwd()
    return os.path.join(base_dir, 'keys',
                        f'server_{int(port) if port else "default"}{KEY_FILE_SUFFIX}')


def fingerprint(raw_pub: bytes) -> str:
    """公钥指纹：SHA-256 前 16 字节的十六进制（32 个字符）。"""
    return hashlib.sha256(raw_pub).hexdigest()[:32]


def fingerprint_short(raw_pub: bytes) -> str:
    """便于人工核对的短码：把 32 个十六进制字符按 4 个一组用短横线分开。

    例：A1B2C3D4-E5F6...（8 组）。仍然只取 SHA-256 前缀，不会被轻易碰撞。
    """
    fp = fingerprint(raw_pub).upper()
    return '-'.join(fp[i:i + 4] for i in range(0, len(fp), 4))


def format_fingerprint_short(text: str) -> str:
    """把（可能是旧格式的）指纹字符串重新按短码排版，便于展示。"""
    clean = ''.join(ch for ch in (text or '') if ch.isalnum()).upper()
    return '-'.join(clean[i:i + 4] for i in range(0, len(clean), 4))


# ---------------------------------------------------------------------------
# 握手载荷
# ---------------------------------------------------------------------------

def make_hello(private_key: X25519PrivateKey) -> str:
    """服务端 HELLO 正文：公开自己的长期公钥与指纹。"""
    raw = public_key_bytes(private_key)
    return json.dumps({'pub': b64e(raw),
                       'fingerprint': fingerprint(raw),
                       'fmt': 'x25519-hkdf-aesgcm-v1'},
                      ensure_ascii=False)


def parse_hello(payload: str):
    """解析服务端 HELLO，返回 (公钥对象, 公钥原始字节, 指纹短码)；不合法抛 ValueError。"""
    try:
        obj = json.loads(payload)
        raw = b64d(obj['pub'])
    except Exception as e:
        raise ValueError(f'HELLO 载荷无法解析：{e}')
    if len(raw) != 32:
        raise ValueError('HELLO 公钥长度不合法。')
    try:
        pub = X25519PublicKey.from_public_bytes(raw)
    except Exception as e:
        raise ValueError(f'HELLO 公钥不合法：{e}')
    return pub, raw, fingerprint_short(raw)


def make_hello_ack(server_pub_raw: bytes, client_priv: X25519PrivateKey,
                   session_key: bytes, password: str, role: str,
                   display_ip: str, aad: bytes = b''):
    """客户端 HELLO_ACK 正文：把登录信息+会话密钥用密钥交换出来的密钥加密。

    返回 (payload_json, aes_key)。
      aes_key 用 HKDF 从 ECDH 共享秘密派生，仅用于加密这一段 login_blob；
      真正的内容加密用 session_key（随 login_blob 一起交给服务端）。
    """
    client_pub_raw = public_key_bytes(client_priv)
    server_pub = X25519PublicKey.from_public_bytes(server_pub_raw)
    shared = client_priv.exchange(server_pub)
    aes_key = derive_key(shared, server_pub_raw, client_pub_raw)

    blob = json.dumps({'password': password, 'role': role, 'ip': display_ip,
                       'key': b64e(session_key)}, ensure_ascii=False)
    ct = encrypt_with_key(aes_key, blob, aad=aad)
    return json.dumps({'ct': b64e(ct), 'pub': b64e(client_pub_raw)},
                      ensure_ascii=False), aes_key


def parse_hello_ack(server_priv: X25519PrivateKey, payload: str):
    """服务端解析 HELLO_ACK，返回 (登录信息 dict, 会话密钥 bytes)；失败抛 ValueError。"""
    try:
        obj = json.loads(payload)
        ct = b64d(obj['ct'])
        client_pub_raw = b64d(obj['pub'])
    except Exception as e:
        raise ValueError(f'HELLO_ACK 载荷无法解析：{e}')
    if len(client_pub_raw) != 32:
        raise ValueError('客户端公钥长度不合法。')
    try:
        client_pub = X25519PublicKey.from_public_bytes(client_pub_raw)
    except Exception as e:
        raise ValueError(f'客户端公钥不合法：{e}')

    server_pub_raw = public_key_bytes(server_priv)
    shared = server_priv.exchange(client_pub)
    aes_key = derive_key(shared, server_pub_raw, client_pub_raw)
    try:
        blob = decrypt_with_key(aes_key, ct)
    except Exception as e:
        raise ValueError(f'登录信息解密失败：{e}')
    try:
        info = json.loads(blob)
    except Exception as e:
        raise ValueError(f'登录信息格式不合法：{e}')
    if not isinstance(info, dict):
        raise ValueError('登录信息格式不合法。')
    try:
        session_key = b64d(info['key'])
    except Exception as e:
        raise ValueError(f'会话密钥不合法：{e}')
    if len(session_key) != 32:
        raise ValueError('会话密钥长度不合法。')
    return info, session_key


# ---------------------------------------------------------------------------
# 密钥派生与对称加解密
# ---------------------------------------------------------------------------

def derive_key(shared_secret: bytes, server_pub: bytes, client_pub: bytes) -> bytes:
    """HKDF-SHA256 派生 32 字节 AES-256 密钥。

    salt 绑定双方公钥，避免不同连接之间出现相同的派生结果。
    """
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=server_pub + client_pub,
                info=HKDF_INFO).derive(shared_secret)


def new_session_key() -> bytes:
    """程序自主生成一个随机的对称会话密钥（AES-256）。"""
    return os.urandom(32)


def new_nonce() -> bytes:
    """随机 12 字节 GCM nonce。"""
    return os.urandom(NONCE_LENGTH)


def seal(key: bytes, plain_text: str, nonce: bytes = None, aad: bytes = b'') -> bytes:
    """加密：返回 nonce || tag || ciphertext 的字节包（自带 nonce，随包发送）。"""
    nonce = nonce or new_nonce()
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
    enc = cipher.encryptor()
    if aad:
        enc.authenticate_additional_data(aad)
    ct = enc.update(plain_text.encode('utf-8')) + enc.finalize()
    return nonce + enc.tag + ct


def unseal(key: bytes, package: bytes, aad: bytes = b'') -> str:
    """解密：package 为 nonce || tag || ciphertext；失败抛 ValueError。"""
    if len(package) < NONCE_LENGTH + TAG_LENGTH:
        raise ValueError('密文包长度不合法。')
    nonce = package[:NONCE_LENGTH]
    tag = package[NONCE_LENGTH:NONCE_LENGTH + TAG_LENGTH]
    ct = package[NONCE_LENGTH + TAG_LENGTH:]
    try:
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
        dec = cipher.decryptor()
        if aad:
            dec.authenticate_additional_data(aad)
        raw = dec.update(ct) + dec.finalize()
    except Exception as e:
        raise ValueError(f'解密失败（密钥不匹配或数据被篡改）：{e}')
    return raw.decode('utf-8')


def encrypt_with_key(key: bytes, plain_text: str, aad: bytes = b'') -> bytes:
    """见 seal（保留语义化别名，便于握手代码可读）。"""
    return seal(key, plain_text, aad=aad)


def decrypt_with_key(key: bytes, package: bytes, aad: bytes = b'') -> str:
    """见 unseal。"""
    return unseal(key, package, aad=aad)


# ---------------------------------------------------------------------------
# 会话加解密器（带重放保护）
# ---------------------------------------------------------------------------

class SessionCipher:
    """一次连接上的会话加解密器。

    每帧使用独立随机 nonce（随密文一起发送），因此**不依赖收发顺序对齐**——
    这对本项目是必须的：服务端会在任意时刻向任意客户端插入 PEERS/SYNC 广播，
    而客户端在握手/拉取过程中可能跳过某些广播帧，若把 nonce 或 AAD 绑定到
    单调计数器，任何一次跳过都会让后续帧全部解不开。

    重放防护改用「最近收到过的 nonce 集合」：GCM 本身保证完整性，重复出现的
    nonce 直接拒绝即可（内存有上限，超出后淘汰最旧的记录）。
    """

    #: 最多记住多少个已用 nonce（窗口大小）
    NONCE_MEMORY = 4096

    def __init__(self, key: bytes):
        self.key = key
        self._send_count = 0
        self._recv_count = 0
        self._seen_nonces = set()
        self._nonce_order = collections.deque()

    @property
    def send_count(self):
        return self._send_count

    @property
    def recv_count(self):
        return self._recv_count

    def encrypt(self, plain_text: str) -> bytes:
        nonce = new_nonce()
        package = seal(self.key, plain_text, nonce=nonce)
        self._send_count += 1
        return package

    def decrypt(self, package: bytes) -> str:
        """解密一帧。密文被篡改或为重复的旧帧时抛 ValueError。"""
        if len(package) < NONCE_LENGTH + TAG_LENGTH:
            raise ValueError('帧长度不合法。')
        nonce = package[:NONCE_LENGTH]
        if nonce in self._seen_nonces:
            raise ValueError('检测到重放的帧，已丢弃。')
        text = unseal(self.key, package)
        self._seen_nonces.add(nonce)
        self._nonce_order.append(nonce)
        while len(self._nonce_order) > self.NONCE_MEMORY:
            old = self._nonce_order.popleft()
            self._seen_nonces.discard(old)
        self._recv_count += 1
        return text


# ---------------------------------------------------------------------------
# 已知服务端公钥记录（首次核对后记住，下次自动校验；变了要告警）
# ---------------------------------------------------------------------------

KNOWN_KEYS_FILE = 'known_server_keys.txt'


def known_keys_path(file_path=None):
    """已知服务端公钥记录文件的路径（默认放在 file/ 下）。"""
    if file_path:
        return file_path
    return os.path.join('file', KNOWN_KEYS_FILE)


def load_known_keys(file_path=None):
    """读取已记住的服务端公钥。

    返回 {<主机:端口>: {"pub": <b64>, "fp": <指纹短码>}}；文件不存在/损坏返回 {}。
    """
    path = known_keys_path(file_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_known_keys(mapping, file_path=None):
    """写回已知服务端公钥记录（尽力而为，失败不抛）。"""
    path = known_keys_path(file_path)
    try:
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)
        return True
    except Exception:
        return False


def check_known_key(host, port, raw_pub, file_path=None):
    """核对服务端公钥。

    返回 (状态, 记录内容)，状态取值：
      'new'     该地址首次连接（无记录）；
      'match'   已有记录且公钥一致；
      'mismatch'已有记录但公钥变了（可能是换了服务端，也可能遭中间人替换）。
    """
    mapping = load_known_keys(file_path)
    key = f'{host}:{port}'
    entry = mapping.get(key) if isinstance(mapping, dict) else None
    if not entry:
        return 'new', None
    old_pub = str(entry.get('pub', '')) if isinstance(entry, dict) else str(entry)
    if old_pub == b64e(raw_pub):
        return 'match', entry
    return 'mismatch', entry


def remember_key(host, port, raw_pub, file_path=None):
    """记住（或更新）某个地址的服务端公钥。"""
    mapping = load_known_keys(file_path)
    if not isinstance(mapping, dict):
        mapping = {}
    mapping[f'{host}:{port}'] = {'pub': b64e(raw_pub),
                                 'fp': fingerprint_short(raw_pub)}
    return save_known_keys(mapping, file_path)


def forget_key(host, port, file_path=None):
    """删除某个地址的服务端公钥记录（用户确认服务端确实换过密钥时）。"""
    mapping = load_known_keys(file_path)
    if isinstance(mapping, dict) and f'{host}:{port}' in mapping:
        del mapping[f'{host}:{port}']
        return save_known_keys(mapping, file_path)
    return False

if __name__ == '__main__':
    srv = generate_server_key()
    raw_pub = public_key_bytes(srv)
    print('服务端指纹：', fingerprint_short(raw_pub))

    pub, parsed_raw, short = parse_hello(make_hello(srv))
    assert parsed_raw == raw_pub and short == fingerprint_short(raw_pub)
    print('HELLO 往返一致。')

    cli = generate_server_key()          # 客户端临时密钥对（同类型）
    sk = new_session_key()
    ack, aes_key = make_hello_ack(raw_pub, cli, sk, 'pw123', 'guest', '192.168.1.9')
    info, got_key = parse_hello_ack(srv, ack)
    assert info['password'] == 'pw123' and info['role'] == 'guest'
    assert info['ip'] == '192.168.1.9' and got_key == sk
    print('HELLO_ACK 往返一致，会话密钥分发成功。')

    a = SessionCipher(sk)
    b = SessionCipher(sk)
    for msg in ('hello', json.dumps({'o_call': 'BG5AAA'}, ensure_ascii=False), ''):
        pkg = a.encrypt(msg)
        assert b.decrypt(pkg) == msg
    print('会话帧加解密往返一致（含空正文/中文）。')

    # 乱序投递也能解：不依赖收发顺序对齐
    p1, p2, p3 = a.encrypt('m1'), a.encrypt('m2'), a.encrypt('m3')
    assert b.decrypt(p3) == 'm3' and b.decrypt(p1) == 'm1' and b.decrypt(p2) == 'm2'
    print('乱序帧可正常解密（广播插入/跳过帧不会打断会话）。')

    # 重放：同一帧再解一次必须失败
    pkg = a.encrypt('x')
    b.decrypt(pkg)
    try:
        b.decrypt(pkg)
        raise AssertionError('重放未被拦截')
    except ValueError:
        print('重放帧已被拦截。')

    # 错误的密钥不应能解密
    try:
        SessionCipher(new_session_key()).decrypt(a.encrypt('y'))
        raise AssertionError('错误密钥竟然解开了')
    except ValueError:
        print('错误密钥解密被拒绝。')

    # 篡改密文应被 GCM 完整性校验拦下
    pkg = bytearray(a.encrypt('z'))
    pkg[-1] ^= 0x01
    try:
        b.decrypt(bytes(pkg))
        raise AssertionError('篡改未被发现')
    except ValueError:
        print('篡改数据已被完整性校验拦下。')

    print('remote_crypto 自测全部通过。')
