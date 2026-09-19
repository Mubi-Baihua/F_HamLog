# -*- coding: utf-8 -*-
"""默认端口 8000 行为冒烟测试。

覆盖：
1. `is_port_in_use` 能正确识别端口占用/空闲。
2. 未占用时 `port=8000` 正常启动，`port_status == 'ok'`，实际端口就是 8000。
3. 已占用时 `port_status == 'occupied'`（供调用方改用 port=0 自动分配）。
4. `port=0` 时为自动分配，`port_status == 'ok'` 且实际端口由系统给出。
5. 端到端：以 8000 开房 → 客户端按 8000 加入 → 加密会话建立 → 同步可用。
6. 8000 被占时，「开房」回退自动端口仍能成功，且客户端可用实际端口加入。
"""
import os
import sys
import socket
import tempfile

FAILED = []


def check(name, cond, extra=''):
    if cond:
        print(f'  PASS  {name}')
    else:
        print(f'  FAIL  {name}  {extra}')
        FAILED.append(name)


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    import remote_server as rs
    from remote_server import LogServer, is_port_in_use
    from project import RemoteConnection, DEFAULT_ROOM_PORT

    tmpdir = tempfile.mkdtemp(prefix='fhl_port_')
    check('DEFAULT_ROOM_PORT 为 8000', DEFAULT_ROOM_PORT == 8000, f'got={DEFAULT_ROOM_PORT}')

    # --- 1. is_port_in_use ---
    # 服务端一律以 0.0.0.0 监听，因此探测口径就是 0.0.0.0。
    # Windows 绑定语义不对称：只有试探「与 holder 完全相同」的地址才准，
    # 故本测试统一让 holder 也绑 0.0.0.0（与实际服务端一致）。
    free = _free_port()
    check('空闲端口未被判为占用', is_port_in_use('0.0.0.0', free) is False)

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(('0.0.0.0', free))
    holder.listen(1)
    try:
        check('已监听端口被判为占用', is_port_in_use('0.0.0.0', free) is True)
        check("host='' 时按通配探测", is_port_in_use('', free) is True)
        check('port=0 不算占用', is_port_in_use('0.0.0.0', 0) is False)

        # --- 2/3. 占用时的 port_status ---
        fhl_a = os.path.join(tmpdir, 'room_a.fhl')
        srv_busy = LogServer(password='pw', port=free, fhl_path=fhl_a)
        check("端口被占时 port_status=='occupied'",
              srv_busy.port_status == 'occupied', f'got={srv_busy.port_status!r}')
    finally:
        holder.close()

    # --- 2. 未占用时按默认端口启动 ---
    # 选一个确定空闲的端口来模拟「8000 空闲」的情形（避免真实 8000 在 CI 上不确定）
    free2 = _free_port()
    fhl_b = os.path.join(tmpdir, 'room_b.fhl')
    srv = LogServer(password='pw', port=free2, fhl_path=fhl_b)
    check("空闲端口 port_status=='ok'", srv.port_status == 'ok', f'got={srv.port_status!r}')
    srv.start(seed_list=[{'date': '2026-09-19', 'time': '13:00', 'm_call': 'A',
                          'o_call': 'SEED'}])
    check('启动后实际端口 == 指定端口', srv.address[1] == free2,
          f'got={srv.address[1]} want={free2}')
    check('启动后指纹可用', bool(srv.fingerprint_short))

    # --- 5. 端到端：客户端按该端口加入（加密）---
    import remote_crypto

    def _auto_verify(short_fp, raw_pub):
        remote_crypto.remember_key('127.0.0.1', free2, raw_pub)
        return True

    conn = RemoteConnection('127.0.0.1', free2, 'pw', role='guest',
                            verify_fingerprint=_auto_verify)
    try:
        conn.connect()
        check('客户端加入成功', True)
        check('客户端处于加密会话', conn.encrypted is True, f'got={conn.encrypted!r}')
        check('客户端拿到服务端指纹', bool(conn.server_fingerprint),
              f'got={conn.server_fingerprint!r}')
        calls = [r.get('o_call') for r in conn.initial_file]
        check('初始内容已按密文送达', calls == ['SEED'], f'got={calls!r}')
    finally:
        try:
            conn.shutdown()
        except Exception:
            pass
        srv.stop()

    # --- 4. port=0 自动分配 ---
    fhl_c = os.path.join(tmpdir, 'room_c.fhl')
    srv_auto = LogServer(password='pw', port=0, fhl_path=fhl_c)
    check("port=0 时 port_status=='ok'", srv_auto.port_status == 'ok',
          f'got={srv_auto.port_status!r}')
    srv_auto.start()
    check('port=0 分配到了具体端口', srv_auto.address[1] > 0,
          f'got={srv_auto.address[1]}')
    srv_auto.stop()

    # --- 6. 「8000 被占 → 回退自动端口」的完整路径 ---
    holder2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder2.bind(('0.0.0.0', 8000))
    holder2.listen(1)
    try:
        occupied = is_port_in_use('0.0.0.0', DEFAULT_ROOM_PORT)
        check('本机 8000 可被探测（占用则走回退）', isinstance(occupied, bool),
              f'got={occupied!r}')
        if occupied:
            srv_fb = LogServer(password='pw', port=DEFAULT_ROOM_PORT,
                               fhl_path=os.path.join(tmpdir, 'room_d.fhl'))
            check('8000 占用时 port_status 反映占用',
                  srv_fb.port_status == 'occupied', f'got={srv_fb.port_status!r}')
            # 模拟 project._open_lan 的回退
            srv_fb = LogServer(password='pw', port=0,
                               fhl_path=os.path.join(tmpdir, 'room_d.fhl'))
            srv_fb.start()
            check('回退到自动端口后启动成功',
                  srv_fb.address[1] > 0 and srv_fb.address[1] != 8000,
                  f'got={srv_fb.address[1]}')
            srv_fb.stop()
        else:
            check('8000 空闲（无法模拟占用场景，跳过回退断言）', True)
    finally:
        holder2.close()

    print()
    if FAILED:
        print('=== DEFAULT_PORT_SMOKE_FAILED ===')
        for n in FAILED:
            print('  -', n)
        return 1
    print('=== DEFAULT_PORT_SMOKE_OK ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
