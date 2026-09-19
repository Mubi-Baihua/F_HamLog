# -*- coding: utf-8 -*-
"""传输加密的 headless 烟囱测试：握手 / 加密 FETCH / 加密 SAVE / 拒绝路径 / 明文兼容。"""

import os
import sys
import json
import socket
import tempfile

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

import remote_crypto
import remote_server
from remote_server import send_frame, recv_frame

REPORT = []


def say(s):
    REPORT.append(s)
    print(s)
    with open('__enc_out.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(REPORT) + '\n')


PASS = []


def ok(name, cond, detail=''):
    PASS.append(bool(cond))
    say(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f'  -> {detail}' if detail else ''))


def rec(o_call):
    return {'date': '2026-09-14', 'time': '20:00', 'm_call': 'BG1AAA', 'o_call': o_call,
            'freq': '145.000', 'freq_rx': '', 'mode': 'FM', 'prop_mode': '',
            'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
            'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
            'notes': ''}


def new_server(seed=None, password='pw', encrypt=True, tag='srv'):
    tmp = tempfile.mkdtemp()
    fhl = os.path.join(tmp, 'room.fhl')
    keyf = os.path.join(tmp, 'server_test.fhlkey')
    srv = remote_server.LogServer(password=password, port=0, fhl_path=fhl,
                                  encrypt=encrypt, key_path=keyf)
    srv.start(seed_list=seed or [])
    return srv, fhl, keyf


def recv_or_none(sock, timeout=1.5):
    """带超时收一帧；超时或连接关闭都返回 (None, None)。"""
    old = sock.gettimeout()
    sock.settimeout(timeout)
    try:
        r = recv_frame(sock)
        return (None, None) if r is None else r
    except socket.timeout:
        return (None, None)
    finally:
        try:
            sock.settimeout(old)
        except Exception:
            pass


def raw_enc_client(srv, password='pw', role='guest', tamper=False):
    """手动走一遍加密握手，返回 (socket, SessionCipher, 服务端公钥, 首响应)。

    握手成功后服务端会广播一条加密 PEERS，这里一并收掉，避免调用方错位。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(6)
    s.connect(('127.0.0.1', srv.address[1]))
    t, body = recv_frame(s)
    assert t == 'HELLO', f'首帧应为 HELLO，实际 {t}'
    pub, raw_pub, short = remote_crypto.parse_hello(body)
    sk = remote_crypto.new_session_key()
    cli = remote_crypto.generate_server_key()
    ack, _ = remote_crypto.make_hello_ack(raw_pub, cli, sk, password, role, '10.0.0.5')
    if tamper:
        # 破坏密文本身（改一个字节即可让 GCM 完整性校验失败）
        obj = json.loads(ack)
        ct = bytearray(remote_crypto.b64d(obj['ct']))
        ct[-1] ^= 0x01
        obj['ct'] = remote_crypto.b64e(bytes(ct))
        ack = json.dumps(obj, ensure_ascii=False)
    send_frame(s, 'HELLO_ACK', ack)
    t2, b2 = recv_frame(s)
    if tamper:
        s.close()
        return s, None, raw_pub, (t2, b2)
    assert t2 == 'LOGIN', f'握手后应回 LOGIN，实际 {t2}: {b2}'
    cipher = remote_crypto.SessionCipher(sk)
    # 握手后可能还有若干加密广播帧（PEERS）在途：全部收掉并解密，保持读取位置干净
    while True:
        t3, b3 = recv_or_none(s, 0.6)
        if t3 is None:
            break
        remote_server.open_enc_payload(cipher, b3)
    return s, cipher, raw_pub, (t2, b2)


def enc_send(s, cipher, t, payload):
    send_frame(s, t, remote_server.make_enc_payload(cipher, payload))


def enc_recv(s, cipher, skip=()):
    """收一帧并解密；skip 中的帧类型解密后丢弃（如 PEERS 广播）。"""
    while True:
        t, body = recv_or_none(s, 4.0)
        if t is None:
            return (None, None)
        text = remote_server.open_enc_payload(cipher, body)
        if t in skip:
            continue
        return (t, text)


try:
    # ---------- 1. 握手与指纹 ----------
    srv, fhl, keyf = new_server([rec('SEED1')], password='pw')
    fp1 = srv.fingerprint_short
    ok('服务端公钥指纹可用', len(fp1) == 39 and fp1.count('-') == 7, fp1)
    ok('长期密钥已落盘', os.path.exists(keyf))

    s, cipher, raw_pub, _ = raw_enc_client(srv, 'pw')
    ok('握手成功并建立加密会话', cipher is not None)
    ok('客户端拿到的公钥与服务端一致', raw_pub == srv.public_key)
    key_material = remote_crypto.fingerprint_short(raw_pub)
    ok('指纹一致', key_material == fp1, key_material)

    # ---------- 2. 加密 FETCH ----------
    enc_send(s, cipher, 'FETCH', '')
    t, body = enc_recv(s, cipher, skip=('PEERS',))
    ok('FETCH 返回加密 FILE 帧', t == 'FILE', str(t))
    data = json.loads(body)
    ok('FILE 内容正确', len(data) == 1 and data[0]['o_call'] == 'SEED1',
       str([r.get('o_call') for r in data]))

    # ---------- 3. 抓包只能是密文 ----------
    ok('身份验证信息未在密文中以明文出现',
       b'password' not in body.encode('utf-8') and b'pw' != body.encode('utf-8'))

    # ---------- 4. 加密 SAVE 与广播 ----------
    s2, cipher2, _, _ = raw_enc_client(srv, 'pw')
    enc_send(s, cipher, 'SAVE', json.dumps([rec('FROM-A'), rec('FROM-B')],
                                          ensure_ascii=False))
    t, body = enc_recv(s, cipher, skip=('PEERS',))
    ok('SAVE 收到 OK', t == 'OK', str(t))
    t, body = enc_recv(s2, cipher2, skip=('PEERS',))
    ok('其他客户端收到加密 SYNC 广播', t == 'SYNC', str(t))
    ok('SYNC 内容正确', [r['o_call'] for r in json.loads(body)] == ['FROM-A', 'FROM-B'])
    ok('服务端内存已更新', [r['o_call'] for r in srv.file] == ['FROM-A', 'FROM-B'])
    with open(fhl, encoding='utf-8') as f:
        ok('服务端已落盘', [r['o_call'] for r in json.load(f)] == ['FROM-A', 'FROM-B'])

    # ---------- 5. NEXT / PONG 走密文 ----------
    enc_send(s, cipher, 'NEXT', '')
    t, body = enc_recv(s, cipher, skip=('PEERS',))
    ok('NEXT 收到 PONG（密文）', t == 'PONG', str(t))

    s.close()
    s2.close()

    # ---------- 6. 错误密码被拒绝 ----------
    s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s3.settimeout(6)
    s3.connect(('127.0.0.1', srv.address[1]))
    t, body = recv_frame(s3)
    pub, raw_pub, _ = remote_crypto.parse_hello(body)
    sk = remote_crypto.new_session_key()
    cli = remote_crypto.generate_server_key()
    ack, _ = remote_crypto.make_hello_ack(raw_pub, cli, sk, 'WRONG', 'guest', '')
    send_frame(s3, 'HELLO_ACK', ack)
    t, body = recv_frame(s3)
    ok('错误密码被拒绝（DENY）', t == 'DENY', str(t))
    s3.close()

    # ---------- 7. 篡改的握手载荷被拒绝 ----------
    s4, c4, _, resp = raw_enc_client(srv, 'pw', tamper=True)
    ok('篡改的 HELLO_ACK 被拒绝', resp[0] == 'DENY', str(resp[0]))
    s4.close()

    # ---------- 8. 旧客户端明文 AUTH 仍可用（向后兼容） ----------
    s5 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s5.settimeout(6)
    s5.connect(('127.0.0.1', srv.address[1]))
    # 旧客户端第一帧就是 AUTH：服务端先发 HELLO，旧客户端会忽略它
    t, body = recv_frame(s5)
    ok('服务端对未知客户端先发 HELLO', t == 'HELLO', str(t))
    send_frame(s5, 'AUTH', json.dumps({'password': 'pw', 'role': 'guest', 'ip': '1.2.3.4'}))
    t, body = recv_frame(s5)
    ok('旧客户端明文 AUTH 仍可登录', t == 'LOGIN', str(t))
    send_frame(s5, 'FETCH', '')
    t, body = recv_frame(s5)
    while t == 'PEERS':
        t, body = recv_frame(s5)
    ok('旧客户端仍能拿到明文 FILE', t == 'FILE', str(t))
    s5.close()

    # ---------- 9. 加密会话下用明文帧会被断开 ----------
    s6, c6, _, _ = raw_enc_client(srv, 'pw')   # 在途广播已在握手辅助里收掉
    send_frame(s6, 'FETCH', '')                # 未加密的正文
    t, body = recv_or_none(s6, 3.0)
    ok('加密会话收到明文帧即断开', t is None, str(t))
    s6.close()

    # ---------- 10. 服务端重启后指纹保持（同一密钥文件） ----------
    srv.stop()
    srv2 = remote_server.LogServer(password='pw', port=0, fhl_path=fhl, key_path=keyf)
    srv2.start()
    ok('重启后指纹不变（长期身份稳定）', srv2.fingerprint_short == fp1,
       f'{fp1} / {srv2.fingerprint_short}')
    srv2.stop()

    # ---------- 11. 换密钥文件 => 指纹改变 ----------
    tmp2 = tempfile.mkdtemp()
    other_key = os.path.join(tmp2, 'other.fhlkey')
    srv3 = remote_server.LogServer(password='pw', port=0, fhl_path=None, key_path=other_key)
    srv3.start()
    ok('换密钥文件后指纹改变', srv3.fingerprint_short != fp1, srv3.fingerprint_short)
    srv3.stop()

    # ---------- 12. 关闭加密时退化为明文协议 ----------
    srv4, _, _ = new_server([rec('PLAIN')], password='pw', encrypt=False)
    ok('encrypt=False 时无指纹', srv4.fingerprint_short == '')
    s7 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s7.settimeout(6)
    s7.connect(('127.0.0.1', srv4.address[1]))
    send_frame(s7, 'AUTH', json.dumps({'password': 'pw', 'role': 'guest', 'ip': ''}))
    t, body = recv_frame(s7)
    ok('encrypt=False 时明文 AUTH 可用', t == 'LOGIN', str(t))
    send_frame(s7, 'FETCH', '')
    t, body = recv_frame(s7)
    while t == 'PEERS':
        t, body = recv_frame(s7)
    ok('encrypt=False 时明文 FILE 可用', t == 'FILE' and 'PLAIN' in body, str(t))
    s7.close()
    srv4.stop()

finally:
    try:
        srv.stop()
    except Exception:
        pass

say('')
say(f'总计 {len(PASS)} 项，通过 {sum(PASS)} 项，失败 {len(PASS) - sum(PASS)} 项。')
sys.exit(0 if all(PASS) else 1)
