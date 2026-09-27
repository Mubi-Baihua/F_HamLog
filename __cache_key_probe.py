import yaml
from pathlib import Path

def get(n):
    d = yaml.safe_load((Path(".github/workflows") / n).read_text(encoding="utf-8"))
    steps = d["jobs"][list(d["jobs"])[0]]["steps"]
    for s in steps:
        if s.get("name") == "缓存 Nuitka 构建目录":
            return s["with"]
    return None

m = get("main.yml")
p = get("preview.yml")

RUNNER = "Windows"
PY = "3.13"
MAIN_EXE = "F HamLog 2"          # inputs.app_exe_name 的默认值
PREV_EXE = "F HamLog 2 Preview"  # env.APP_EXE_NAME
SRC_HASH = "<源码哈希，两边相同>"

main_key = f"{RUNNER}-nuitka-build-{PY}-{MAIN_EXE}-{SRC_HASH}"
prev_key = f"{RUNNER}-nuitka-build-{PY}-{PREV_EXE}-{SRC_HASH}"

print("=" * 78)
print("main.build 缓存键展开后的实际值")
print("=" * 78)
print(f"main.yml    : {main_key}")
print(f"preview.yml : {prev_key}")
print()
print(f"两键是否相同: {main_key == prev_key}   <-- 必须为 False（否则又互相作废）")
print()

print("=" * 78)
print("restore-keys 前缀重叠分析（决定「跨次复用」是否成立）")
print("=" * 78)
print("main.yml 的 restore-keys 依次为：")
for r in [f"{RUNNER}-nuitka-build-{PY}-{MAIN_EXE}-",
          f"{RUNNER}-nuitka-build-{PY}-",
          f"{RUNNER}-nuitka-build-"]:
    print(f"    {r}")
print()
print("preview.yml 的 restore-keys 依次为：")
for r in [f"{RUNNER}-nuitka-build-{PY}-{PREV_EXE}-",
          f"{RUNNER}-nuitka-build-{PY}-",
          f"{RUNNER}-nuitka-build-"]:
    print(f"    {r}")
print()

print("=" * 78)
print("模拟：源码改动后（*.py 哈希变化）各自能否靠 restore-keys 命中上一份")
print("=" * 78)
OLD_HASH = "OLDHASH"
NEW_HASH = "NEWHASH"

# 假设缓存里已有上一次的精确键
existing = {
    f"{RUNNER}-nuitka-build-{PY}-{MAIN_EXE}-{OLD_HASH}": "main 上一份",
    f"{RUNNER}-nuitka-build-{PY}-{PREV_EXE}-{OLD_HASH}": "preview 上一份",
}

def pick(restore_keys, existing):
    """GitHub 按 restore-keys 顺序做前缀匹配，取最新的一个"""
    for rk in restore_keys:
        hits = [k for k in existing if k.startswith(rk)]
        if hits:
            return rk, hits[0]
    return None, None

for label, exe, keys in (
    ("main.yml（exe=F HamLog 2）", MAIN_EXE,
     [f"{RUNNER}-nuitka-build-{PY}-{MAIN_EXE}-", f"{RUNNER}-nuitka-build-{PY}-", f"{RUNNER}-nuitka-build-"]),
    ("preview.yml（exe=F HamLog 2 Preview）", PREV_EXE,
     [f"{RUNNER}-nuitka-build-{PY}-{PREV_EXE}-", f"{RUNNER}-nuitka-build-{PY}-", f"{RUNNER}-nuitka-build-"]),
):
    rk, hit = pick(keys, existing)
    print(f"  {label}")
    print(f"      命中前缀: {rk}")
    print(f"      命中缓存: {hit}")
    # 检查是否会串到对方
    if hit and (MAIN_EXE in hit) != (MAIN_EXE in label):
        print("      ⚠️ 串到了对方的构建目录！")
    else:
        print("      ✓ 只命中自己的构建目录，exe 名一致，不会全量重编")
    print()
