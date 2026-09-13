# -*- coding: utf-8 -*-
"""验证服务端「2 秒空闲即视为退出」的清理逻辑（CLIENT_IDLE_TIMEOUT）。

三种情形：
  1) 客户端连上后不再发任何信息 → 超过 2 秒被服务端清理；
  2) 客户端周期性发心跳（模拟真实客户端每秒 FETCH）→ 持续存活；
  3) 客户端主动发 QUIT → 立即被清理（客户端退出指令）。
"""
import socket
import json
import time
import remote_server as rs


def _hello(ip, port, role='guest', display_ip=''):
    """完成鉴权 + 一次 FETCH，之后不再主动发消息。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((ip, port))
    rs.send_frame(s, 'AUTH', json.dumps(
        {'password': '000000', 'role': role, 'ip': display_ip}, ensure_ascii=False))
    assert rs.recv_frame(s)[0] == 'LOGIN'
    rs.send_frame(s, 'FETCH', '')
    while True:
        f = rs.recv_frame(s)
        assert f is not None, '连接中断'
        if f[0] == 'FILE':
            break
    return s


def main():
    srv = rs.LogServer(password='000000', port=0)
    srv.start()
    ip, port = srv.address
    print('server', ip, port, 'CLIENT_IDLE_TIMEOUT =', rs.CLIENT_IDLE_TIMEOUT)

    # 1) 空闲客户端 → 超时被清理
    idle = _hello(ip, port)
    assert srv.client_count == 1, srv.client_count
    time.sleep(rs.CLIENT_IDLE_TIMEOUT + 0.8)
    assert srv.client_count == 0, f'空闲客户端应被清理，实际在线={srv.client_count}'
    print('idle client cleaned up OK')

    # 2) 有周期性心跳的客户端 → 持续存活
    alive = _hello(ip, port)
    assert srv.client_count == 1, srv.client_count
    beats = int((rs.CLIENT_IDLE_TIMEOUT * 2) / 0.7) + 1
    for _ in range(beats):
        rs.send_frame(alive, 'NEXT', '')
        time.sleep(0.7)
    assert srv.client_count == 1, f'有心跳的客户端不应被清理，实际在线={srv.client_count}'
    print('client with heartbeat stays alive OK')

    # 3) 主动 QUIT → 立即清理
    rs.send_frame(alive, 'QUIT', '')
    time.sleep(0.5)
    assert srv.client_count == 0, f'QUIT 后应立即清理，实际在线={srv.client_count}'
    print('QUIT removes client immediately OK')

    idle.close(); alive.close()
    srv.stop()
    print('IDLE_TIMEOUT_SMOKE_OK')


if __name__ == '__main__':
    main()
