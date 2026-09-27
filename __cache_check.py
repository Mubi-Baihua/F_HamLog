import yaml
from pathlib import Path

def cache_keys(n):
    d = yaml.safe_load((Path(".github/workflows") / n).read_text(encoding="utf-8"))
    steps = d["jobs"][list(d["jobs"])[0]]["steps"]
    out = []
    for s in steps:
        if str(s.get("uses", "")).startswith("actions/cache"):
            out.append((s.get("name"), s["with"].get("key")))
    return out

main = cache_keys("main.yml")
prev = cache_keys("preview.yml")

print("=" * 78)
print("逐字符比对缓存键")
print("=" * 78)
for (n1, k1), (n2, k2) in zip(main, prev):
    same = k1 == k2
    print(f"{'SAME' if same else 'DIFF'}  {n1}")
    print(f"        main    : {k1}")
    print(f"        preview : {k2}")

print()
print("=" * 78)
print("关键差异定位：${{ inputs.python_version }} vs ${{ env.PYTHON_VERSION }}")
print("=" * 78)
# 两边实际会展开成什么值
main_py = "3.13"   # inputs.python_version 的 default
prev_py = "3.13"   # env.PYTHON_VERSION
print(f"main.yml    inputs.python_version 默认值 = {main_py!r}  → 键里是 '3.13'")
print(f"preview.yml env.PYTHON_VERSION         = {prev_py!r}  → 键里是 '3.13'")
print(f"展开后是否同键: {main_py == prev_py}")

print()
print("=" * 78)
print("缓存路径比对")
print("=" * 78)
def cache_paths(n):
    d = yaml.safe_load((Path(".github/workflows") / n).read_text(encoding="utf-8"))
    steps = d["jobs"][list(d["jobs"])[0]]["steps"]
    return [(s["with"].get("path")) for s in steps if str(s.get("uses","")).startswith("actions/cache")]
print("main.yml    :", cache_paths("main.yml"))
print("preview.yml :", cache_paths("preview.yml"))
print("路径集合相同:", cache_paths("main.yml") == cache_paths("preview.yml"))
