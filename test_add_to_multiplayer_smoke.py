# -*- coding: utf-8 -*-
"""验证「批量记录 → 添加到多人日志」流程：
  连接房间 → 拉取现有日志 → 追加本次记录 → 整体保存 → 服务端确认 OK。
（复刻 batch_project.add_to_multiplayer 的连接/保存步骤；无需 PySide6。）
"""
import socket
import json
import os
import tempfile
import remote_server as rs


def connect_and_append(host, port, password, new_records):
    """完全复刻 batch_project.add_to_multiplayer 的网络步骤。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((host, port))
    rs.send_frame(s, 'AUTH', json.dumps(
        {'password': password, 'role': 'guest', 'ip': ''}, ensure_ascii=False))
    assert rs.recv_frame(s)[0] == 'LOGIN'
    # FETCH：跳过 PEERS 广播直到 FILE
    rs.send_frame(s, 'FETCH', '')
    initial = None
    while True:
        f = rs.recv_frame(s)
        assert f is not None
        if f[0] == 'FILE':
            initial = json.loads(f[1])
            break
    merged = list(initial) + list(new_records)
    rs.send_frame(s, 'SAVE', json.dumps(merged, ensure_ascii=False))
    # 等 OK
    got_ok = False
    while True:
        f = rs.recv_frame(s)
        if f is None:
            break
        if f[0] == 'OK':
            got_ok = True
            break
    rs.send_frame(s, 'QUIT', '')
    s.close()
    return initial, merged, got_ok


def main():
    tmp = tempfile.mkdtemp(prefix='fhl_multi_')
    fhl = os.path.join(tmp, 'room.fhl')

    # 房间已有 1 条记录
    srv = rs.LogServer(password='pw', port=0, fhl_path=fhl)
    srv.start(seed_list=[{'m_call': 'EXIST'}])
    ip, port = srv.address
    print('server', ip, port)

    initial, merged, got_ok = connect_and_append(ip, port, 'pw',
                                                 [{'m_call': 'NEW1'}, {'m_call': 'NEW2'}])
    print('initial =', initial)
    print('merged  =', merged, 'OK =', got_ok)
    assert initial == [{'m_call': 'EXIST'}], initial
    assert got_ok, '未收到服务端 OK'
    assert len(merged) == 3 and merged[0]['m_call'] == 'EXIST', merged

    # 服务端内存应已更新
    assert len(srv.file) == 3 and srv.file[0]['m_call'] == 'EXIST', srv.file
    # 应已落盘
    with open(fhl, 'r', encoding='utf-8') as f:
        on_disk = json.load(f)
    assert len(on_disk) == 3 and on_disk[2]['m_call'] == 'NEW2', on_disk
    print('server memory + disk updated OK')

    srv.stop()
    try:
        os.remove(fhl)
        os.rmdir(tmp)
    except Exception:
        pass
    print('ADD_TO_MULTIPLAYER_SMOKE_OK')


if __name__ == '__main__':
    main()
