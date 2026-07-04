# 业余无线电台通联日志 
# F HamLog

## 基本功能
### 编辑日志
支持基本的业余无线电台通联日志的记录。
支持从ADI文件导入导出。
支持从HAM个人工具导入。
支持导出为表格。


### 支持安装插件
可以自行编写插件，并安装。

### 远程日志
**1.8.0及以上版本不支持远程日志。如需继续使用，请自行构建[#remote_project.py](https://github.com/Mubi-Baihua/F_HamLog/blob/main/%23remote_project.py)。**   

支持编辑远程服务器上的日志。

远程日志服务端请下载 [F HamLog Remote Log Server 1.1.0.exe](https://github.com/Mubi-Baihua/F_HamLog/blob/main/F_HamLog_Remote_Log_Server_1.1.0/F%20HamLog%20Remote%20Log%20Server%201.1.0.exe)。

## 相关技术文档

### 插件开发

可查看[示例插件](https://github.com/Mubi-Baihua/F_HamLog/blob/main/F%20%E6%A0%BC%E5%BC%8F%E4%BC%98%E5%8C%96.fhlpypack)。

#### 插件主体结构
```
XML:{"describe":"<插件的描述>","pack version":"<插件的版本>","available fhl version":"<插件适配的F HamLog版本>","producer":"<开发者>"}
python:
#你的python代码
```

#### 插件python代码
##### 输入
运行时F HamLog会将当前文件放在python文件的工作目录下。名称为：input.fhl。编码使用utf-8。

示例输入代码:
```python
import json
from pathlib import Path

abs_path = Path(__file__).resolve().parent

with open(f"{abs_path}/input.fhl", "r", encoding="utf-8") as f:
    file_list = json.load(f)  
```
##### 输出
运行时F HamLog会读取python文件的工作目录下的输出文件。名称为：output.fhl。编码使用utf-8。

示例输出代码:
```python
from pathlib import Path

abs_path = Path(__file__).resolve().parent

with open(f"{abs_path}/output.fhl", "w", encoding="utf-8") as f:
    json.dump(file_list, f, ensure_ascii=False, indent=2)
```
#### 插件打包
将插件文件保存为 *.fhlpypack 文件。编码使用utf-8。

### FHL文件格式
FHL文件格式为json文件。编码使用utf-8。

参考文件：
```json
[
    {
    "date": "2026-01-27",
    "time": "11:27",
    "m_call": "BI8SQL",
    "o_call": "BD8SE",
    "freq": "438.7",
    "freq_rx": "438.7",
    "mode": "FM",
    "prop_mode": "SAT",
    "sat_name": "SO-50",
    "m_rst": "59",
    "o_rst": "59",
    "m_qth": "昆明",
    "o_qth": "成都",
    "m_dig": "UV-K5",
    "o_dig": "DM9100",
    "m_ant": "原装",
    "o_ant": "原装",
    "m_pow": "H",
    "o_pow": "H",
    "notes": "中继点名"
  },
  {
    "date": "2026-01-03",
    "time": "13:42",
    "m_call": "BI8SQL",
    "o_call": "BG8SVJ",
    "freq": "438.7",
    "freq_rx": "438.7",
    "mode": "FM",
    "prop_mode": "SAT",
    "sat_name": "ARISS",
    "m_rst": "59",
    "o_rst": "59",
    "m_qth": "昆明",
    "o_qth": "西南林业大学",
    "m_dig": "IC-705",
    "o_dig": "IC-9700",
    "m_ant": "原装",
    "o_ant": "771",
    "m_pow": "H",
    "o_pow": "M",
    "notes": "测试设备"
  }
]
```

字典中字段对应的中文：
```json
{
    "date": "日期",
    "time": "时间",
    "m_call": "己方呼号",
    "o_call": "对方呼号",
    "freq": "频率",
    "freq_rx": "接收频率",
    "mode": "调制模式",
    "prop_mode": "传播方式",
    "sat_name": "卫星名称",
    "m_rst": "己方接收信号",
    "o_rst": "对方接收信号",
    "m_qth": "己方QTH",
    "o_qth": "对方QTH",
    "m_dig": "己方设备",
    "o_dig": "对方设备",
    "m_ant": "己方天线",
    "o_ant": "对方天线",
    "m_pow": "己方功率",
    "o_pow": "对方功率",
    "notes": "备注"
}
```

##### Coded by [BI8SQL](https://mubi-baihua.github.io/)