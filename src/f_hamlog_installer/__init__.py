# -*- coding: utf-8 -*-
"""F HamLog 安装器 —— 独立的小工具，复用主程序「自动更新」的那条链路。

做三件事：

1. **装最新版**：从 GitHub Releases 找出最新正式版，用 ``f_hamlog.check_update``
   的下载器（16 线程动态分块 + 镜像择优 + 抽样比对）把安装包拉下来，再调
   ``/SILENT`` 静默安装 —— 与主程序「设置 → 检查更新 → 下载并安装」完全同一条路。
2. **收全历史版本**：把 Releases 页面上所有版本的安装包按
   ``<输出目录>/<版本号>/<文件名>`` 排好，附一份 ``manifest.json`` 记大小、摘要、
   来源地址；重复运行只补缺的，不全量重下。
3. **自带 GitHub 加速**：安装包下载走 ``check_update`` 里的镜像择优；版本列表走
   api.github.com，同样支持镜像前缀回退（直连不通时自动换），并把列表缓存到本地，
   省掉未登录 GitHub 每小时只有 60 次的接口额度。

命令行入口：``python -m f_hamlog_installer``（装进环境后是 ``f-hamlog-installer``）。
本包**不 import Qt**，可以在纯控制台里跑，也能单独用 Nuitka 打成 exe。
"""

__version__ = "1.0.0"
