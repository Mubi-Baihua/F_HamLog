# -*- coding: utf-8 -*-
"""中 → 英词表。

**中文是源语言**：键就是界面代码里的中文原文（原样复制，含全角标点与空格），
值是英文译文。值里可写 ``{}`` 表示可变内容（对应 f-string / % 格式化插进去的
那一段），这样动态文案也能翻译，例如::

    '已删除 {} 条日志。': 'Deleted {} log(s).'

几个约定：

* 键必须与源码里的中文**逐字符一致**（含全角冒号「：」、书名号「」、省略号「…」）。
  源码里用 ``%d`` / ``%.2f`` 拼出来的文案，键要写成**渲染后的形状**（占位符一律 ``{}``）。
* 模板里的 ``{}`` 按出现顺序依次对应原文里的可变片段，译文顺序可自行调整。
* 只翻「会显示给用户看」的文字；写进数据文件 / 只进 print 的内容不收录。
* 中英相同的条目不必写（查不到就原样输出）。``%p%`` 是 Qt 进度条的占位符，例外保留。
"""

TRANSLATIONS = {
    # ------------------------------------------------------------------
    #  通用按钮
    # ------------------------------------------------------------------
    '保存': 'Save',
    '保存更改': 'Save changes',
    '保存并退出': 'Save and exit',
    '另存为': 'Save as',
    '另存为 F HamLog 项目': 'Save as F HamLog project',
    '取消': 'Cancel',
    '关闭': 'Close',
    '删除': 'Delete',
    '删除选中': 'Delete selected',
    '删除日志': 'Delete log',
    '删除当前列 (Ctrl+D)': 'Delete column (Ctrl+D)',
    '删除选中的日志': 'Delete selected logs',
    '添加': 'Add',
    '添加日志列 (Ctrl+N)': 'Add log column (Ctrl+N)',
    '导入': 'Import',
    '复制': 'Copy',
    '复制选中行': 'Copy selected rows',
    '粘贴': 'Paste',
    '撤销': 'Undo',
    '撤销 (Ctrl+Z)': 'Undo (Ctrl+Z)',
    '重做': 'Redo',
    '重做 (Ctrl+Y)': 'Redo (Ctrl+Y)',
    '全选': 'Select all',
    '全不选': 'Deselect all',
    '反选': 'Invert selection',
    '取消选择': 'Clear selection',
    '替换': 'Replace',
    '上移': 'Move up',
    '下移': 'Move down',
    '刷新星历': 'Refresh ephemeris',
    '恢复默认': 'Restore defaults',
    '完成 (Ctrl+S)': 'Done (Ctrl+S)',
    '新建日志（Ctrl+N）': 'New log (Ctrl+N)',
    '退出': 'Exit',
    '显示/隐藏': 'Show/Hide',
    '导入星历数据': 'Import ephemeris',
    '设置星历数据源': 'Ephemeris sources',
    '安装插件': 'Install plugin',
    '使用记事本编辑': 'Edit in Notepad',
    '查看对方QRZ主页': 'Open QRZ page',
    '编辑TQSL映射': 'Edit TQSL mapping',
    '编辑转发器': 'Edit transponder',
    '观测站设置': 'Station setup',
    '选择卫星…': 'Select satellites…',
    '取消下载': 'Cancel download',
    '取消连接': 'Disconnect',
    '取消中…': 'Cancelling…',
    '开放多人日志': 'Host online log',
    '关闭多人日志': 'Close online log',
    '加入多人日志': 'Join online log',
    '添加到 F HamLog 项目': 'Add to F HamLog project',
    '添加到默认通联日志': 'Add to default log',
    '添加到多人日志': 'Add to online log',
    '定位': 'Locate',
    '定位到此条': 'Locate this record',
    '指纹一致，继续连接': 'Fingerprint matches, continue',
    '确认已核对，继续连接': 'Confirmed, continue',
    '忽略': 'Ignore',
    '恢复': 'Recover',
    '全部覆盖': 'Overwrite all',
    '全部跳过': 'Skip all',
    '不保存': 'Do not save',
    '同步': 'Sync',
    '不同步': 'Do not sync',

    # ------------------------------------------------------------------
    #  菜单
    # ------------------------------------------------------------------
    '选择': 'Select',
    '文件': 'File',
    '编辑': 'Edit',
    '功能': 'Tools',
    '插件': 'Plugins',
    '搜索': 'Search',
    '统计': 'Statistics',
    '统计图': 'Charts',
    '查找替换': 'Find & replace',
    '多人日志': 'Online log',
    '多人日志管理': 'Online log manager',
    '导入/导出': 'Import/Export',
    '导出选中的日志': 'Export selected logs',
    '导出选中的日志为 F HamLog 项目文件': 'Export selected as F HamLog project',
    '导出选中的日志为ADI': 'Export selected as ADI',
    '导出选中的日志为表格': 'Export selected as spreadsheet',
    '导出ADI文件': 'Export ADI file',
    '导出为表格': 'Export as spreadsheet',
    '从 F HamLog 导入日志': 'Import from F HamLog',
    '从 旧版 HAM个人工具 导入日志': 'Import from HAM tools (legacy)',
    '从ADI导入日志': 'Import from ADI',
    '批量记录': 'Batch entry',
    '通联日志': 'QSO log',
    '卫星过境': 'Satellite passes',
    '通联预测': 'QSO prediction',
    '卫星地图': 'Satellite map',
    '设置': 'Settings',
    '插件设置': 'Plugin settings',
    '从其他版本导入数据': 'Import old data',
    '加密此项目': 'Encrypt this project',
    '不再加密此项目': 'Do not encrypt again',
    '按时间排序': 'Sort by time',
    '标记点管理': 'Manage markers',
    '编辑 TQSL/LoTW 映射': 'Edit TQSL/LoTW mapping',
    '编辑卫星转发器': 'Edit satellite transponder',
    '新建日志': 'New log',
    '新建项目': 'New project',
    '打开项目': 'Open project',
    '更多信息': 'More info',
    '星历数据源': 'Ephemeris sources',
    '卫星通联记录': 'Satellite QSOs',

    # ------------------------------------------------------------------
    #  主窗口 / 设置窗口
    # ------------------------------------------------------------------
    '业余无线电通联日志': 'Amateur Radio QSO Log',
    'F HamLog 版本：': 'F HamLog version: ',
    '我的呼号:': 'My call:',
    '我的QTH:': 'My QTH:',
    '我的设备:': 'My rig:',
    '观测站位置（纬度北纬为正，经度东经为正）：':
        'Station position (lat N+, lon E+):',
    '纬度(°):': 'Latitude (°):',
    '经度(°):': 'Longitude (°):',
    '海拔(m):': 'Altitude (m):',
    '坐标网:': 'Grid:',
    '网格:': 'Grid:',
    '梅登黑格网格': 'Maidenhead grid',
    '梅登黑格网格，如 PM84': 'Maidenhead grid, e.g. PM84',
    '自动保存': 'Auto save',
    '自动按时间排序': 'Auto sort',
    '星历自动更新': 'Auto TLE update',
    '更新间隔:': 'Every:',
    ' 小时': ' h',
    '颜色模式:': 'Theme:',
    '语言 Language:': '语言 Language:',
    '跟随系统': 'Follow system',
    '浅色': 'Light',
    '深色': 'Dark',

    # ------------------------------------------------------------------
    #  日志字段（表头）
    # ------------------------------------------------------------------
    '日期': 'Date',
    '时间': 'Time',
    '己方呼号': 'My call',
    '对方呼号': 'Other call',
    '频率': 'Freq',
    '调制模式': 'Mode',
    '传播模式': 'Prop',
    '传播方式': 'Prop',
    '卫星名称': 'Satellite',
    '卫星名': 'Satellite',
    '卫星显示名': 'Display name',
    '己方接收信号': 'My RST',
    '对方接收信号': 'Other RST',
    '己方QTH': 'My QTH',
    '对方QTH': 'Other QTH',
    '己方设备': 'My rig',
    '对方设备': 'Other rig',
    '己方功率': 'My pwr',
    '对方功率': 'Other pwr',
    '己方天线': 'My ant',
    '对方天线': 'Other ant',
    '接收频率': 'RX freq',
    '下行频率': 'Downlink',
    '上行频率': 'Uplink',
    '备注': 'Note',
    '更多': 'More',
    '模板': 'Template',
    '项目': 'Item',
    '内容': 'Value',
    '名称': 'Name',
    '版本': 'Version',
    '开发者': 'Developer',
    '简介': 'Description',
    '颜色': 'Color',
    '纬度': 'Latitude',
    '经度': 'Longitude',
    '网格': 'Grid',
    '模式': 'Mode',
    '次数': 'Count',

    # ------------------------------------------------------------------
    #  搜索 / 统计
    # ------------------------------------------------------------------
    '全部通联记录': 'All QSOs',
    '全部搜索结果': 'All search results',
    '仅选中的行': 'Selected rows only',
    '完全匹配': 'Exact match',
    '包含': 'Contains',
    '条形图': 'Bar chart',
    '扇形图': 'Pie chart',
    '关键词：': 'Keyword:',
    '范围：': 'Range:',
    '查找：': 'Find:',
    '替换为：': 'Replace with:',
    '匹配方式：': 'Match:',
    '图表类型：': 'Chart type:',
    '字段：': 'Field:',
    '显示:': 'Show:',
    '固定模板列': 'Freeze template column',
    '使用卫星编号搜索': 'Search by NORAD ID',
    '搜索卫星名…': 'Search satellite name…',
    '搜索卫星名或编号…': 'Search satellite name or ID…',
    '第一列为模板（默认值，可留空）；新增日志列时，日期/时间为空则自动填充当前时间。':
        'The first column is the template (default value, may be empty). When adding a log '
        'column, an empty date/time is filled with the current time.',
    '每行一条记录。点击单元格可直接编辑；用“添加”新增，“删除选中”移除整行；完成后点“保存”写回文件。':
        'One record per row. Click a cell to edit; use "Add" to insert and "Delete selected" '
        'to remove a row; click "Save" to write back to the file.',
    '双击某行即可编辑；更改后点「保存」写入文件。':
        'Double-click a row to edit; click "Save" to write changes to the file.',
    '第{}条': 'Log {}',
    '{} - 多人日志已断开': '{} - online log disconnected',
    'F HamLog 2 - 多人日志（{}） {}:{}': 'F HamLog 2 - Online log ({}) {}:{}',
    'F HamLog 2 - 通联日志': 'F HamLog 2 - QSO log',
    'F HamLog 2 - 恢复的项目': 'F HamLog 2 - Recovered project',
    '批量记录 - {}': 'Batch entry - {}',

    # ------------------------------------------------------------------
    #  卫星 / 过境 / 地图
    # ------------------------------------------------------------------
    '观测站位置': 'Station position',
    '选择卫星': 'Select satellites',
    '选择的卫星过多': 'Too many satellites selected',
    '选择的卫星过多。': 'Too many satellites selected.',
    '预测参数': 'Prediction parameters',
    '预测时长(小时):': 'Prediction span (h):',
    '轨迹时长(小时):': 'Track span (h):',
    '最低仰角:': 'Min elevation:',
    '最低仰角(°):': 'Min elevation (°):',
    '最低仰角(本台):': 'Min elevation (local):',
    '对方最低仰角:': 'Min elevation (remote):',
    '最多显示的卫星:': 'Max satellites shown:',
    '台站 A（本站）': 'Station A (local)',
    '台站 B（对方）': 'Station B (remote)',
    '地面轨迹': 'Ground track',
    '覆盖区': 'Footprint',
    '晨昏线': 'Terminator',
    '星历更新时间：—': 'Ephemeris updated: —',
    '星历更新时间：尚未获取': 'Ephemeris updated: not yet',
    '星历更新时间：{}': 'Ephemeris updated: {}',
    '数据与设置': 'Data & settings',
    '已连接的设备': 'Connected devices',
    '轨迹时长：最长 {} 小时': 'Track span: at most {} h',
    '预测时长：最长 {} 小时（10 天）': 'Prediction span: at most {} h (10 days)',
    '选择卫星：最多 {} 颗': 'Select satellites: at most {}',
    '方位(升起→落下)': 'Azimuth (rise→set)',
    '升起(本地)': 'Rise (local)',
    '落下(本地)': 'Set (local)',
    '最佳时刻(本地)': 'Best time (local)',
    '可通联开始(本地)': 'Window start (local)',
    '可通联结束(本地)': 'Window end (local)',
    '可通联时长': 'Window duration',
    '时长': 'Duration',
    '最大仰角': 'Max el.',
    'A最大仰角': 'Max el. A',
    'B最大仰角': 'Max el. B',
    'LoTW 认可名': 'LoTW name',
    '本台': 'Local',
    '对方台': 'Remote',
    '可见': 'visible',
    '不可见': 'not visible',
    '（无）': '(none)',
    '（空）': '(empty)',
    '<空>': '<empty>',
    '（截断）': '(truncated)',
    '{}（服务端）': '{} (server)',
    '轨迹 {} → {} ({} h)': 'Track {} → {} ({} h)',
    '显示 {}/{} 颗': 'Showing {}/{}',
    '显示 {}/{} 颗（还有 {} 颗未显示，可调大「最多显示的卫星」）':
        'Showing {}/{} ({} not shown; increase "Max satellites shown")',
    '{}: 纬 {}° 经 {}° 高 {} km': '{}: lat {}° lon {}° alt {} km',
    '其中 {} 条未能在当前星历中找到对应卫星，已按输入的名称原文保存（不会丢失）。':
        '{} of them could not be matched to a satellite in the current '
        'ephemeris; kept under the name as entered (no data lost).',
    '全部已选卫星 ({})': 'All selected satellites ({})',
    '，本台仰角 {}°（{}）': ', local elevation {}° ({})',
    '，对方仰角 {}°（{}）': ', remote elevation {}° ({})',
    '… 其余 {} 颗': '… {} more',
    '（可尝试降低最低仰角或延长预测时长）':
        ' (try lowering the minimum elevation or extending the prediction span)',
    '（另保留 {} 颗本次未取得的旧卫星）':
        ' ({} old satellites not in this download kept)',
    '{} ｜ 卫星 {} 颗 ｜ 可见过境 {} 次':
        '{} | Satellites: {} | Visible passes: {}',
    '{}　已选 {} 颗': '{}  Selected {}',
    '{}　已选 {} 颗，超过上限 {} 颗': '{}  Selected {}, over the limit of {}',
    '{} ｜ 已选 {} 颗': '{} | Selected {}',
    '，超过上限 {} 颗': ', over the limit of {}',
    '匹配 {} / 共 {} 颗': 'Matched {} / {}',
    '共 {} 颗': '{} total',
    'A 纬{}° 经{}°（≥{}°） ｜ B 纬{}° 经{}°（≥{}°） ｜ 地面距离 {} km ｜ 卫星 {} 颗 ｜ 可通联窗口 {} 个 ｜ 累计 {}':
        'A lat {}° lon {}° (≥{}°) | B lat {}° lon {}° (≥{}°) | ground distance {} km | '
        '{} satellites | {} mutual windows | total {}',
    '{}分': '{} min',
    '{}分{}秒': '{} min {} s',
    '{}时{}分': '{} h {} min',
    '{}秒': '{} s',
    '在线用户：0': 'Online: 0',
    '在线用户：{}': 'Online: {}',
    '在线用户：': 'Online: ',
    '（暂无其他用户）': '(no other users)',
    '（未启用加密）': '(encryption off)',
    '密钥指纹：': 'Key fingerprint:',
    '密钥字符串': 'Key string',
    '局域网地址：': 'LAN address:',
    '服务端：': 'Server: ',
    '服务端：{}:{}': 'Server: {}:{}',
    '状态：未连接': 'Status: not connected',
    '状态：客户端 {}:{}': 'Status: client {}:{}',
    '状态：服务端 {}:{}': 'Status: server {}:{}',
    '密码（可留空）': 'Password (optional)',
    '服务端地址（IP 或域名）': 'Server address (IP or domain)',
    '端口：': 'Port: ',
    '服务端': 'Server',
    '端口': 'Port',
    '密码': 'Password',
    '请输入加密密钥：': 'Enter encryption key:',
    '输入加密密钥': 'Enter encryption key',
    '设置观测站': 'Set up station',
    '默认取“观测站设置”里的本站位置，可临时修改。':
        'Defaults to the local station position from "Station setup"; can be changed '
        'temporarily.',
    '填写对方 QTH：可直接填经纬度或梅登黑格网格，编辑完成后自动同步。':
        'Remote QTH: enter coordinates or a Maidenhead grid; it syncs after you finish editing.',

    # ------------------------------------------------------------------
    #  对话框标题
    # ------------------------------------------------------------------
    '提示': 'Notice',
    '输入错误': 'Invalid input',
    '格式错误': 'Invalid format',
    '保存失败': 'Save failed',
    '导出失败': 'Export failed',
    '导出成功': 'Export complete',
    '导入失败': 'Import failed',
    '导入完成': 'Import complete',
    '读取失败': 'Read failed',
    '删除失败': 'Delete failed',
    '清空失败': 'Clear failed',
    '加密失败': 'Encryption failed',
    '解密失败': 'Decryption failed',
    '加密项目': 'Encrypt project',
    '解密项目': 'Decrypt project',
    '加密成功！\n请重新打开此项目。': 'Encrypted.\nPlease reopen this project.',
    '解密成功！\n请重新打开此项目。': 'Decrypted.\nPlease reopen this project.',
    '加入失败': 'Join failed',
    '开放失败': 'Host failed',
    '同步失败': 'Sync failed',
    '排序失败': 'Sort failed',
    '排序完成': 'Sorted',
    '按时间排序完成。': 'Sorted by time.',
    '安装失败': 'Install failed',
    '安装成功': 'Installed',
    '运行成功': 'Completed',
    '缺少依赖': 'Missing dependency',
    '插件错误': 'Plugin error',
    '版本不匹配': 'Version mismatch',
    '转换失败': 'Conversion failed',
    '部分坐标无效': 'Some coordinates invalid',
    '网格无效': 'Invalid grid',
    '密钥错误！': 'Wrong key!',
    '无可保存数据': 'Nothing to save',
    '已保存': 'Saved',
    '保存成功！': 'Saved!',
    '另存成功！': 'Saved!',
    '已复制': 'Copied',
    '已保存恢复的内容。': 'Recovered content saved.',
    '恢复未保存的内容': 'Recover unsaved changes',
    '检测到上次有未保存的更改，是否恢复？':
        'Unsaved changes from last time were found. Recover them?',
    '未保存的更改': 'Unsaved changes',
    '当前窗口有未保存的更改，是否保存？': 'This window has unsaved changes. Save them?',
    '有内容尚未同步到服务端，是否立即同步？':
        'Some content has not been synced to the server. Sync now?',
    '未同步到服务端': 'Not synced to server',
    '确认删除': 'Confirm delete',
    '确认清除': 'Confirm clear',
    '结束多人日志': 'End online log session',
    '多人日志已断开': 'Online log disconnected',
    '与多人日志服务端的连接已断开，之后的修改将不再同步到服务端。\n需要继续同步请重新加入多人日志。':
        'The connection to the online log server was lost. Further changes will not be '
        'synced.\nTo keep syncing, join the online log again.',
    '服务端身份核对': 'Verify server identity',
    '搜索结果': 'Search results',
    '搜索结果：{}': 'Search results: {}',
    '删除星历数据源': 'Remove ephemeris source',
    '清空星历': 'Clear ephemeris',
    '恢复默认数据源': 'Restore default sources',
    '从梅登黑格坐标导入': 'Import from Maidenhead coordinates',
    '检测到重复记录': 'Duplicate records found',
    'TQSL 映射提醒': 'TQSL mapping reminder',
    '确定删除插件：{} ?': 'Remove plugin {} ?',
    '已安装的插件': 'Installed plugins',

    # ------------------------------------------------------------------
    #  文件对话框标题 / 过滤器
    # ------------------------------------------------------------------
    '选择 F HamLog 项目文件': 'Select F HamLog project file',
    'F HamLog项目 (*.fhl)': 'F HamLog project (*.fhl)',
    'F HamLog项目 (*.fhl);;All Files (*)': 'F HamLog project (*.fhl);;All Files (*)',
    '另存为 F HamLog项目': 'Save as F HamLog project',
    '添加到 F HamLog项目': 'Add to F HamLog project',
    '导出选中日志为FHL文件': 'Export selected logs to FHL file',
    '导出搜索结果为FHL文件': 'Export search results to FHL file',
    '保存恢复的文件': 'Save recovered file',
    '另存为文件': 'Save as file',
    '选择 ADI/ADIF 文件': 'Select ADI/ADIF file',
    'ADI 文件 (*.adi);;All Files (*)': 'ADI file (*.adi);;All Files (*)',
    '导出 ADIF (TQSL/LoTW)': 'Export ADIF (TQSL/LoTW)',
    '导出 ADIF 文件 (TQSL/LoTW)': 'Export ADIF file (TQSL/LoTW)',
    '选择Excel文件': 'Select Excel file',
    'Excel文件 (*.xlsx *.xls)': 'Excel file (*.xlsx *.xls)',
    '导出为Excel文件': 'Export to Excel file',
    'Excel文件 (*.xlsx);;所有文件 (*)': 'Excel file (*.xlsx);;All files (*)',
    '选择插件包': 'Select plugin package',
    'F HamLog插件包 (*.fhlpypack *.txt);;All Files (*)':
        'F HamLog plugin package (*.fhlpypack *.txt);;All Files (*)',
    '星历文件 (*.tle *.txt *.csv);;TLE 文件 (*.tle);;CSV 文件 (*.csv);;文本文件 (*.txt)':
        'Ephemeris file (*.tle *.txt *.csv);;TLE file (*.tle);;CSV file (*.csv);;'
        'Text file (*.txt)',
    '导入卫星星历数据': 'Import satellite ephemeris',
    '选择之前版本 F HamLog.exe 所在的文件夹':
        'Select the folder containing the previous F HamLog.exe',

    # ------------------------------------------------------------------
    #  校验 / 错误提示
    # ------------------------------------------------------------------
    '观测站经纬度/海拔请填写数字。': 'Station latitude/longitude/altitude must be numbers.',
    '请先填写有效的经纬度数字。': 'Please enter valid latitude/longitude numbers.',
    '两个台站的经纬度/海拔必须都是有效数字。':
        'Both stations need valid latitude/longitude/altitude numbers.',
    '请输入有效的数字。': 'Please enter a valid number.',
    '请输入服务端地址。': 'Please enter the server address.',
    '请输入关键词。': 'Please enter a keyword.',
    '请输入查找内容。': 'Please enter what to find.',
    '请选择之前版本 F HamLog.exe 所在的文件夹！':
        'Please select the folder containing the previous F HamLog.exe!',
    '对方呼号为空，无法打开 QRZ。': 'Other call is empty; cannot open QRZ.',
    '梅登黑格坐标前两位应为字母（A–R）': 'The first two grid characters must be letters (A–R)',
    '梅登黑格坐标的偶数位应为数字': 'Even-position grid characters must be digits',
    '梅登黑格坐标的子格位应为字母': 'Grid sub-square characters must be letters',
    '梅登黑格坐标至少需 4 位，例如 PM84':
        'A Maidenhead locator needs at least 4 characters, e.g. PM84',
    '日期格式错误，应为YYYY-MM-DD': 'Invalid date, expected YYYY-MM-DD',
    '时间格式错误，应为HH:MM': 'Invalid time, expected HH:MM',
    '{} 日期格式错误，应为YYYY-MM-DD': 'Invalid date, expected YYYY-MM-DD',
    '{} 时间格式错误，应为HH:MM': 'Invalid time, expected HH:MM',
    '缺少 {} (必填)': 'Missing {} (required)',
    ' (必填)': ' (required)',
    '地址不能为空。': 'Address cannot be empty.',
    '地址格式不正确': 'Invalid address format',
    '地址需以 http:// 或 https:// 开头。': 'Address must start with http:// or https://',
    '该地址已在列表中。': 'That address is already in the list.',
    '未从文件中解析到有效的 TLE 数据。': 'No valid TLE data found in the file.',
    '以下行无法解析，已跳过：\n': 'The following lines could not be parsed and were skipped:\n',
    '没有可保存的记录。': 'No records to save.',
    '没有可保存的记录（日志列均为空）。': 'No records to save (all log columns are empty).',
    '没有任何有效（键不为空）的记录。': 'No valid records (all keys are empty).',
    '没有可导出的记录。': 'No records to export.',
    '没有可导出的搜索结果。': 'No search results to export.',
    '当前没有可导出的日志。': 'No logs to export.',
    '请先勾选要导出的日志行。': 'Please tick the log rows to export.',
    '请先勾选或选中要复制的行。': 'Please tick or select rows to copy.',
    '请先勾选要复制的行。': 'Please tick rows to copy.',
    '剪贴板为空或不是文本。': 'The clipboard is empty or not text.',
    '剪贴板内容无法识别为日志数据。': 'Clipboard content is not recognized as log data.',
    '没有可撤销的操作。': 'Nothing to undo.',
    '没有可重做的操作。': 'Nothing to redo.',
    '没有可统计的数据。': 'No data to chart.',
    '没有找到匹配的记录。': 'No matching records found.',
    '未找到任何匹配记录。': 'No matching records found.',
    '所选文件中没有可导入的日志记录。': 'No importable log records in the selected file.',
    '请先选中要删除的数据源。': 'Please select the source to delete.',
    '请先选中要删除的日志列（模板列不可删除）。':
        'Please select the log column to delete (the template column cannot be deleted).',
    '请先在表格里点击选中一颗卫星所在的行。':
        'Please click the row of a satellite in the table first.',
    '请先在表格里选中一行。': 'Please select a row in the table first.',
    '请先刷新星历。': 'Please refresh the ephemeris first.',
    '没有可用的卫星数据，请先“刷新星历”。':
        'No satellite data available. Please "Refresh ephemeris" first.',
    '当前未加载日志表。': 'The log table is not loaded.',
    '主窗口日志表尚未就绪，无法定位。': 'The main log table is not ready; cannot locate.',
    '未设置记录回调，无法自动添加到项目。':
        'No record callback configured; cannot add to the project automatically.',
    '尚未选择卫星，请点击“选择卫星…”勾选。':
        'No satellites selected yet. Click "Select satellites…".',
    '尚未选择卫星，请点击“选择卫星…”勾选要跟踪的卫星。':
        'No satellites selected yet. Click "Select satellites…" to choose ones to track.',
    '至少需要保留一个数据源。': 'At least one data source must be kept.',
    '未修改：至少需要保留一个启用的数据源。':
        'Not applied: at least one data source must stay enabled.',
    '设置中保存的自选卫星已超过上限。': 'The satellites saved in settings exceed the limit.',
    '所有星历数据源都已禁用，请在「设置 → 星历数据源」中至少启用一个数据源。':
        'All ephemeris sources are disabled. Enable at least one in '
        '"Settings → Ephemeris sources".',
    '全部星历数据源都下载失败。': 'All ephemeris sources failed to download.',
    '星历数据源返回了空的卫星 TLE 数据。': 'The ephemeris source returned empty TLE data.',
    '用户取消了星历下载': 'Ephemeris download cancelled by user',
    '未选择卫星（请在来源窗口刷新星历或选择卫星）':
        'No satellite selected (refresh the ephemeris or pick one in the source window)',
    '应用运行失败，请检查权限！': 'The application failed to run. Check permissions!',
    '已取消星历下载。': 'Ephemeris download cancelled.',
    '已取消连接：未通过服务端身份核对。':
        'Connection cancelled: server identity not verified.',
    '登录失败：密码错误或服务端拒绝连接。':
        'Login failed: wrong password or the server refused the connection.',
    '服务端未响应。': 'The server did not respond.',
    '服务端响应异常，无法建立连接。': 'Unexpected server response; cannot connect.',
    '获取日志数据失败。': 'Failed to get log data.',
    '缺少第三方库 skyfield，请先安装：pip install skyfield numpy':
        'Missing library skyfield. Install it first: pip install skyfield numpy',
    '未安装 matplotlib，请运行: pip install matplotlib':
        'matplotlib is not installed. Run: pip install matplotlib',
    '星历已清空，自选卫星的选择已保留；点击「刷新星历」重新下载。':
        'Ephemeris cleared; your satellite selection was kept. Click "Refresh ephemeris" '
        'to download again.',

    # ------------------------------------------------------------------
    #  状态 / 进度
    # ------------------------------------------------------------------
    '准备中…': 'Preparing…',
    '测试中…': 'Testing…',
    '正在自动测试各数据源延迟…': 'Testing data source latency…',
    '正在下载数据源 {}/{}：{}': 'Downloading source {}/{}: {}',
    '正在合并 {} 个数据源…': 'Merging {} data sources…',
    '正在写入星历缓存…': 'Writing ephemeris cache…',
    '正在获取业余卫星星历…': 'Fetching amateur satellite ephemeris…',
    '正在获取全部活动卫星星历…': 'Fetching all active satellite ephemeris…',
    '正在计算过境… {}%': 'Computing passes… {}%',
    '正在计算过境（{} 颗卫星）…': 'Computing passes ({} satellites)…',
    '正在计算过境（{} 颗卫星，跨度 {} 小时，可能较慢）…':
        'Computing passes ({} satellites, {} h span, may be slow)…',
    '正在计算两地可通联窗口… {}%': 'Computing mutual windows… {}%',
    '正在计算两地可通联窗口（{} 颗卫星，跨度 {} 小时{}）…':
        'Computing mutual windows ({} satellites, {} h span{})…',
    '，可能较慢': ', may be slow',
    '下载星历…': 'Downloading ephemeris…',
    '下载星历 %p%': 'Downloading ephemeris %p%',
    '开始时间无效：{}': 'Invalid start time: {}',
    '开始时间格式无效：{}': 'Invalid start time format: {}',
    '已保存 {} 条记录。': 'Saved {} record(s).',
    '已导入 {} 颗卫星：更新 {} 颗、新增 {} 颗，当前共 {} 颗。':
        'Imported {} satellites: {} updated, {} added, {} total now.',
    '已保存：{} 个数据源（{} 个已启用）': 'Saved: {} sources ({} enabled)',
    '未修改：{}': 'Not applied: {}',
    '延迟测试完成：{} 个数据源中 {} 个无法访问。':
        'Latency test done: {} of {} sources unreachable.',
    '延迟测试完成：{} 个数据源均可访问{}。':
        'Latency test done: all {} sources reachable{}.',
    '，最快 {} ms': ', fastest {} ms',
    '已更新星历：本次取得 {} 颗，共 {} 颗卫星{}。':
        'Ephemeris updated: got {} satellites, {} in total{}.',
    '已载入星历，共 {} 颗卫星。请填写两个台站的位置（坐标或网格）后自动开始预测。':
        'Ephemeris loaded with {} satellites. Fill in both station positions (coordinates or '
        'grid) to start prediction automatically.',
    '已载入星历：本次取得 {} 颗，共 {} 颗卫星{}。':
        'Ephemeris loaded: got {} satellites, {} in total{}.',
    'UTC {}   |   本地 {} ({})': 'UTC {}   |   local {} ({})',
    '按列表顺序读取已启用的数据源；同一颗卫星（按 NORAD 编号）以先出现的为准。\n左侧方框为启用开关；双击地址即可编辑（回车确认、Esc 取消）。\n打开本窗口或改完地址会自动测试各源延迟，无需手动操作；点「保存」后写入：{}':
        'Enabled sources are read in list order; for the same satellite (by NORAD ID) the '
        'earlier one wins.\nThe left checkbox enables/disables a source; double-click an '
        'address to edit (Enter to confirm, Esc to cancel).\nOpening this window or editing '
        'an address tests latency automatically; click "Save" to write to: {}',

    # ------------------------------------------------------------------
    #  结果提示 / 确认
    # ------------------------------------------------------------------
    '已删除 {} 条日志。': 'Deleted {} log(s).',
    '已删除 1 条日志。': 'Deleted 1 log.',
    '已复制 {} 条日志到剪贴板。': 'Copied {} log(s) to the clipboard.',
    '已粘贴 {} 条日志。': 'Pasted {} log(s).',
    '已添加 {} 条记录到当前项目。': 'Added {} record(s) to the current project.',
    '已添加 {} 条记录到项目。': 'Added {} record(s) to the project.',
    '已添加 {} 条记录到默认通联日志': 'Added {} record(s) to the default log',
    '已添加 {} 条记录到多人日志（{}:{}）。': 'Added {} record(s) to the online log ({}:{}).',
    '已保存到服务端！': 'Saved to the server!',
    '已保存到服务端，多人日志已关闭。': 'Saved to the server; online log closed.',
    '无法保存到服务端：{}': 'Cannot save to the server: {}',
    '已成功录入 {} 条记录，请选择保存方式：':
        '{} record(s) entered. Choose how to save:',
    '检测到 {} 条导入记录与现有记录重复。请选择处理方式：':
        '{} imported record(s) duplicate existing ones. Choose how to handle them:',
    '已导出 {} 条记录到：\n{}\n\n可用 TQSL 打开该 ADIF 文件进行签名，再上传到 LoTW。':
        'Exported {} record(s) to:\n{}\n\nYou can open the ADIF file in TQSL to sign it, '
        'then upload to LoTW.',
    '已另存为项目文件：{}': 'Saved as project file: {}',
    '已安装到：{}': 'Installed to: {}',
    '成功导入{}\n（目前不支持从之前版本中导入插件）':
        'Imported{}\n(importing plugins from older versions is not supported)',
    '用户设置': 'user settings',
    '问题反馈到：BI8SQL@outlook.com': 'Report issues to: BI8SQL@outlook.com',
    '版本更新请访问：': 'For updates visit: ',
    'Github项目：': 'GitHub project: ',
    '、通联日志文件': ', QSO log file',
    '、卫星转发器表': ', satellite transponder table',
    '、TQSL映射表': ', TQSL mapping table',
    '、卫星地图标记点': ', satellite map markers',
    '、星历数据源': ', ephemeris sources',
    '、卫星数据缓存': ', satellite data cache',
    '、多人日志缓存': ', online log cache',
    '替换完成：影响 {} 条记录，共 {} 处替换。':
        'Replaced: {} record(s), {} occurrence(s) in total.',
    '安装程序运行成功！\n安装完成后，请重新打开插件设置。':
        'Installer finished successfully!\nPlease reopen Plugin settings.',
    '安装失败：{}': 'Installation failed: {}',
    '插件 {} 未正确生成输出文件！': 'Plugin {} did not produce an output file!',
    '该插件与当前F HamLog版本不兼容\n当前F HamLog版本：2.6.0\n插件适配版本：{}':
        'This plugin is incompatible with the current F HamLog version\n'
        'Current F HamLog version: 2.6.0\nPlugin targets: {}',
    'F HamLog 将使用AES加密项目，\n请牢记你的密钥！若密钥丢失则无法恢复日志数据。':
        'F HamLog will encrypt the project with AES.\nRemember your key! A lost key means '
        'unrecoverable log data.',
    'F HamLog 会将项目解密后提供给插件，\n请确保插件来自可信的开发者。':
        'F HamLog will decrypt the project before handing it to the plugin.\n'
        'Only use plugins from trusted developers.',
    'Python 未安装，\n为正常使用插件需安装 Python3.13.11\n是否安装？':
        'Python is not installed.\nPython 3.13.11 is required for plugins.\nInstall it?',
    '未安装Python': 'Python not installed',
    '未安装插件，请前往 设置 安装插件':
        'No plugin installed. Go to Settings to install one.',
    '无法连接到服务端 {}:{}（{}）': 'Cannot connect to server {}:{} ({})',
    '无法连接服务端：{}': 'Cannot connect to the server: {}',
    '无法连接本机服务端：{}': 'Cannot connect to the local server: {}',
    '无法启动服务端：{}': 'Cannot start the server: {}',
    '无法启动与服务端的同步：{}': 'Cannot start syncing with the server: {}',
    '无法加载多人日志客户端：{}': 'Cannot load the online log client: {}',
    '写入文件失败：\n{}': 'Failed to write the file:\n{}',
    '保存失败：{}': 'Save failed: {}',
    '添加失败：{}': 'Add failed: {}',
    '删除失败：{}': 'Delete failed: {}',
    '导入 ADI 失败：{}': 'ADI import failed: {}',
    '导出过程中发生错误：\n{}': 'An error occurred during export:\n{}',
    '导出 ADIF 时出错: ': 'Error exporting ADIF: ',
    '添加到项目失败：\n{}': 'Failed to add to the project:\n{}',
    '请检查密钥是否正确。\n错误信息：{}': 'Please check whether the key is correct.\nError: {}',
    '请检查密钥是否正确。': 'Please check whether the key is correct.',
    '密钥交换失败：{}': 'Key exchange failed: {}',
    '服务端公钥无效：{}': 'Invalid server public key: {}',
    '服务端密钥指纹与上次记录不一致！':
        'The server key fingerprint differs from the one recorded last time!',
    '收到无法解密的帧（{}）：{}': 'Received an undecryptable frame ({}): {}',
    '下载失败，使用本地缓存（{} 颗）：{}':
        'Download failed; using local cache ({} satellites): {}',
    '无法下载 TLE 且没有本地缓存：\n{}': 'Cannot download TLE and no local cache:\n{}',
    '无法获取全部活动卫星星历：\n{}': 'Cannot fetch ephemeris for all active satellites:\n{}',
    '无法删除星历缓存文件：{}': 'Cannot delete the ephemeris cache file: {}',
    '无法读取文件：{}': 'Cannot read the file: {}',
    '写入文件出错：{}': 'Error writing the file: {}',
    '当前项目窗口正作为多人日志{}（{}）。\n打开新窗口会结束这个会话，其他用户将无法再与之同步日志。\n\n是否继续？':
        'The current project window is the online log {} ({}).\nOpening a new window will end '
        'this session and other users will no longer sync with it.\n\nContinue?',
    '将把数据源恢复为内置默认（Celestrak 全部活动卫星），当前列表中的自定义地址会被清除（保存后才会写入文件）。是否继续？':
        'This restores the built-in default sources (Celestrak all active satellites). '
        'Custom addresses in the list will be cleared (written to file only after saving). '
        'Continue?',
    '确定清空本地星历吗？\n\n将删除本地星历缓存并清空当前卫星列表；\n自选卫星的选择保留，之后可用「刷新星历」重新下载。':
        'Clear the local ephemeris?\n\nThis deletes the local ephemeris cache and clears the '
        'current satellite list.\nYour satellite selection is kept; use "Refresh ephemeris" '
        'to download again.',
    '卫星「{}」未找到 TQSL / LoTW 名称映射，\n记录将以原始名称「{}」保存，可能不会被 LoTW / TQSL 正确识别。\n可在「卫星过境预测」窗口的「编辑TQSL映射」中补充。':
        'No TQSL / LoTW name mapping found for satellite "{}".\nThe record will be saved with '
        'the original name "{}" and may not be recognized correctly by LoTW / TQSL.\nYou can '
        'add the mapping via "Edit TQSL mapping" in the pass prediction window.',
    '卫星「{}」未找到 TQSL / LoTW 名称映射，\n记录将以原始名称「{}」保存，可能不会被 LoTW / TQSL 正确识别。\n可点击工具栏「编辑TQSL映射」补充该卫星的映射。':
        'No TQSL / LoTW name mapping found for satellite "{}".\nThe record will be saved with '
        'the original name "{}" and may not be recognized correctly by LoTW / TQSL.\nClick '
        '"Edit TQSL mapping" on the toolbar to add the mapping.',
    '加密传输已启用：客户端加入时请核对上面这串指纹。':
        'Encrypted transport is on: verify the fingerprint above when clients join.',
    '勾选下方记录，选择结果会自动同步到主页面的选择框（Ctrl+A 全选 / Ctrl+I 反选 / Ctrl+D 取消选择）':
        'Tick records below; the selection syncs to the main window automatically '
        '(Ctrl+A select all / Ctrl+I invert / Ctrl+D clear)',
    '勾选要参与过境预测的卫星（可搜索筛选）：':
        'Tick the satellites to include in pass prediction (searchable):',
    '每行一个梅登黑格坐标（4 / 6 / 8 位均可，大小写不限），如：\n  PM84\n  EM12ab\n也可写「名称 坐标」（空格分隔），如：\n  北京 PM84':
        'One Maidenhead locator per line (4 / 6 / 8 characters, any case), e.g.:\n  PM84\n  '
        'EM12ab\nYou can also write "name locator" separated by a space, e.g.:\n  Beijing PM84',
    '快捷键：Ctrl+←/→ 上一条/下一条 · Ctrl+N 新建 · Ctrl+D 删除 · Ctrl+Z 撤销 · Ctrl+Y 重做 · Ctrl+S 完成':
        'Shortcuts: Ctrl+←/→ previous/next · Ctrl+N new · Ctrl+D delete · Ctrl+Z undo · '
        'Ctrl+Y redo · Ctrl+S done',
    '台站 B（对方）尚未设置位置，请填写对方 QTH 或网格后自动开始预测。':
        'Station B (remote) has no position yet. Fill in the remote QTH or grid to start '
        'prediction automatically.',
    '这是首次连接该服务端，请向服务端持有者核对下面这串指纹。\n核对通过后会被记住，以后同一地址自动校验。':
        'This is the first connection to this server. Verify the fingerprint below with the '
        'server owner.\nOnce confirmed it is remembered and checked automatically.',
    '这可能意味着服务端重装/更换了机器（正常），\n也可能是局域网内有人冒名顶替（中间人攻击）。\n\n请向服务端持有者当面确认下面这串指纹后再继续。':
        'This may mean the server was reinstalled or replaced (normal),\nor that someone on '
        'the LAN is impersonating it (man-in-the-middle attack).\n\nConfirm the fingerprint '
        'below with the server owner before continuing.',
    '尚未设置观测站位置。\n请在弹出的对话框中填写你的 QTH 经纬度与海拔，否则过境预测不准确。':
        'Station position not set yet.\nFill in your QTH latitude/longitude and altitude in '
        'the dialog, otherwise pass predictions will be inaccurate.',

    # ------------------------------------------------------------------
    #  杂项（标题后缀 / 提示 / 表格小字）
    # ------------------------------------------------------------------
    '{} 统计': '{} Statistics',
    '{} 缺少 {} (必填)': '{} missing {} (required)',
    '{}: 坐标超出地球范围（经纬度无效）': '{}: out of Earth range (invalid lat/lon)',
    '不可用': 'N/A',
    '全部已选卫星': 'All satellites selected',
    '删除日志列': 'Delete log column',
    '添加日志列': 'Add log column',
    '卫星': 'Satellite',
    '完成': 'Done',
    '客户端': 'Client',
    '密码：': 'Password: ',
    '开始时间:': 'Start time:',
    '星历更新时间：': 'Ephemeris updated: ',
    '星历获取失败': 'Ephemeris fetch failed',
    '暂无卫星': 'No satellites',
    '标记点 {}': 'Marker {}',
    '记录': 'Record',
    '超时': 'Timeout',
    '连接失败': 'Connection failed',
    '尚未测试': 'Not tested',
    '已修改': 'Modified',
    '已修改启用状态': 'Enable state changed',
    '已删除': 'Deleted',
    '已恢复默认': 'Defaults restored',
    '已调整顺序': 'Order changed',
    '新建文件': 'New file',
    '清除所有选择': 'Clear all selections',
    '重新选择': 'Select again',
    '编辑单元格': 'Edit cell',
    '自选卫星': 'Selected satellites',
    '纬度(°) 北纬为正:': 'Latitude (°), north positive:',
    '经度(°) 东经为正:': 'Longitude (°), east positive:',
    '观测站: 纬{}° 经{}° 海拔{}m': 'Station: lat {}° lon {}° alt {} m',
    '梅登黑格网格，如 {}': 'Maidenhead grid, e.g. {}',
    '{}（未保存，点「保存」写入文件）': '{} (unsaved; click "Save" to write)',
    '格式：卫星名=': 'Format: satellite name=',
    '格式：卫星显示名=': 'Format: satellite display name=',
    '格式：卫星编号(NORAD ID)=': 'Format: satellite NORAD ID=',
    '格式：显示名=': 'Format: display name=',
    '安装失败！\n错误信息：{}': 'Installation failed!\nError: {}',
    '导出 ADIF 时出错: {}': 'Error exporting ADIF: {}',
    '导出过程中发生错误：{}': 'An error occurred during export: {}',
    '已导出 {} 条记录到：\n{}': 'Exported {} record(s) to:\n{}',
    '将清除全部 {} 颗已选卫星，回到未选择状态，并重新打开选择窗口。是否继续？':
        'This will clear all {} selected satellites and reopen the selection window. Continue?',
    '已勾选 {} 颗，单次最多支持 {} 颗。\n请减少勾选后再确定，或清除全部已选卫星重新挑选。':
        '{} selected, at most {} allowed.\nDeselect some, or clear all selections and pick '
        'again.',
    '没有可删除的日志：请先在“选择”列勾选要删除的行，或直接选中（高亮）这些行。':
        'Nothing to delete: tick rows in the "Sel." column, or select (highlight) them '
        'directly.',
    '格式应为 YYYY-MM-DD HH:MM（例如 2026-07-27 17:45），可带秒；当前输入：{}':
        'Expected YYYY-MM-DD HH:MM (e.g. 2026-07-27 17:45), seconds allowed; current input: {}',
    '格式应为 YYYY-MM-DD HH:MM（例如 2026-08-02 17:45），当前输入：{}':
        'Expected YYYY-MM-DD HH:MM (e.g. 2026-08-02 17:45), current input: {}',
    'ADIF 文件 (*.adi);;All Files (*)': 'ADIF file (*.adi);;All Files (*)',
    'YYYY-MM-DD HH:MM（如 2026-07-27 17:45）': 'YYYY-MM-DD HH:MM (e.g. 2026-07-27 17:45)',
}
