from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
import sys
import json
import webbrowser
import urllib.parse
import fhl_rw
from dialog_defaults import desktop_dir

def main():
    def quick_project():
        print("通联日志")
        import project
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        save_path = 'file/main.fhl'
        print(save_path)
        data,key = fhl_rw.read_fhl_file(save_path)
        if data == None:
            return
        project.main(project_window, data, save_path,key_=key,quick_poject=True)
    def new_project():
        print("新建项目")
        import project
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        project.main(project_window)

    def open_project():
        print("打开项目")
        import project
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        save_path = ''
        save_path, _ = QFileDialog.getOpenFileName(
            window,  # 父窗口
            "打开项目",  # 对话框标题
            desktop_dir(),  # 初始目录：桌面
            "F HamLog项目 (*.fhl)"  # 文件过滤器
        )
        if save_path == '':
            return
        print(save_path)
        data,key = fhl_rw.read_fhl_file(save_path)
        if data == None:
            return
        project.main(project_window, data, save_path,key_=key)

    '''    
    def remote_project():
        print("远程项目")
        import remote_project
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        remote_project.main(project_window)'''
    
    def set():
        print("设置")
        import set
        global set_window  # 保持引用，防止被回收
        set_window = QMainWindow()
        set.main(set_window)

    def qrz_page():
        print('qrz主页')
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())
        callsign = xml_dict['m_call']
        if callsign == '':
            url = 'https://www.qrz.com'
        else:
            url = f"https://www.qrz.com/db/{urllib.parse.quote_plus(callsign)}"
        webbrowser.open(url)
    
    def batch_project():
        print("批量记录")
        import batch_project
        global batch_window  # 保持引用，防止被回收
        batch_window = QMainWindow()
        batch_project.main(batch_window)

    def satellite_pred_open():
            print("卫星过境预测")
            import satellite_window
            import batch_project
            _batch_windows = []
            def quick_log(preset):
                # 主页：使用原有批量记录方式，保存时弹出“保存方式选择”对话框
                bw = QMainWindow()
                bw.setWindowTitle('批量记录')
                batch_project.main(bw, preset=preset)
                _batch_windows.append(bw)
            satellite_window.main(None, quick_log_callback=quick_log,
                                  title='卫星过境')
    
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("file/F_HamLog.ico"))

    global window
    window = QMainWindow()
    window.resize(575, 375)
    window.setFixedSize(575, 375)
    window.setWindowTitle('F HamLog 2')

    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(24, 18, 24, 16)
    main_layout.setSpacing(6)

    ACCENT = '#2f6fed'
    BTN_H = 40

    def _style_btn(btn, primary=False):
        if primary:
            btn.setMinimumHeight(BTN_H)
            #btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{background:%s;color:#ffffff;border:none;"
                "border-radius:6px;font-size:13px;font-weight:bold;}"
                "QPushButton:hover{background:#2a63d4;}"
                "QPushButton:pressed{background:#2356ba;}" % ACCENT)

    # ---------- 标题区 ----------
    title = QLabel('F HamLog 2')
    title.setAlignment(Qt.AlignCenter)
    f = title.font(); f.setPointSize(18); f.setBold(True)
    title.setFont(f)
    sub = QLabel('业余无线电通联日志')
    sub.setAlignment(Qt.AlignCenter)
    f = sub.font(); f.setPointSize(10)
    sub.setFont(f)
    sub.setStyleSheet('color:#7a8190;')
    main_layout.addWidget(title)
    main_layout.addWidget(sub)
    main_layout.addSpacing(50)

    main_layout

    # ---------- 主操作 ----------
    button_quick = QPushButton('通联日志')
    button_quick.setFixedSize(220, 46)
    button_quick.clicked.connect(quick_project)
    _style_btn(button_quick, primary=True)
    button_quick.setDefault(True)
    main_layout.addWidget(button_quick, alignment=Qt.AlignHCenter)

    # ---------- 次要操作（两列网格） ----------
    grid_box = QWidget()
    grid_box.setFixedWidth(220)
    grid = QGridLayout(grid_box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(6)

    button_batch = QPushButton('批量记录')
    button_batch.setFixedSize(105, BTN_H)
    button_batch.clicked.connect(batch_project)
    _style_btn(button_batch)

    button_qrz = QPushButton('QRZ主页')
    button_qrz.setFixedSize(105, BTN_H)
    button_qrz.clicked.connect(qrz_page)
    _style_btn(button_qrz)

    button_sat = QPushButton('卫星过境')
    button_sat.setFixedSize(220, BTN_H)
    button_sat.clicked.connect(satellite_pred_open)
    _style_btn(button_sat)

    button_start = QPushButton('新建项目')
    button_start.setFixedSize(105, BTN_H)
    button_start.clicked.connect(new_project)
    _style_btn(button_start)

    button_open = QPushButton('打开项目')
    button_open.setFixedSize(105, BTN_H)
    button_open.clicked.connect(open_project)
    _style_btn(button_open)

    grid.addWidget(button_batch, 0, 0)
    grid.addWidget(button_qrz, 0, 1)
    grid.addWidget(button_sat, 1, 0, 1, 2)
    grid.addWidget(button_start, 2, 0)
    grid.addWidget(button_open, 2, 1)
    main_layout.addWidget(grid_box, alignment=Qt.AlignHCenter)

    # ---------- 分隔线 ----------
    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)
    main_layout.addWidget(line)

    # ---------- 设置 ----------
    button_set = QPushButton('设置')
    button_set.setFixedSize(105, BTN_H)
    button_set.clicked.connect(set)
    _style_btn(button_set)
    main_layout.addWidget(button_set, alignment=Qt.AlignHCenter)

    main_layout.addStretch(1)

    window.show()

    # 启动卫星星历（TLE）自动定时更新：按“设置”中的开关与间隔，在后台周期性刷新缓存
    import satellite_auto_update
    satellite_auto_updater = satellite_auto_update.AutoTleUpdater(window)
    satellite_auto_updater.start()

    app.exec()

if __name__ == '__main__':
    main()