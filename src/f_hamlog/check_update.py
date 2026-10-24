# -*- coding: utf-8 -*-
from f_hamlog import __version__
import time
import urllib.error
import urllib.request

check_url = "https://mubi-baihua.pages.dev/f_hamlog_check_update.txt"

# 必须用浏览器 UA：Cloudflare 会直接 403 掉 "Python-urllib/x.y"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

TIMEOUT = 10        # 单次请求超时（秒）
MAX_RETRIES = 5     # 失败后最多重试 5 次（首次不算，合计最多 6 次请求）
MAX_BACKOFF = 5.0   # 单次重试等待上限（秒）

# 这些状态码「再试也一样」，直接放弃，不浪费 5 次重试
PERMANENT_CODES = (400, 401, 404, 410, 451)


def get_text(retry=0):
    """取版本信息文本。失败后最多重试 MAX_RETRIES 次，全失败返回 None。

    retry 只是内部计数器，外部调用不用传。
    用 while 循环而不是递归：递归在次数判断写错时会变成无限深，
    且栈溢出后还会被 except 吞掉继续递归。
    """
    err = None
    while True:
        try:
            req = urllib.request.Request(check_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                text = r.read().decode('utf-8', errors='replace').strip()
            #print(text)
            return text

        except urllib.error.HTTPError as e:
            err = e
            if e.code in PERMANENT_CODES:
                print('检查更新失败：%s' % e)
                return 'e'

        except Exception as e:          # URLError / 超时 / 连接重置 / SSL
            err = e

        if retry >= MAX_RETRIES:
            #print('检查更新失败（已重试 %d 次）：%s' % (retry, err))
            return 'e'

        retry += 1
        delay = min(0.5 * 2 ** (retry - 1), MAX_BACKOFF)   # 0.5/1/2/4/5
        print('[重试 %d/%d] %s，%.1f 秒后重试…' % (retry, MAX_RETRIES, err, delay))
        time.sleep(delay)

def main():
    if 'UTC' in __version__:
        return 'p'
    text = get_text()
    if text=='e':
        return 'e'
    version,down_url = text.split(' ')
    #print('version:',version,'down_url:',down_url,sep='\n')
    if version == __version__:
        return 'n'
    else:
        return (version,down_url)



if __name__ == "__main__":
    print(main())
