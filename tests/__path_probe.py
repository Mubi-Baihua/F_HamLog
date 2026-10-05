import re
import collections

t = open("main.build/scons-debug.py", encoding="utf-8", errors="replace").read()

# 统计构建目录里记录的绝对路径前缀
paths = collections.Counter(re.findall(r"[A-Za-z]:\\\\[^'\"]{0,90}", t))
print("scons-debug.py 中记录的绝对路径（去重后前 8 条）:")
for p, c in list(paths.items())[:8]:
    print(f"  x{c:2d}  {p[:100]}")

print()
print("含本机仓库路径 'F-Dev\\BIG\\F_HamLog' 的出现次数:", t.count("F-Dev"))
print("含 CI 路径特征 '\\\\a\\\\' (D:\\a\\...) 的次数:", t.count("\\a\\"))
