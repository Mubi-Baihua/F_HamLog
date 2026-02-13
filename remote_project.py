from PySide6.QtWidgets import *
from PySide6.QtGui import QAction
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt  # 新增导入 Qt
from functools import partial
from PySide6.QtCore import QThread, Signal
import subprocess
import time as time_
import sys
import socket
import re
import webbrowser
import urllib.parse

file = []
socket_ = None
network_thread = None
def main(window_ip):
    def remote_project(ip,port,password):
        global socket_
        try: 
        
            socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socket_.connect((ip, int(port)))
        except Exception as e:
            QMessageBox.warning(window_ip, "登录失败", f"请检查服务端IP和端口是否正确！\n错误信息：{e}")
            return
        socket_.send(password.encode('utf-8'))
        if socket_.recv(1024).decode('utf-8') == 'Login':
            #QMessageBox.information(window_ip, "登录成功", "登录成功！\n退出时请使用文件菜单中的退出选项！")
            msg_box = QMessageBox(window_ip)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("登录成功")
            msg_box.setText("登录成功！\n退出时请使用文件菜单中的退出选项！")
            msg_box.setModal(False)  # 设置为非模态
            msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
            msg_box.show()
            msg_box.raise_()        # 将窗口提升到顶层
            msg_box.activateWindow()
        else:
            QMessageBox.warning(window_ip, "登录失败", "密码错误！")
            return
        



        global file

        socket_.send('send_fhl'.encode('utf-8'))
        import json
        received_data = socket_.recv(1024**3).decode('utf-8')
        try:
            file = json.loads(received_data)
        except json.JSONDecodeError:
            file = eval(received_data)
       
        table = None

        window_ip.close()


        def table_update(delete=True):
            global window, table
            if delete:
                layout.removeWidget(table)
                table.deleteLater()
                table = None
                save(masage=False)
                

            file_length = len(file)
            # 创建表格部件
            table = QTableWidget(file_length, 11) 
            table.setHorizontalHeaderLabels(["日期","时间","己方呼号","对方呼号","频率","调制模式", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            print(file_length)
            # 添加一些示例数据
            for i in range(file_length):
                date = QTableWidgetItem(file[i]['date'])
                table.setItem(i, 0, date)
                time = QTableWidgetItem(file[i]['time'])
                table.setItem(i, 1, time)
                m_call = QTableWidgetItem(file[i]['m_call'])
                table.setItem(i, 2, m_call)
                o_call = QTableWidgetItem(file[i]['o_call'])
                table.setItem(i, 3, o_call)
                freq = QTableWidgetItem(file[i]['freq'])
                table.setItem(i, 4, freq)
                mode = QTableWidgetItem(file[i]['mode'])
                table.setItem(i, 5, mode)
                m_rst = QTableWidgetItem(file[i]['m_rst'])
                table.setItem(i, 6, m_rst)
                o_rst = QTableWidgetItem(file[i]['o_rst'])
                table.setItem(i, 7, o_rst)
                m_qth = QTableWidgetItem(file[i]['m_qth'])
                table.setItem(i, 8, m_qth)
                o_qth = QTableWidgetItem(file[i]['o_qth'])
                table.setItem(i, 9, o_qth)
                other_button = QPushButton("更多")
                table.setCellWidget(i, 10, other_button)
                other_button.clicked.connect(partial(project_others, i))

                # 将表格添加到布局中
            layout.addWidget(table)

            table.scrollToBottom()  # 自动跳到底部

        def new():
            with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
                xml_dict = eval(f.read())
            global project_others_window,file
            index = len(file)
            date = time_.strftime("%Y-%m-%d", time_.localtime())
            time = time_.strftime("%H:%M", time_.localtime())
            file_app = {
                'date': date,
                'time': time,
                'm_call': xml_dict['m_call'],
                'o_call': '',
                'freq': '',
                'mode': '',
                'm_rst': '59',
                'o_rst': '59',
                'm_qth': xml_dict['m_qth'],
                'o_qth': '',
                "m_dig": xml_dict['m_dig'],
                'o_dig': '',
                'm_ant': '',
                'o_ant': '',
                'm_pow': '',
                'o_pow': '',
                'notes': ''
            }
            
            project_others_window = QMainWindow()
            project_others_window.resize(400, 600)
            project_others_window.setWindowTitle('新建日志')
            table_others = QTableWidget(17, 2)
            table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
            table_others.setColumnWidth(1, 250)
            
            table_others.setHorizontalHeaderLabels(["项目", "内容"])
            translation_dict = {
                'date': '日期',
                'time': '时间',
                'm_call': '己方呼号',
                'o_call': '对方呼号',
                'freq': '频率',
                'mode': '调制模式',
                'm_rst': '己方接收信号','o_rst': '对方接收信号',
                'm_qth': '己方QTH','o_qth': '对方QTH',
                "m_dig": '己方设备','o_dig': '对方设备',
                'm_ant': '己方天线','o_ant': '对方天线',
                'm_pow': '己方功率','o_pow': '对方功率',
                'notes': '备注'
            }
            row = 0
            for i in translation_dict.keys():
                item = QTableWidgetItem(translation_dict[i])
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
                table_others.setItem(row, 0, item)
                
                item2 = QTableWidgetItem(file_app[i])  # 第2列可以编辑
                table_others.setItem(row, 1, item2)
                row += 1
            central_widget = QWidget()
            project_others_window.setCentralWidget(central_widget)
            layout_others = QVBoxLayout(central_widget)
            layout_others.addWidget(table_others)
            def save_changes():
                # 获取表格数据并更新到 file 结构
                keys_list = list(translation_dict.keys())
                for row in range(len(keys_list)):
                    key = keys_list[row]

                    if key == 'date':
                        if not re.search(r'^\d{4}-\d{2}-\d{2}$', table_others.item(row, 1).text()):
                                QMessageBox.warning(project_others_window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                                return
                    elif key == 'time':
                        if not re.search(r'^\d{2}:\d{2}$', table_others.item(row, 1).text()):
                            QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                            return
                    elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                        if table_others.item(row, 1).text() == '':
                            QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                            return

                    item = table_others.item(row, 1)  # 第二列是可编辑的内容
                    if item!=None:
                        file_app[key] = item.text()
                project_others_window.close()

                file.append(file_app)

                table_update()
            save_button = QPushButton("新建日志")
            save_button.clicked.connect(save_changes)
            layout_others.addWidget(save_button)
            
            project_others_window.show()

        def project_others(index):
            global project_others_window,file
            project_others_window = QMainWindow()
            project_others_window.resize(400, 670)
            project_others_window.setWindowTitle('更多信息')
            table_others = QTableWidget(17, 2)
            table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
            table_others.setColumnWidth(1, 250)
            
            table_others.setHorizontalHeaderLabels(["项目", "内容"])
            translation_dict = {
                'date': '日期',
                'time': '时间',
                'm_call': '己方呼号',
                'o_call': '对方呼号',
                'freq': '频率',
                'mode': '调制模式',
                'm_rst': '己方接收信号','o_rst': '对方接收信号',
                'm_qth': '己方QTH','o_qth': '对方QTH',
                "m_dig": '己方设备','o_dig': '对方设备',
                'm_ant': '己方天线','o_ant': '对方天线',
                'm_pow': '己方功率','o_pow': '对方功率',
                'notes': '备注'
            }
            row = 0
            for i in translation_dict.keys():
                item = QTableWidgetItem(translation_dict[i])
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
                table_others.setItem(row, 0, item)
                
                
                item2 = QTableWidgetItem(file[index][i])  # 第2列可以编辑
                table_others.setItem(row, 1, item2)
                row += 1
            central_widget = QWidget()
            project_others_window.setCentralWidget(central_widget)
            layout_others = QVBoxLayout(central_widget)
            layout_others.addWidget(table_others)
            def save_changes():
                # 获取表格数据并更新到 file 结构
                keys_list = list(translation_dict.keys())
                for row in range(len(keys_list)):
                    key = keys_list[row]

                    if key == 'date':
                        if not re.search(r'^\d{4}-\d{2}-\d{2}$', table_others.item(row, 1).text()):
                            QMessageBox.warning(project_others_window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                            return
                    elif key == 'time':
                        if not re.search(r'^\d{2}:\d{2}$', table_others.item(row, 1).text()):
                            QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                            return
                    elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                        if table_others.item(row, 1).text() == '':
                            QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                            return

                    item = table_others.item(row, 1)  # 第二列是可编辑的内容
                    if item!=None:
                        file[index][key] = item.text()
                project_others_window.close()
                table_update()
            def del_log(index):
                if QMessageBox.question(window, "删除日志", "确定要删除此日志吗？") == QMessageBox.Yes:
                    file.pop(index)
                    project_others_window.close()
                    table_update()
            def open_qrz():
                call = file[index].get('o_call','').strip()
                if call == '':
                    QMessageBox.warning(project_others_window, 'QRZ', '对方呼号为空，无法打开 QRZ。')
                    return
                url = f"https://www.qrz.com/db/{urllib.parse.quote_plus(call)}"
                webbrowser.open(url)

            qrz_button = QPushButton("查看对方QRZ主页")
            qrz_button.clicked.connect(open_qrz)
            layout_others.addWidget(qrz_button)
            save_button = QPushButton("保存更改")
            save_button.clicked.connect(save_changes)
            layout_others.addWidget(save_button)

            del_button = QPushButton("删除日志")
            del_button.clicked.connect(lambda:del_log(index))
            layout_others.addWidget(del_button)
            
            project_others_window.show()

        def save(masage=True):
            import json
            socket_.send(f'save_fhl$#${json.dumps(file, ensure_ascii=False)}'.encode('utf-8'))
            if masage:
                QMessageBox.information(window, "保存成功", "保存成功！")

        def osave():
            import json
            save_path, _ = QFileDialog.getSaveFileName(
                window,  # 父窗口，可以是None或者您的主窗口
                "另存为文件",  # 对话框标题
                "",  # 初始目录，空字符串表示使用系统默认
                "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
            )
            if save_path == '':
                return
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(file, f, ensure_ascii=False, indent=2)
                QMessageBox.information(window, "另存成功", "另存成功！")

        def esave():
            import json
            socket_.send(f'save$#${json.dumps(file, ensure_ascii=False)}'.encode('utf-8'))
            QMessageBox.information(window, "保存成功", "保存成功！")
            socket_.send('exit'.encode('utf-8'))
            if 'network_thread' in globals():
                network_thread.stop()
                network_thread.wait()
            window.close()

        def ee():
            global socket_
            if 'network_thread' in globals():
                network_thread.stop()
                network_thread.wait()
            socket_.send('exit'.encode('utf-8'))
            window.close()

        def import_from_HAM_tolls_():
            global file
            old_file = file.copy()  # 使用copy()确保是深拷贝
            import import_from_HAM_tolls
            file = import_from_HAM_tolls.main(file)
            table_update()
            if QMessageBox.question(window, "导入日志", "应用导入吗？") == QMessageBox.No:
                file = old_file
                table_update()  # 确保界面更新

        def import_from_ADI():
            global file
            old_file = file.copy()
            import input_adi
            try:
                file = input_adi.main(file)
            except Exception as e:
                QMessageBox.warning(window, "导入失败", f"导入 ADI 失败：{e}")
                return
            table_update()
            if QMessageBox.question(window, "导入日志", "应用导入吗？") == QMessageBox.No:
                file = old_file
                table_update()
        
        def output_adi(file):
            import output_adi

            if output_adi.main(file):
                QMessageBox.information(window, "导出成功", "导出成功！")

        def output_excel(file):
            import output_excel
            if output_excel.main(file):
                QMessageBox.information(window, "导出成功", "导出成功！")

        window = QMainWindow()
        window.resize(1200, 700)
        window.setWindowTitle(f'F HamLog 1 - 远程日志({ip}:{port})')
        # window.showMaximized()
        menu_bar = window.menuBar()

        # 创建"文件"菜单
        file_menu = menu_bar.addMenu('文件')

        save_action = QAction('保存', window)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(lambda: save())
        file_menu.addAction(save_action)

        osave_action = QAction('另存为', window)
        osave_action.setShortcut('Ctrl+Shift+S')
        osave_action.triggered.connect(lambda: osave())
        file_menu.addAction(osave_action)

        file_menu.addSeparator()

        sexit_action = QAction('保存并退出', window)
        sexit_action.triggered.connect(lambda: esave())
        file_menu.addAction(sexit_action)

        zexit_action = QAction('退出', window)
        zexit_action.triggered.connect(lambda: ee())
        file_menu.addAction(zexit_action)

        import_menu = menu_bar.addMenu('导入/导出')

        import_from_ADI_action = QAction('从ADI导入日志', window)
        import_from_ADI_action.triggered.connect(lambda: import_from_ADI())
        import_menu.addAction(import_from_ADI_action)

        import_from_HAM_tolls_action = QAction('从 HAM个人工具 导入日志', window)
        import_from_HAM_tolls_action.triggered.connect(lambda: import_from_HAM_tolls_())
        import_menu.addAction(import_from_HAM_tolls_action)

        import_menu.addSeparator()

        export_adi_action = QAction('导出ADI文件', window)
        export_adi_action.triggered.connect(lambda: output_adi(file))
        import_menu.addAction(export_adi_action)

        export_excel_action = QAction('导出为表格', window)
        export_excel_action.triggered.connect(lambda: output_excel(file))
        import_menu.addAction(export_excel_action)

        def list_time():
            try:
                file.sort(key=lambda x: (x.get('date', ''), x.get('time', '')))
                table_update()
                QMessageBox.information(window, "排序完成", "按时间排序完成。")
            except Exception as e:
                QMessageBox.warning(window, "排序失败", str(e))

        def research_call(file_param=None):
            global research_window
            text, ok = QInputDialog.getText(window, "按呼号搜索", "请输入呼号或其一部分：")
            if not ok or text.strip() == '':
                return
            q = text.strip().lower()
            matches = [(i, rec) for i, rec in enumerate(file) if q in rec.get('o_call', '').lower()]
            if not matches:
                QMessageBox.information(window, "搜索结果", "未找到任何匹配记录。")
                return
            research_window = QMainWindow()
            research_window.resize(1200, 500)
            research_window.setWindowTitle(f"搜索结果：{text}")
            central = QWidget()
            research_window.setCentralWidget(central)
            lay = QVBoxLayout(central)
            table_r = QTableWidget(len(matches), 11)
            table_r.setHorizontalHeaderLabels(["日期","时间","己方呼号","对方呼号","频率","调制模式", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
            table_r.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for row, (orig_index, rec) in enumerate(matches):
                table_r.setItem(row, 0, QTableWidgetItem(rec.get('date', '')))
                table_r.setItem(row, 1, QTableWidgetItem(rec.get('time', '')))
                table_r.setItem(row, 2, QTableWidgetItem(rec.get('m_call', '')))
                table_r.setItem(row, 3, QTableWidgetItem(rec.get('o_call', '')))
                table_r.setItem(row, 4, QTableWidgetItem(rec.get('freq', '')))
                table_r.setItem(row, 5, QTableWidgetItem(rec.get('mode', '')))
                table_r.setItem(row, 6, QTableWidgetItem(rec.get('m_rst', '')))
                table_r.setItem(row, 7, QTableWidgetItem(rec.get('o_rst', '')))
                table_r.setItem(row, 8, QTableWidgetItem(rec.get('m_qth', '')))
                table_r.setItem(row, 9, QTableWidgetItem(rec.get('o_qth', '')))
                more_btn = QPushButton("更多")
                more_btn.clicked.connect(partial(project_others, orig_index))
                table_r.setCellWidget(row, 10, more_btn)
            lay.addWidget(table_r)
            table_r.scrollToBottom()
            research_window.show()
        def research_call(file_param=None):
            global research_window
            # 弹出高级搜索对话：选择字段 + 关键词 + 匹配方式
            dlg = QDialog(window)
            dlg.setWindowTitle('搜索')
            dlg_layout = QVBoxLayout(dlg)

            h1 = QHBoxLayout()
            h1.addWidget(QLabel('字段：'))
            combo = QComboBox()
            choices = [
                ('o_call', '对方呼号'),
                ('m_call', '己方呼号'),
                ('date', '日期'),
                ('time', '时间'),
                ('freq', '频率'),
                ('mode', '调制模式'),
                ('m_dig', '己方设备'),
                ('o_dig', '对方设备'),
                ('m_qth', '己方QTH'),
                ('o_qth', '对方QTH'),
                ('m_ant', '己方天线'),
                ('o_ant', '对方天线'),
                ('m_pow', '己方功率'),
                ('o_pow', '对方功率'),
                ('notes', '备注')
            ]
            for k, v in choices:
                combo.addItem(v, k)
            h1.addWidget(combo)
            dlg_layout.addLayout(h1)

            h2 = QHBoxLayout()
            h2.addWidget(QLabel('关键词：'))
            edit = QLineEdit()
            h2.addWidget(edit)
            dlg_layout.addLayout(h2)

            h3 = QHBoxLayout()
            h3.addWidget(QLabel('匹配方式：'))
            match_combo = QComboBox()
            match_combo.addItems(['包含', '完全匹配'])
            h3.addWidget(match_combo)
            dlg_layout.addLayout(h3)

            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            dlg_layout.addWidget(btns)

            if dlg.exec() != QDialog.Accepted:
                return

            field = combo.currentData()
            q = edit.text().strip().lower()
            if q == '':
                QMessageBox.information(window, '搜索', '请输入关键词。')
                return
            exact = (match_combo.currentText() == '完全匹配')

            matches = []
            for i, rec in enumerate(file):
                val = str(rec.get(field, '')).lower()
                if (exact and val == q) or (not exact and q in val):
                    matches.append((i, rec))

            if not matches:
                QMessageBox.information(window, "搜索结果", "未找到任何匹配记录。")
                return

            research_window = QMainWindow()
            research_window.resize(1200, 500)
            research_window.setWindowTitle(f"搜索结果：{edit.text().strip()}")
            central = QWidget()
            research_window.setCentralWidget(central)
            lay = QVBoxLayout(central)
            table_r = QTableWidget(len(matches), 11)
            table_r.setHorizontalHeaderLabels(["日期","时间","己方呼号","对方呼号","频率","调制模式", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
            table_r.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for row, (orig_index, rec) in enumerate(matches):
                table_r.setItem(row, 0, QTableWidgetItem(rec.get('date', '')))
                table_r.setItem(row, 1, QTableWidgetItem(rec.get('time', '')))
                table_r.setItem(row, 2, QTableWidgetItem(rec.get('m_call', '')))
                table_r.setItem(row, 3, QTableWidgetItem(rec.get('o_call', '')))
                table_r.setItem(row, 4, QTableWidgetItem(rec.get('freq', '')))
                table_r.setItem(row, 5, QTableWidgetItem(rec.get('mode', '')))
                table_r.setItem(row, 6, QTableWidgetItem(rec.get('m_rst', '')))
                table_r.setItem(row, 7, QTableWidgetItem(rec.get('o_rst', '')))
                table_r.setItem(row, 8, QTableWidgetItem(rec.get('m_qth', '')))
                table_r.setItem(row, 9, QTableWidgetItem(rec.get('o_qth', '')))
                more_btn = QPushButton("更多")
                more_btn.clicked.connect(partial(project_others, orig_index))
                table_r.setCellWidget(row, 10, more_btn)

            lay.addWidget(table_r)
            table_r.scrollToBottom()
            research_window.show()

        tool_menu = menu_bar.addMenu('功能')

        list_action = QAction('按时间排序', window)
        list_action.setShortcut('Ctrl+L')
        list_action.triggered.connect(lambda: list_time())
        tool_menu.addAction(list_action)

        tool_menu.addSeparator()

        research_call_action = QAction('搜索', window)
        research_call_action.setShortcut('Ctrl+R')
        research_call_action.triggered.connect(lambda: research_call(file))
        tool_menu.addAction(research_call_action)

        central_widget = QWidget()
        window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        button_new = QPushButton("新建日志（Ctrl+N）", window)
        button_new.setShortcut('Ctrl+N')
        button_new.clicked.connect(lambda: new())
        layout.addWidget(button_new)

        pack_menu = menu_bar.addMenu('插件')
        with open('file/pack_list.txt', 'r', encoding='utf-8') as f:
            pack_list = eval(f.read())
        # 在菜单栏上显示插件状态（若无插件则显示“未安装插件”）
        plugin_label = QLabel()
        plugin_label.setStyleSheet("color: gray; padding: 4px;")
        plugin_label.setAlignment(Qt.AlignCenter)
        plugin_action = QWidgetAction(window)
        plugin_action.setDefaultWidget(plugin_label)
        pack_menu.addAction(plugin_action)
        if len(pack_list) == 0:
            plugin_label.setText("未安装插件，请前往 设置 安装插件")
        else:
            plugin_action.setVisible(False)
        
        def run_pack(pack_name):
            """返回一个 QAction，触发时执行插件文件夹下的 main.py 或 run.py（使用 runpy）。"""
            action = QAction(pack_name, window)

            def handler():
                global file
                with open(f'file/pypack/{pack_name}/input.fhl','w',encoding='utf-8') as f:
                    f.write(str(file))
                subprocess.run(['python', f'file/pypack/{pack_name}/main.py'])
                try:
                    with open(f'file/pypack/{pack_name}/output.fhl','r',encoding='utf-8') as f:
                        file = json.load(f)
                except FileNotFoundError:
                    QMessageBox.warning(window, "插件错误", f"插件 {pack_name} 未正确生成输出文件！")
                table_update()

            action.triggered.connect(handler)
            return action

        for pack in pack_list:
            pack_menu.addAction(run_pack(pack))
        

        table_update(delete=False)
        table_update()

        class NetworkThread(QThread):
            update_signal = Signal()
            
            def __init__(self):
                super().__init__()
                self._running = True
            
            def stop(self):
                self._running = False
            
            def run(self):
                while self._running:
                    socket_.send('Next'.encode('utf-8'))
                    self.msleep(1000*1) 

        global network_thread
        network_thread = NetworkThread()
        network_thread.start()

        def setup_close_handler(window):
            global network_thread
            original_close_event = window.closeEvent if hasattr(window, 'closeEvent') else None
            
            def close_event(event):
                global network_thread
                # 停止网络线程
                if 'network_thread' in globals() and network_thread.isRunning():
                    network_thread.stop()
                    network_thread.wait(3000)
                # 调用原始关闭事件
                if original_close_event:
                    original_close_event(event)
                else:
                    event.accept()
                print("窗口已关闭")
            
            window.closeEvent = close_event
    
        setup_close_handler(window)

        window.show()
    window_ip.resize(300, 150)
    window_ip.setFixedSize(300, 150)
    window_ip.setWindowTitle(f'F HamLog 1 - 远程日志')

    central_widget = QWidget()
    window_ip.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
        
    first_layout = QHBoxLayout()
    first_layout.addWidget(QLabel("服务端IP:"))
    first_input = QLineEdit()
    first_layout.addWidget(first_input)
        
    second_layout = QHBoxLayout()
    second_layout.addWidget(QLabel("端口:"))
    second_input = QLineEdit()
    second_layout.addWidget(second_input)

    third_layout = QHBoxLayout()
    third_layout.addWidget(QLabel("密码:"))
    third_input = QLineEdit()
    third_layout.addWidget(third_input)
        

    ok_button = QPushButton("登录")
    ok_button.clicked.connect(lambda: remote_project(ip=first_input.text(),port=second_input.text(),password=third_input.text()))
    
        
    layout.addLayout(first_layout)
    layout.addLayout(second_layout)
    layout.addLayout(third_layout)
    layout.addWidget(ok_button)
        
    window_ip.setLayout(layout)
    
    window_ip.show()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()