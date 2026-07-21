import fhl_aes
import json
from PySide6.QtWidgets import *
import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QLabel, QLineEdit, QPushButton, QMessageBox)
from PySide6.QtCore import Qt

def is_utf8_text(file_path: str) -> bool:
    with open(file_path, "rb") as f:
        data = f.read()
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False
    
def get_user_key_dialog():
    """弹出对话框，返回用户输入的密钥，取消返回None"""
    dlg = QDialog()
    dlg.setWindowTitle("输入加密密钥")
    dlg.resize(350, 125)
    dlg.setFixedSize(350, 125)
    layout = QVBoxLayout(dlg)

    layout.addWidget(QLabel("请输入加密密钥："))
    key_edit = QLineEdit()
    key_edit.setEchoMode(QLineEdit.Password)
    key_edit.setPlaceholderText("密钥字符串")
    layout.addWidget(key_edit)

    # 显示隐藏按钮
    toggle_btn = QPushButton("显示/隐藏")
    def toggle():
        if key_edit.echoMode() == QLineEdit.Password:
            key_edit.setEchoMode(QLineEdit.Normal)
        else:
            key_edit.setEchoMode(QLineEdit.Password)
    toggle_btn.clicked.connect(toggle)
    layout.addWidget(toggle_btn)

    # 确定取消按钮
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    layout.addWidget(btns)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)

    # 弹窗打开，获取结果
    if dlg.exec():
        return key_edit.text().strip()
    return None

def read_fhl_file(file_path,key=None):
    """读取fhl文件，解密内容"""
    global window

    if is_utf8_text(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = eval(f.read())
    else:
        if not key:
            key = get_user_key_dialog()
        if key:
            with open(file_path, 'rb') as f:
                encrypted_data = f.read()
            try:
                decrypted_data = fhl_aes.aes_gcm_decrypt(encrypted_data, key)
                data = json.loads(decrypted_data)
            except Exception as e:
                data = None
                QMessageBox.warning(None,"解密失败", f"请检查密钥是否正确。")

                data,key = read_fhl_file(file_path)  # 重新弹出输入密钥对话框
    return data,key

def write_fhl_file(file_path, data, key=None):
    """写入fhl文件，支持加密"""
    if key:
        try:
            json_data = json.dumps(data, ensure_ascii=False)
            encrypted_data = fhl_aes.aes_gcm_encrypt(json_data, key)
            with open(file_path, 'wb') as f:
                f.write(encrypted_data)
        except Exception as e:
            QMessageBox.warning(None, "加密失败", f"请检查密钥是否正确。\n错误信息：{e}")
    else:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    
    data,key = read_fhl_file("D:/HAM/20251101日志.fhl")
    write_fhl_file('aes_.fhl',data,'123')
    data2,key = read_fhl_file('aes_.fhl')
    print(data2)

    sys.exit(app.exec())
