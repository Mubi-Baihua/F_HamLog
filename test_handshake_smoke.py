"""复现「无法连接本地房间：获取日志数据失败」握手竞态。

服务器在 LOGIN 后会立刻下发 PEERS 广播，真实 RemoteConnection.connect()
必须在 FETCH 之后循环读取、跳过 PEERS 直到拿到 FILE。本测试用标准库复刻
该握手逻辑，验证即便 PEERS 夹在 LOGIN 与 FILE 之间也能成功。
"""
import json
import socket
import threading

import remote_server as rs


def connect_handshake(host, port, password):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((host, port))
    rs.send_frame(s, 'AUTH', password)
    r = rs.recv_frame(s)
    assert r and r[0] == 'LOGIN', f'AUTH 失败: {r}'
    rs.send_frame(s, 'FETCH', '')
    # 关键：循环读取，跳过 PEERS / SYNC 等非 FILE 广播帧
    while True:
        r = rs.recv_frame(s)
        if r is None:
            raise RuntimeError('获取日志数据失败。')
        if r[0] == 'FILE':
            break
        # 忽略 PEERS 等广播帧
    data = json.loads(r[1])
    s.close()
    return data


def main():
    srv = rs.LogServer(password='pw', port=0, encrypt=False)
    srv.start()
    ip, port = srv.address
    print(f'server {ip} {port}')
    # 模拟房主本地连接（127.0.0.1）
    local = connect_handshake('127.0.0.1', port, 'pw')
    assert local == [], f'初始日志应空，实际 {local!r}'
    print('[handshake] 房主本地连接拿到空日志 OK')
    # 模拟好友经局域网加入（用实际地址，触发 PEERS 广播含两方）
    friend = connect_handshake(ip, port, 'pw')
    assert friend == [], f'初始日志应空，实际 {friend!r}'
    print('[handshake] 好友加入连接拿到空日志 OK')
    # 房主发一条日志后再让好友 FETCH，验证 FILE 仍被正确解析（不被 PEERS 干扰）
    srv._file = [{'m_call': 'TEST1'}]
    f2 = connect_handshake(ip, port, 'pw')
    assert len(f2) == 1 and f2[0].get('m_call') == 'TEST1', f'应拿到 1 条，实际 {f2!r}'
    print('[handshake] 含数据的 FILE 解析正确 OK')
    srv.stop()
    print('HANDSHAKE_SMOKE_OK')


if __name__ == '__main__':
    main()
