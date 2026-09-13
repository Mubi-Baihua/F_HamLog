# -*- coding: utf-8 -*-
"""验证「每秒拉取」同步：客户端周期性 FETCH，能拿到其他客户端 SAVE 的最新日志。
（复刻 project._SyncThread 的拉取循环；PySide6 不可用时也能验证服务端行为。）
"""
import socket
import json
import threading
import time
import remote_server as rs


def auth_fetch(s, password, role='guest', ip=''):
    """完成鉴权 + 首次 FETCH，返回 (client_sock, initial_list)。"""
    rs.send_frame(s, 'AUTH', json.dumps({'password': password, 'role': role, 'ip': ip}))
    assert rs.recv_frame(s)[0] == 'LOGIN'
    rs.send_frame(s, 'FETCH', '')
    while True:
        f = rs.recv_frame(s)
        assert f is not None
        if f[0] == 'FILE':
            return s, json.loads(f[1])


def pull_once(s, password, timeout=3.0):
    """发一次 FETCH，循环跳过 PEERS/SYNC 直到拿到 FILE，返回日志列表。"""
    rs.send_frame(s, 'FETCH', '')
    s.settimeout(timeout)
    while True:
        f = rs.recv_frame(s)
        if f is None:
            raise RuntimeError('连接中断')
        if f[0] == 'FILE':
            return json.loads(f[1])


def main():
    srv = rs.LogServer(password='000000', port=0)
    srv.start()
    ip, port = srv.address
    print('server', ip, port)

    # A 客户端：后台线程每秒拉取一次，记录最新看到的日志
    sa = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sa.settimeout(5)
    sa.connect((ip, port))
    _, init = auth_fetch(sa, '000000', role='host', ip='10.0.0.9')
    assert init == [], init
    seen = {'latest': init}
    stop = {'flag': False}

    def puller():
        while not stop['flag']:
            try:
                seen['latest'] = pull_once(sa, '000000')
            except Exception as e:
                print('puller error:', e)
                return
            time.sleep(1.0)  # 与 _SyncThread 一致：每秒一次

    t = threading.Thread(target=puller, daemon=True)
    t.start()

    # B 客户端：连接后 SAVE 一批新日志
    sb = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sb.settimeout(5)
    sb.connect((ip, port))
    auth_fetch(sb, '000000', role='guest')
    rs.send_frame(sb, 'SAVE', json.dumps([{'m_call': 'PULL1'}, {'m_call': 'PULL2'}]))
    # 等服务端 OK
    while True:
        f = rs.recv_frame(sb)
        if f is None:
            break
        if f[0] == 'OK':
            break
    print('B saved 2 records')

    # 等待 A 的拉取循环把最新数据拉到（最多 3 秒）
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if len(seen['latest']) == 2 and seen['latest'][0].get('m_call') == 'PULL1':
            break
        time.sleep(0.1)
    print('A latest after pull =', seen['latest'])
    assert len(seen['latest']) == 2, f'拉取未同步到最新数据: {seen["latest"]}'
    assert seen['latest'][0].get('m_call') == 'PULL1', seen['latest']

    stop['flag'] = True
    sa.close()
    sb.close()
    srv.stop()
    print('PULL_SYNC_SMOKE_OK')


if __name__ == '__main__':
    main()
