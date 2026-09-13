# -*- coding: utf-8 -*-
"""回归测试：新加入的客户端也能立即看到在线客户端列表。

复现历史 bug：A、B 已在多人日志内且不再有上下线事件时，新加入的 C 在握手期
（LOGIN 后紧跟着的 PEERS 广播）会读到并丢弃 PEERS，之后没有任何 PEERS 再到，
导致 C 的在线客户端列表一直为空。

修复后：服务端在每次 FETCH 的响应里（FILE 之前）单独回一份 PEERS，
因此 C 的下一次拉取即可拿到完整列表。
注：服务端有 2 秒空闲超时，故 A、B 用心跳保活（模拟真实客户端每秒 FETCH）。
"""
import socket
import json
import time
import threading
import remote_server as rs


def _start_heartbeat(sock):
    """周期性发 NEXT 保活，避免被服务端 2 秒空闲超时清理。返回停止事件。"""
    stop = threading.Event()

    def _loop():
        while not stop.is_set():
            try:
                rs.send_frame(sock, 'NEXT', '')
            except Exception:
                return
            stop.wait(0.7)

    threading.Thread(target=_loop, daemon=True).start()
    return stop


def full_handshake(host, port, pw='000000', role='guest', display_ip=''):
    """完整模拟真实客户端 connect()：读 LOGIN，发 FETCH，循环读直到 FILE。

    返回 (sock, peers)：
      - peers：握手期间捕获到的 PEERS（可能为 None）
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((host, port))
    rs.send_frame(s, 'AUTH', json.dumps(
        {'password': pw, 'role': role, 'ip': display_ip}, ensure_ascii=False))
    assert rs.recv_frame(s)[0] == 'LOGIN'
    rs.send_frame(s, 'FETCH', '')
    peers = None
    while True:
        f = rs.recv_frame(s)
        assert f is not None, '连接中断'
        if f[0] == 'FILE':
            break
        if f[0] == 'PEERS':
            peers = json.loads(f[1])
    return s, peers


def pull_peers(s):
    """模拟同步线程每秒一次的拉取：FETCH 后读到 PEERS（FILE 之前）即返回。"""
    rs.send_frame(s, 'FETCH', '')
    peers = None
    while True:
        f = rs.recv_frame(s)
        assert f is not None, '连接中断'
        if f[0] == 'PEERS':
            peers = json.loads(f[1])
        elif f[0] == 'FILE':
            break
    return peers


def main():
    srv = rs.LogServer(password='000000', port=0)
    srv.start()
    ip, port = srv.address
    print('server', ip, port)

    # A 服务端本机 + B 客户端先进入多人日志
    a, _ = full_handshake(ip, port, role='host', display_ip='10.0.0.1')
    b, pb = full_handshake(ip, port, role='guest', display_ip='10.0.0.2')
    assert pb is not None and len(pb) == 2, pb
    # A、B 需保活（否则会被 2 秒空闲超时清理，导致 C 看不到它们）
    stop_a = _start_heartbeat(a)
    stop_b = _start_heartbeat(b)

    # 新客户端 C 加入：握手期就会读到一次 PEERS（若非 None 则说明握手期已可见）
    c, pc_hand = full_handshake(ip, port, role='guest', display_ip='10.0.0.3')
    print('C handshake peers =', pc_hand)
    assert pc_hand is not None and len(pc_hand) == 3, \
        f'新客户端握手期应看到 3 台设备：{pc_hand}'

    # 关键：即使握手期的 PEERS 被丢弃，C 的下一次 FETCH 仍应拿到完整列表
    pc_pull = pull_peers(c)
    print('C next-pull peers =', pc_pull)
    assert pc_pull is not None and len(pc_pull) == 3, \
        f'新客户端拉取应看到 3 台设备：{pc_pull}'
    host_ips = [p['ip'] for p in pc_pull if p.get('host')]
    assert host_ips == ['10.0.0.1'], f'服务端标记异常：{pc_pull}'
    ips = sorted(p['ip'] for p in pc_pull)
    assert ips == ['10.0.0.1', '10.0.0.2', '10.0.0.3'], ips

    stop_a.set(); stop_b.set()
    for s in (a, b, c):
        s.close()
    srv.stop()
    print('NEW_CLIENT_PEERS_SMOKE_OK')


if __name__ == '__main__':
    main()
