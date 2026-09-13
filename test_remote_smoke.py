# -*- coding: utf-8 -*-
"""多人日志 服务端/客户端 帧协议与协同的 headless 烟囱测试（不依赖 GUI 窗口）。

环境无 PySide6 时，仍完整验证服务端引擎（监听/鉴权/广播/落盘），并用原始 socket
完整模拟客户端收发（与 project.RemoteConnection 共用同一套帧协议）。若环境装有
PySide6，则额外真正跑一遍 project.RemoteConnection（connect/send_save/再拉取）。
注意：服务端有 2 秒空闲超时，只等待广播的客户端需自行周期发心跳（见 _hb_loop）。
"""
import os
import sys
import socket
import json
import tempfile
import threading
import time

import remote_server
from remote_server import send_frame, recv_frame


def raw_client(host, port, password):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((host, port))
    send_frame(s, 'AUTH', password)
    r = recv_frame(s)
    assert r and r[0] == 'LOGIN', f'AUTH 失败: {r}'
    # 登录后服务端可能立即广播 PEERS，全部丢弃，保持后续交互干净
    while True:
        s.settimeout(0.5)
        try:
            f = recv_frame(s)
        except socket.timeout:
            break
        if f is None or f[0] != 'PEERS':
            break
    return s


def test_engine_and_broadcast():
    tmp = tempfile.mkdtemp()
    fhl = os.path.join(tmp, 'room.fhl')
    srv = remote_server.LogServer(password='pw', port=0, fhl_path=fhl)
    srv.start()
    ip, port = srv.address
    assert port != 0, '端口未分配'
    print(f'[engine] 服务器启动于 {ip}:{port}')

    c1 = raw_client('127.0.0.1', port, 'pw')
    c2 = raw_client('127.0.0.1', port, 'pw')

    send_frame(c1, 'FETCH', '')
    r = None
    while True:
        f = recv_frame(c1)
        assert f is not None, 'FETCH 无响应'
        if f[0] == 'FILE':
            r = f
            break
        # 忽略服务器在 LOGIN 后推送的 PEERS 广播
    assert r and r[0] == 'FILE', f'FETCH 失败: {r}'
    assert json.loads(r[1]) == [], f'初始日志应空: {r[1]}'
    print('[engine] c1 FETCH 得到空日志 OK')

    # c1 在本测试中只等待广播，必须周期性发心跳，否则会被服务端按 2s 空闲超时清理
    stop_hb = threading.Event()
    def _hb_loop(sock):
        while not stop_hb.is_set():
            try:
                send_frame(sock, 'NEXT', '')
            except Exception:
                return
            stop_hb.wait(0.7)
    threading.Thread(target=_hb_loop, args=(c1,), daemon=True).start()

    recved = {}
    def reader():
        c1.settimeout(3)
        while True:
            try:
                fr = recv_frame(c1)
            except socket.timeout:
                break
            if fr is None:
                break
            if fr[0] == 'PEERS':
                continue  # 忽略在线设备广播，只关心 SYNC
            if fr[0] == 'SYNC':
                recved['type'] = fr[0]
                recved['body'] = fr[1]
                break
    t = threading.Thread(target=reader, daemon=True); t.start()

    data = [{'date': '2026-01-01', 'time': '12:00', 'm_call': 'BI8SQL', 'o_call': 'TEST'}]
    send_frame(c2, 'SAVE', json.dumps(data, ensure_ascii=False))
    assert recv_frame(c2)[0] == 'OK', 'c2 未收到 OK'
    print('[engine] c2 SAVE 收到 OK OK')

    t.join(timeout=3)
    assert recved.get('type') == 'SYNC', f'c1 未收到广播 SYNC: {recved}'
    assert json.loads(recved['body']) == data, '广播内容不一致'
    print('[engine] c1 收到广播 SYNC 内容一致 OK')

    time.sleep(0.3)
    with open(fhl, 'r', encoding='utf-8') as f:
        assert json.load(f) == data, '落盘内容不一致'
    print('[engine] 落盘内容一致 OK')

    sb = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sb.settimeout(5); sb.connect(('127.0.0.1', port))
    send_frame(sb, 'AUTH', 'wrong')
    assert recv_frame(sb)[0] == 'DENY', '错误密码未 DENY'
    print('[engine] 错误密码 DENY OK')

    stop_hb.set()
    c1.close(); c2.close(); sb.close()
    srv.stop()
    print('[engine] 全部通过')


def test_project_remote_connection():
    """仅在装有 PySide6 的环境运行（真正使用 project.RemoteConnection）。"""
    try:
        from project import RemoteConnection
    except Exception as e:
        print(f'[client] 跳过（无 PySide6）：{e}')
        return
    tmp = tempfile.mkdtemp()
    fhl = os.path.join(tmp, 'room2.fhl')
    srv = remote_server.LogServer(password='abc', port=0, fhl_path=fhl)
    srv.start()
    ip, port = srv.address

    conn = RemoteConnection('127.0.0.1', port, 'abc')
    conn.connect()
    assert conn.initial_file == [], '初始应为空'
    print('[client] connect + 初始空列表 OK')

    rec = {'date': '2026-02-02', 'time': '08:30', 'm_call': 'AA1AA', 'o_call': 'BB2BB'}
    conn.send_save([rec])
    time.sleep(0.2)

    conn2 = RemoteConnection('127.0.0.1', port, 'abc')
    conn2.connect()
    # 注意：connect() 会对拉取到的记录做 _upgrade_file_records 补默认字段
    # （freq_rx / prop_mode / sat_name），因此不能与原始 rec 直接整体相等比较，
    # 这里逐字段核对原始键值，并确认默认字段已被补齐。
    assert len(conn2.initial_file) == 1, f'第二个连接拉取条数不对: {conn2.initial_file}'
    got = conn2.initial_file[0]
    for k, v in rec.items():
        assert got.get(k) == v, f'第二个连接拉取不一致: {k}={got.get(k)!r} != {v!r}'
    for k in ('freq_rx', 'prop_mode', 'sat_name'):
        assert k in got, f'拉取后未补齐默认字段 {k}: {got}'
    print('[client] send_save + 第二个连接 FETCH 一致 OK')

    conn.close(); conn2.close(); srv.stop()
    print('[client] 全部通过')


if __name__ == '__main__':
    test_engine_and_broadcast()
    test_project_remote_connection()
    print('\nALL_SMOKE_TESTS_PASSED')
