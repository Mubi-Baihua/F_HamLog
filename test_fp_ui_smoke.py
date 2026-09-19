# -*- coding: utf-8 -*-
"""指纹确认 UI 与加密状态显示 离屏烟测。

覆盖：
1. make_fingerprint_verifier 在 'match'（已知密钥一致）时静默放行，不弹窗。
2. 'new'（首次连接）时弹窗，点「确认已核对」后放行并写入 known_server_keys.txt。
3. 'mismatch'（密钥变了）时弹窗，默认按钮是「取消连接」，点取消即拒绝。
4. LogServer.fingerprint_short 可用且格式为 4-4 分组。
5. SessionCipher 加解密往返、乱序解密、重放拒绝。
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

FAILED = []


def check(name, cond, extra=''):
    if cond:
        print(f'  PASS  {name}')
    else:
        print(f'  FAIL  {name}  {extra}')
        FAILED.append(name)


def main():
    from PySide6 import QtWidgets, QtCore
    QTimer = QtCore.QTimer

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    import remote_crypto
    import remote_server

    # --- 1. 密钥指纹格式 ---
    tmpdir = tempfile.mkdtemp(prefix='fhl_fp_ui_')
    key_path = os.path.join(tmpdir, 'server_5555.fhlkey')
    priv, created = remote_crypto.load_or_create_server_key(key_path)
    check('首次创建密钥文件', created and os.path.exists(key_path))
    srv_raw = remote_crypto.public_key_bytes(priv)
    short = remote_crypto.fingerprint_short(srv_raw)
    parts = short.split('-')
    check('指纹为 4-4 分组共 8 组', len(parts) == 8 and all(len(p) == 4 for p in parts),
          f'got={short!r}')
    check('指纹为大写十六进制',
          all(c in '0123456789ABCDEF' for c in short.replace('-', '')),
          f'got={short!r}')

    # --- 2. SessionCipher 往返 / 乱序 / 重放 ---
    key = remote_crypto.new_session_key()
    c1 = remote_crypto.SessionCipher(key)
    c2 = remote_crypto.SessionCipher(key)
    p1 = c1.encrypt('第一帧：你好')
    p2 = c1.encrypt('第二帧：world')
    check('乱序解密：先解第二帧', c2.decrypt(p2) == '第二帧：world')
    check('乱序解密：再解第一帧', c2.decrypt(p1) == '第一帧：你好')
    try:
        c2.decrypt(p1)
        check('重放帧被拒绝', False, '未抛异常')
    except Exception:
        check('重放帧被拒绝', True)
    check('发送计数', c1.send_count == 2, f'got={c1.send_count}')

    # --- 3. 指纹校验回调 ---
    # 用一个假的 parent，只测试逻辑分支
    parent = QtWidgets.QWidget()

    def click_dialog_button(keyword, timeout_ms=3000):
        """在可见对话框上点击文本含 keyword 的按钮。

        注意：offscreen 下 app.topLevelWidgets() 同时包含对话框和不可见的 parent，
        findChildren 会把两边按钮都捞出来；必须限定在 isVisible() 的对话框上，
        否则点到隐藏控件上不会触发槽函数（表现为挂死）。
        """
        box = {'done': False}

        def tick():
            for w in app.topLevelWidgets():
                if not (isinstance(w, QtWidgets.QDialog) and w.isVisible()):
                    continue
                for btn in w.findChildren(QtWidgets.QPushButton):
                    if keyword in btn.text() and btn.isVisible():
                        btn.click()
                        box['done'] = True
                        return
            if not box['done']:
                QTimer.singleShot(50, tick)

        QTimer.singleShot(50, tick)
        return box

    # 先让 known_keys 指向临时文件，避免污染真实记录
    orig_known = remote_crypto.known_keys_path
    known_tmp = os.path.join(tmpdir, 'known_server_keys.txt')
    remote_crypto.known_keys_path = lambda *a, **kw: known_tmp
    try:
        from project import make_fingerprint_verifier
        verify = make_fingerprint_verifier(parent, '127.0.0.1', 5555)

        # 3a. 首次连接：应弹窗，自动点「指纹一致，继续连接」
        click_dialog_button('指纹一致，继续连接')
        ok_new = verify(short, srv_raw)
        check("'new' 弹窗后点确认 -> 放行", ok_new is True, f'got={ok_new!r}')
        check('确认后写入了 known_server_keys.txt', os.path.exists(known_tmp))
        st, info = remote_crypto.check_known_key('127.0.0.1', 5555, srv_raw)
        check("再次核对状态变为 'match'", st == 'match', f'got={st!r}')

        # 3b. 已知且一致：静默放行（不应有窗口）
        ok_match = verify(short, srv_raw)
        check("'match' 静默放行（True）", ok_match is True, f'got={ok_match!r}')
        visible = [w for w in app.topLevelWidgets()
                   if isinstance(w, QtWidgets.QDialog) and w.isVisible()]
        check("'match' 不弹窗", len(visible) == 0, f'可见对话框={len(visible)}')

        # 3c. 密钥变了：应弹窗，点「取消连接」应返回 False
        other_priv = remote_crypto.generate_server_key()
        other_raw = remote_crypto.public_key_bytes(other_priv)
        other_short = remote_crypto.fingerprint_short(other_raw)

        click_dialog_button('取消连接')
        ok_bad = verify(other_short, other_raw)
        check("'mismatch' 点取消 -> 拒绝（False）", ok_bad is False, f'got={ok_bad!r}')

        # 3d. mismatch 但用户坚持连接 -> True 且更新记录
        click_dialog_button('确认已核对，继续连接')
        ok_force = verify(other_short, other_raw)
        check("'mismatch' 选「指纹一致，继续」-> 放行", ok_force is True, f'got={ok_force!r}')
        st2, info2 = remote_crypto.check_known_key('127.0.0.1', 5555, other_raw)
        check('坚持连接后记录被更新', st2 == 'match', f'got={st2!r}')
    finally:
        remote_crypto.known_keys_path = orig_known

    # --- 4. LogServer 指纹属性 ---
    srv = remote_server.LogServer(password='pw', host='127.0.0.1', port=0,
                                  fhl_path=None, key_path=None)
    check('LogServer.fingerprint_short 可用', bool(srv.fingerprint_short),
          f'got={srv.fingerprint_short!r}')
    check('LogServer 默认启用加密', srv.encrypt is True)
    srv_plain = remote_server.LogServer(password='pw', host='127.0.0.1', port=0,
                                        fhl_path=None, key_path=None, encrypt=False)
    check('encrypt=False 时无指纹', not srv_plain.fingerprint_short,
          f'got={srv_plain.fingerprint_short!r}')

    parent.deleteLater()
    app.processEvents()

    print()
    if FAILED:
        print('=== FP_UI_SMOKE_FAILED ===')
        for n in FAILED:
            print('  -', n)
        return 1
    print('=== FP_UI_SMOKE_OK ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
