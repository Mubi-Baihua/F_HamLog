
def main(file):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from PySide6.QtCore import Qt
    import sys
    import os
    
    # 获取当前活动窗口作为父窗口
    from PySide6.QtWidgets import QApplication
    parent_window = None
    app = QApplication.instance()
    if app:
        windows = app.topLevelWidgets()
        for window in windows:
            if window.isVisible() and window.windowTitle().startswith('F HamLog'):
                parent_window = window
                break
    
    try:
        import pandas as pd
        import numpy as np
        
        # 定义翻译字典，将英文键转换为中文列名
        translation_dict = {
            'date': '日期',
            'time': '时间',
            'm_call': '己方呼号',
            'o_call': '对方呼号',
            'freq': '频率',
            'mode': '调制模式',
            'm_rst': '己方接收信号',
            'o_rst': '对方接收信号',
            'm_qth': '己方QTH',
            'o_qth': '对方QTH',
            "m_dig": '己方设备',
            'o_dig': '对方设备',
            'm_ant': '己方天线',
            'o_ant': '对方天线',
            'm_pow': '己方功率',
            'o_pow': '对方功率',
            'notes': '备注'
        }
        
        # 转换数据格式
        data_rows = []
        for entry in file:
            row = {}
            for key, chinese_name in translation_dict.items():
                row[chinese_name] = entry.get(key, '')
            data_rows.append(row)
        
        # 创建 DataFrame
        df = pd.DataFrame(data_rows)
        
        # 弹出保存对话框
        save_path, _ = QFileDialog.getSaveFileName(
            parent_window,
            "导出为Excel文件",
            "",
            "Excel文件 (*.xlsx);;所有文件 (*)"
        )
        
        if save_path:
            # 如果用户没有输入扩展名，则自动添加.xlsx
            if not save_path.endswith('.xlsx'):
                save_path += '.xlsx'
            
            # 保存为Excel文件并自动调整列宽
            with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='通联日志')
                
                # 获取工作表对象以调整列宽
                worksheet = writer.sheets['通联日志']
                
                # 自动调整列宽
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    
                    # 设置最小和最大列宽
                    adjusted_width = min(max(max_length + 2, 10), 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # 显示成功消息（在主模块中会显示）
            return True
            
    except ImportError:
        # 如果没有安装 pandas，则显示错误消息
        if parent_window:
            QMessageBox.critical(parent_window, "导出失败", "未安装pandas库，请先安装pandas以支持Excel导出功能。\n\n可以使用命令: pip install pandas openpyxl")
        else:
            print("导出失败：未安装pandas库")
        return False
    except Exception as e:
        # 处理其他可能的异常
        if parent_window:
            QMessageBox.critical(parent_window, "导出失败", f"导出过程中发生错误：\n{str(e)}")
        else:
            print(f"导出过程中发生错误：{str(e)}")
        return False