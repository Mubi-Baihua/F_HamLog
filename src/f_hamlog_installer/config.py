# -*- coding: utf-8 -*-
"""固定配置：仓库地址、接口地址、默认目录、环境变量名。

这里只放常量与「目录从哪来」的解析，不联网、不读文件内容。
"""

import os
import tempfile

REPO = 'Mubi-Baihua/F_HamLog'
REPO_URL = 'https://github.com/' + REPO
RELEASES_URL = REPO_URL + '/releases'
API_RELEASES = 'https://api.github.com/repos/%s/releases' % REPO

PER_PAGE = 100      # GitHub 单页上限
MAX_PAGES = 20      # 兜底：真到 2000 个版本就该换心思了

# 目录都能用环境变量改（无 admin 权限、绿色版、CI 里都用得上）
OUT_ENV = 'F_HAMLOG_RELEASES_DIR'       # 历史版本存放目录
CACHE_ENV = 'F_HAMLOG_INSTALLER_CACHE'  # 版本列表缓存目录
TOKEN_ENVS = ('GITHUB_TOKEN', 'GH_TOKEN')

CACHE_TTL = 600     # 10 分钟内的缓存直接用：未登录调 GitHub 接口只有 60 次/小时


def _local_appdata():
    """放数据的根目录：LOCALAPPDATA → APPDATA → 临时目录，逐级退。"""
    return (os.environ.get('LOCALAPPDATA')
            or os.environ.get('APPDATA')
            or tempfile.gettempdir())


def out_dir():
    """历史版本的存放目录。

    默认 ``%LOCALAPPDATA%/F_HamLog/releases``：和主程序的安装包缓存
    （``%LOCALAPPDATA%/F_HamLog/update``）同门不同屋，互不干扰。
    """
    env = os.environ.get(OUT_ENV)
    if env:
        return os.path.abspath(env)
    return os.path.join(_local_appdata(), 'F_HamLog', 'releases')


def cache_dir():
    """版本列表缓存目录（跟着安装器走，不占版本目录，免得被 --out 带跑）。"""
    env = os.environ.get(CACHE_ENV)
    if env:
        return os.path.abspath(env)
    return os.path.join(_local_appdata(), 'F_HamLog', 'installer', 'cache')


def token(explicit=None):
    """GitHub token：命令行 → GITHUB_TOKEN → GH_TOKEN，取到第一个就用。

    只读公开仓库的话不填也能用；填了能把接口额度从 60 次/小时提到 5000。
    """
    if explicit:
        return str(explicit).strip()
    for name in TOKEN_ENVS:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return ''
