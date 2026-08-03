import subprocess
import sys
from PySide6.QtWidgets import *
import os
import ast
import shutil

def is_python_installed():
    """检查系统是否安装了 Python。

    优先策略：
    1. 使用 shutil.which 检查常见命令 (python, python3, py) 是否在 PATH 中
    2. 尝试运行这些命令获取版本号
    3. 在 Windows 上作为后备检查注册表中的 PythonCore 键
    返回 True/False
    """
    # 先用 which 快速判断
    candidates = [('python', ['python', '--version']),
                  ('python3', ['python3', '--version']),
                  ('py', ['py', '-3', '--version'])]
    for name, cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return True
            except Exception:
                # 忽略某个命令的错误，继续尝试其它命令
                pass

    # 如果 which 没发现，仍然尝试直接运行命令（兼容不同环境）
    for cmd in (['python', '--version'], ['python3', '--version'], ['py', '-3', '--version']):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue

    # Windows 下作为最后手段检查注册表是否存在 Python 安装信息
    if os.name == 'nt':
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\Python\PythonCore")
                except OSError:
                    continue
                try:
                    i = 0
                    while True:
                        try:
                            _ = winreg.EnumKey(key, i)
                            return True
                        except OSError:
                            break
                        finally:
                            i += 1
                finally:
                    try:
                        winreg.CloseKey(key)
                    except Exception:
                        pass
        except Exception:
            pass

    return False

def install_python():
    try:
        # 方法1: 使用ctypes调用ShellExecuteW
        import ctypes
        from ctypes import wintypes
        
        # 获取当前脚本路径
        installer_path = os.path.abspath(r'file\python-3.13.11-amd64.exe')
        
        # 检查文件是否存在
        

        # 调用ShellExecuteW以管理员权限运行
        shell32 = ctypes.windll.shell32
        ret = shell32.ShellExecuteW(
            None, 
            "runas",  # 请求提升权限
            installer_path, 
            None,     # 参数
            None,     # 工作目录
            1         # SW_SHOWNORMAL
        )
        
        # 返回值>32表示成功
        if ret > 32:
            return True,None
        else:
            return False,'应用运行失败，请检查权限！'
    except Exception as e:
        return False,e

def main(window):
    if is_python_installed():
        print("Python 已安装")

    else:
        if QMessageBox.question(window, "未安装Python", 
                                    "Python 未安装，\n为正常使用插件需安装 Python3.13.11\n是否安装？", 
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                bool_,e = install_python()
                if bool_:
                    QMessageBox.information(window, "运行成功", "安装程序运行成功！\n安装完成后，请重新打开插件设置。")
                else:
                    QMessageBox.warning(window, "安装失败", "安装失败！\n错误信息："+str(e))
                return
        else:
                return

    plugins_dir = os.path.abspath('file/pypack')
    if not os.path.exists(plugins_dir):
        os.makedirs(plugins_dir)

    def read_pack_metadata(folder_path):
        """尝试读取 folder_path/xml.txt 并返回 dict（使用 ast.literal_eval 解析）。"""
        xml_path = os.path.join(folder_path, 'xml.txt')
        if not os.path.exists(xml_path):
            return {}
        try:
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {}
                data = ast.literal_eval(content)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
        return {}

    it = os.scandir(plugins_dir)
    pack_list = [entry.name for entry in it if entry.is_dir()]
    window.resize(700, 400)
    window.setWindowTitle('插件设置')
    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    layout_others = QVBoxLayout()
    central_widget.setLayout(layout_others)

    Label_1 = QLabel('已安装的插件')
    layout_others.addWidget(Label_1)

    btn_install = QPushButton('安装插件')
    

    table_others = QTableWidget(0, 5)
    table_others.setHorizontalHeaderLabels(["名称", "简介", '版本', '开发者', '删除'])
    layout_others.addWidget(table_others)
    layout_others.addWidget(btn_install)
    table_others.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table_others.setWordWrap(True)

    def safe_folder_name(name, fallback):
        name = str(name or '').strip()
        if not name:
            name = fallback
        # 保留字母数字和 _-，其余替换为下划线
        safe = ''.join(c if (c.isalnum() or c in ('_', '-')) else '_' for c in name)
        return safe or fallback

    def get_pack_list():
        pack_list = [entry.name for entry in os.scandir(plugins_dir) if entry.is_dir()]
        with open('file/pack_list.txt', 'w', encoding='utf-8') as f:
            f.write(str(pack_list))
        return pack_list

    def read_pack_metadata(folder_path):
        xml_path = os.path.join(folder_path, 'xml.txt')
        if not os.path.exists(xml_path):
            return {}
        try:
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {}
                data = ast.literal_eval(content)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
        return {}

    def populate_table():
        pack_list = get_pack_list()
        table_others.clearContents()
        table_others.setRowCount(len(pack_list))
        for row, name in enumerate(pack_list):
            folder = os.path.join(plugins_dir, name)
            meta = read_pack_metadata(folder)
            desc = meta.get('describe', '') or meta.get('description', '')
            version = meta.get('pack version', '') or meta.get('version', '')
            producer = meta.get('producer', '') or meta.get('author', '')

            table_others.setItem(row, 0, QTableWidgetItem(name))
            table_others.setItem(row, 1, QTableWidgetItem(str(desc)))
            table_others.setItem(row, 2, QTableWidgetItem(str(version)))
            table_others.setItem(row, 3, QTableWidgetItem(str(producer)))

            btn = QPushButton('删除')
            # 使用 lambda 默认参数绑定当前 folder
            btn.clicked.connect(lambda _, p=folder: on_delete(p))
            table_others.setCellWidget(row, 4, btn)
        
        # 调整列宽：先自动调整，然后所有列最小宽度为PySide默认宽度（100像素）
        table_others.resizeColumnsToContents()
        min_width = 100
        for i in range(5):
            current_width = table_others.columnWidth(i)
            table_others.setColumnWidth(i, max(current_width, min_width))
        
    def on_delete(folder_path):
        reply = QMessageBox.question(window, '确认删除', f"确定删除插件：{os.path.basename(folder_path)} ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(folder_path)
        except Exception as e:
            QMessageBox.warning(window, '删除失败', f'删除失败：{e}')
            return
        populate_table()

    def install_plugin():
        file_path, _ = QFileDialog.getOpenFileName(window, '选择插件包', '', 'F HamLog插件包 (*.fhlpypack *.txt);;All Files (*)')
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            xml_data = {}
            python_code = None

            if 'XML:' in content:
                start = content.index('XML:') + len('XML:')
                # 尝试查找 python 段
                py_idx = content.find('\npython:', start)
                if py_idx == -1:
                    xml_text = content[start:].strip()
                else:
                    xml_text = content[start:py_idx].strip()
                    python_code = content[py_idx + len('\npython:'):].lstrip('\n')
                try:
                    xml_data = ast.literal_eval(xml_text) if xml_text else {}
                except Exception:
                    xml_data = {}
            else:
                # 整个文件可能就是 dict 文本
                try:
                    xml_data = ast.literal_eval(content.strip())
                except Exception:
                    xml_data = {}

            # 设置插件名称为fhlpypack文件的名称（不含扩展名）
            xml_data['name'] = os.path.splitext(os.path.basename(file_path))[0]

            base_name = safe_folder_name(xml_data.get('name') or xml_data.get('describe') or os.path.splitext(os.path.basename(file_path))[0],
                                         os.path.splitext(os.path.basename(file_path))[0])
            target = os.path.join(plugins_dir, base_name)
            idx = 1
            while os.path.exists(target):
                target = os.path.join(plugins_dir, f"{base_name}_{idx}")
                idx += 1
            os.makedirs(target, exist_ok=True)

            # 如果包含版本字段，检查兼容性（可选）
            try:
                avail = list(xml_data.get('available fhl version')) 
                if not ('2.2.0' in avail):
                    QMessageBox.warning(window, '版本不匹配', f"该插件与当前F HamLog版本不兼容\n当前F HamLog版本：2.2.0\n插件适配版本：{avail}")
                    shutil.rmtree(target)
                    return
            except Exception:
                pass

            # 写入 xml.txt（保留原始字典格式，便于 ast.literal_eval 读取）
            with open(os.path.join(target, 'xml.txt'), 'w', encoding='utf-8') as xf:
                xf.write(str(xml_data))

            # 如果包含 python_code，则写入 main.py
            if python_code:
                with open(os.path.join(target, 'main.py'), 'w', encoding='utf-8') as pf:
                    pf.write(python_code)

            QMessageBox.information(window, '安装成功', f'已安装到：{target}')
            populate_table()
        except Exception as e:
            QMessageBox.warning(window, '安装失败', f'安装失败：{e}')

    btn_install.clicked.connect(install_plugin)

    # 首次填充
    populate_table()

    window.show()
if __name__ == '__main__':
    app = QApplication()
    window=QMainWindow()
    main(window)
    app.exec()