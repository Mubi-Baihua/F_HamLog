from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import *
def main(file):
    print("导出adi")
    
    
    
    # 选择保存文件路径
    file_path, _ = QFileDialog.getSaveFileName(
        None, "导出ADIF文件", "", "ADIF文件 (*.adi)"
    )
    
    if file_path:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # 写入ADIF文件头
                f.write("ADIF export from F HamLog\n")
                f.write("<adif_ver:5>3.1.0\n")
                f.write("<programid:8>F HamLog\n")
                f.write("<eos>\n\n")
                
                # 遍历每条QSO记录
                for qso in file:
                    # 导出基本字段
                    if qso.get('o_call'):
                        f.write(f"<call:{len(qso['o_call'])}>{qso['o_call']}\n")
                    
                    # 处理日期字段
                    if qso.get('date'):
                        # 转换日期格式 YYYY-MM-DD 到 YYYYMMDD
                        date_str = qso['date'].replace('-', '')
                        f.write(f"<qso_date:8>{date_str}\n")
                    
                    # 处理时间字段
                    if qso.get('time'):
                        # 时间格式 HH:MM 转换为 HHMM
                        time_str = qso['time'].replace(':', '')
                        f.write(f"<time_on:4>{time_str}\n")
                    
                    # 处理频率字段
                    if qso.get('freq'):
                        freq_str = str(qso['freq'])
                        f.write(f"<freq:{len(freq_str)}>{freq_str}\n")
                    
                    # 处理模式字段
                    if qso.get('mode'):
                        mode_str = str(qso['mode'])
                        f.write(f"<mode:{len(mode_str)}>{mode_str}\n")
                    
                    # 处理信号报告
                    if qso.get('m_rst'):
                        rst_sent = str(qso['m_rst'])
                        f.write(f"<rst_sent:{len(rst_sent)}>{rst_sent}\n")
                    
                    if qso.get('o_rst'):
                        rst_rcvd = str(qso['o_rst'])
                        f.write(f"<rst_rcvd:{len(rst_rcvd)}>{rst_rcvd}\n")
                    
                    # 处理己方呼号
                    if qso.get('m_call'):
                        my_call = str(qso['m_call'])
                        f.write(f"<my_call:{len(my_call)}>{my_call}\n")
                    
                    # 处理QTH信息
                    if qso.get('o_qth'):
                        qth = str(qso['o_qth'])
                        f.write(f"<qth:{len(qth)}>{qth}\n")
                    
                    if qso.get('m_qth'):
                        my_qth = str(qso['m_qth'])
                        f.write(f"<my_qth:{len(my_qth)}>{my_qth}\n")
                    
                    # 处理备注
                    if qso.get('notes'):
                        notes = str(qso['notes'])
                        f.write(f"<comment:{len(notes)}>{notes}\n")
                    
                    # 结束当前记录
                    f.write("<eor>\n\n")
            
            print(f"ADIF文件已成功导出到: {file_path}")
            return True
            
        except Exception as e:
            print(f"导出ADIF文件时出错: {e}")
            return False
    
    return False

if __name__ == '__main__':
    # 测试数据
    test_data = [
        {
            'o_call': 'BI8SQL',
            'date': '2023-12-01',
            'time': '14:30',
            'freq': '14.250',
            'mode': 'USB',
            'm_rst': '59',
            'o_rst': '59',
            'm_call': 'BG8XXX',
            'o_qth': 'Shanghai',
            'm_qth': 'Beijing',
            'notes': 'Nice QSO'
        }
    ]
    app = QApplication([])
    main(test_data)