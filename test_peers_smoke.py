# -*- coding: utf-8 -*-
"""验证服务端 PEERS 广播（新版协议）：
  - AUTH 使用 JSON {"password","role","ip"}，兼容旧版明文密码
  - PEERS 为 [{"ip":..., "host":bool}, ...]；服务端本机（role=host）单独标记
  - 服务端 2 秒空闲超时：客户端需周期性发消息（真实客户端每秒 FETCH），
    本测试用 NEXT 心跳保活，模拟真实客户端行为。
"""
import socket
import json
import time
import remote_server as rs

HEARTBEAT_INTERVAL = 0.7   # 小于服务端 CLIENT_IDLE_TIMEOUT(2s)


def connect(host, port, pw='000000', role='guest', display_ip=''):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((host, port))
    rs.send_frame(s, 'AUTH', json.dumps(
        {'password': pw, 'role': role, 'ip': display_ip}, ensure_ascii=False))
    assert rs.recv_frame(s)[0] == 'LOGIN'
    rs.send_frame(s, 'FETCH', '')
    # 服务器在 LOGIN 后立即广播 PEERS，可能先于 FILE 到达，需忽略并捕获
    last_peers = None
    while True:
        f = rs.recv_frame(s)
        assert f is not None, '连接中断'
        if f[0] == 'FILE':
            break
        if f[0] == 'PEERS':
            last_peers = json.loads(f[1])
    return s, last_peers


def wait_peers(socks, timeout=2.5, hb=HEARTBEAT_INTERVAL):
    """在 timeout 内给所有 socks 周期发 NEXT 保活（模拟真实客户端心跳），
    读取各 sock 收到的帧，返回 {id(sock): 最后一次 PEERS}。"""
    end = time.time() + timeout
    last = {id(s): None for s in socks}
    next_hb = 0.0
    while time.time() < end:
        if time.time() >= next_hb:
            for s in socks:
                try:
                    rs.send_frame(s, 'NEXT', '')
                except Exception:
                    pass
            next_hb = time.time() + hb
        for s in socks:
            s.settimeout(0.15)
            try:
                f = rs.recv_frame(s)
            except socket.timeout:
                continue
            except Exception:
                continue
            if f is None:
                continue
            if f[0] == 'PEERS':
                last[id(s)] = json.loads(f[1])
    return last


def host_of(peers):
    return [p for p in (peers or []) if p.get('host')]


def main():
    srv = rs.LogServer(password='000000', port=0, encrypt=False)
    srv.start()
    ip, port = srv.address
    print('server', ip, port)

    # A 作为服务端本机连接，并上报展示用局域网 IP
    a, pa = connect(ip, port, role='host', display_ip='10.0.0.9')
    print('after server-side A connects, peers =', pa)
    assert isinstance(pa, list) and len(pa) == 1, pa
    assert host_of(pa) and host_of(pa)[0]['ip'] == '10.0.0.9', pa
    assert pa[0]['host'] is True, pa

    # B 作为普通客户端连接
    b, pb = connect(ip, port, role='guest')
    print('after client B connects, B sees peers =', pb)
    assert pb is not None and len(pb) == 2, pb
    assert len(host_of(pb)) == 1, pb  # 恰好一个服务端标记

    # A 应收到更新后的 PEERS（服务端 + 客户端）
    wp = wait_peers([a, b], timeout=2.0)
    pa2 = wp[id(a)]
    print('after B connects, A sees peers =', pa2)
    assert pa2 is not None and len(pa2) == 2, pa2
    assert len(host_of(pa2)) == 1, pa2

    # 客户端 B 看到服务端被单独标记且 IP 为上报的展示地址
    assert host_of(pb)[0]['ip'] == '10.0.0.9', pb

    # 断开 B，A 应再次收到只剩自己的 PEERS
    b.close()
    wp2 = wait_peers([a], timeout=2.0)
    pa3 = wp2[id(a)]
    print('after B disconnects, A sees peers =', pa3)
    assert pa3 is not None and len(pa3) == 1, pa3

    a.close()
    srv.stop()

    # 兼容性：旧版明文密码 AUTH 仍可登录（role 视作 guest）
    srv2 = rs.LogServer(password='pw2', port=0, encrypt=False)
    srv2.start()
    ip2, port2 = srv2.address
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s2.settimeout(5)
    s2.connect((ip2, port2))
    rs.send_frame(s2, 'AUTH', 'pw2')  # 旧版明文
    assert rs.recv_frame(s2)[0] == 'LOGIN', '旧版明文密码应仍可登录'
    s2.close()
    srv2.stop()
    print('legacy plain-password AUTH OK')

    print('PEERS_SMOKE_OK')


if __name__ == '__main__':
    main()
