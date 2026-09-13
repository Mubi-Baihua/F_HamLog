# -*- coding: utf-8 -*-
"""心跳保活烟囱测试：

模拟「客户端正在慢慢读取大日志，来不及每秒发 FETCH」的情形——只靠独立心跳
（每秒 NEXT）维持在线。旧实现按 socket 超时判定，2 秒内没收到 FETCH 就会把客户端
踢掉，客户端随之中止同步；新实现只要连接上持续有数据就不算空闲。
"""
import os, sys, socket, json, time, select, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from remote_server import LogServer, send_frame, recv_frame

PASS = []
LINES = []


def say(s):
    LINES.append(s)
    print(s)
    try:
        with open('__hb_out.txt', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(LINES) + '\n')
    except Exception:
        pass


def check(name, cond):
    PASS.append(bool(cond))
    say(('  PASS  ' if cond else '  FAIL  ') + name)


def drain(sock, seconds=0.3):
    """把当前可读的数据全部读掉，返回读到的帧类型列表。"""
    types = []
    end = time.monotonic() + seconds
    while True:
        remain = end - time.monotonic()
        if remain <= 0:
            break
        try:
            r, _, _ = select.select([sock], [], [], remain)
        except (OSError, ValueError):
            break
        if not r:
            break
        try:
            f = recv_frame(sock)
        except (socket.timeout, OSError):
            break
        if f is None:
            break
        types.append(f[0])
    return types


def rec(i):
    return {'date': '2026-01-01', 'time': '00:%02d' % i, 'm_call': 'BG1', 'o_call': 'BG%d' % i,
            'freq': '145', 'freq_rx': '', 'mode': 'FM', 'prop_mode': '', 'sat_name': '',
            'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '', 'm_dig': '', 'o_dig': '',
            'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '', 'notes': '', 'record': 'H' * 300000}


def body():
    srv = LogServer(password='', port=0, fhl_path=None)
    srv.start(seed_list=[rec(i) for i in range(5)])
    ip, port = srv.address
    say('服务端载荷约 %.1f MB' % (len(json.dumps(srv.file)) / 1e6))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((ip, port))
    send_frame(sock, 'AUTH', json.dumps({'password': '', 'role': 'guest', 'ip': ''}))
    f = recv_frame(sock)
    check('鉴权通过收到 LOGIN', f is not None and f[0] == 'LOGIN')
    check('服务端在线数=1', srv.client_count == 1)
    drain(sock, 1.0)   # 吃掉 LOGIN 后立即广播的 PEERS

    send_frame(sock, 'FETCH', '')
    got = drain(sock, 0.8)
    check('FETCH 能拿到 PEERS + FILE', 'FILE' in got)

    # 关键：接下来只发心跳、不发 FETCH（模拟客户端在读大日志），应保持在线。
    # 心跳间隔 ~1.2 秒，始终落在服务端 2 秒空闲阈值之内。
    alive_ok = True
    pong = 0
    for _ in range(8):
        time.sleep(1.0)
        send_frame(sock, 'NEXT', '')
        ts = drain(sock, 0.2)
        pong += ts.count('PONG')
        if srv.client_count != 1:
            alive_ok = False
            break
    check('只发心跳、不发 FETCH 仍保持在线（旧实现会被踢）', alive_ok)
    check('心跳都能收到 PONG', pong >= 6)

    send_frame(sock, 'FETCH', '')
    got2 = drain(sock, 1.2)
    check('保活后仍能正常拉取日志', 'FILE' in got2)

    sock.close()
    time.sleep(0.4)
    check('断开后服务端在线数归零', srv.client_count == 0)
    srv.stop()


try:
    body()
except Exception:
    say('EXCEPTION:\n' + traceback.format_exc())
    sys.exit(2)

say('\n=== HEARTBEAT_KEEPALIVE_SMOKE_OK ===' if all(PASS) else '\n=== SOME FAILED ===')
sys.exit(0 if all(PASS) else 1)
