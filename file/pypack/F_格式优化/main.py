import json
from pathlib import Path

try:
    abs_path = Path(__file__).resolve().parent
    
    with open(f'{abs_path}/input.fhl', 'r', encoding='utf-8') as f:
        file_list = json.load(f)  # 使用 json 替代 eval
    
    for i in range(len(file_list)):
        
        # 安全地更新值
        if file_list[i].get('o_qth') == 'Unknown':
            file_list[i]['o_qth'] = ''
        if file_list[i].get('m_ant') == 'Antenna':
            file_list[i]['m_ant'] = ''
    
    with open(f'{abs_path}/output.fhl', 'w', encoding='utf-8') as f:
        json.dump(file_list, f, ensure_ascii=False, indent=2)
        
except FileNotFoundError:
    print("输入文件不存在")
except json.JSONDecodeError:
    print("输入文件格式错误")
except Exception as e:
    print(f"Error in F 格式优化.fhlpypack: {e}")