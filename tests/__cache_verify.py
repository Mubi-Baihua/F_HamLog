import yaml
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
lines = []
ok = True

def log(s=""):
    lines.append(s)
    print(s)

def good(s):
    log("  ✓ " + s)

def fail(s):
    global ok
    ok = False
    log("  ✗ " + s)

log("=" * 78)
log("一、YAML 解析")
log("=" * 78)
docs = {}
for n in ("main.yml", "preview.yml"):
    p = Path(".github/workflows") / n
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        docs[n] = d
        good(f"{n} 解析成功")
    except Exception as e:
        fail(f"{n} 解析失败: {e}")

log("")
log("=" * 78)
log("二、main.build 缓存键：两边必须不同，且 restore-keys 不跨名")
log("=" * 78)

def build_cache(n):
    d = docs[n]
    for s in d["jobs"][list(d["jobs"])[0]]["steps"]:
        if s.get("name") == "缓存 Nuitka 构建目录":
            return s["with"]
    return None

m = build_cache("main.yml")
p = build_cache("preview.yml")

log(f"main.yml    key = {m['key']}")
log(f"            rk  = {m['restore-keys'].strip()}")
log(f"preview.yml key = {p['key']}")
log(f"            rk  = {p['restore-keys'].strip()}")
log("")

# 1) key 必须含 exe 名
if "app_exe_name" in m["key"]:
    good("main.yml key 含 exe 名（app_exe_name）")
else:
    fail("main.yml key 缺 exe 名")

if "APP_EXE_NAME" in p["key"]:
    good("preview.yml key 含 exe 名（APP_EXE_NAME）")
else:
    fail("preview.yml key 缺 exe 名")

# 2) restore-keys 不得有跨名的宽松回退
for label, cfg, exe_var in (("main.yml", m, "app_exe_name"), ("preview.yml", p, "APP_EXE_NAME")):
    rks = [r.strip() for r in cfg["restore-keys"].strip().splitlines() if r.strip()]
    bad = [r for r in rks if exe_var not in r]
    if bad:
        fail(f"{label} 存在跨 exe 名的 restore-keys（会捞到对方构建目录）: {bad}")
    else:
        good(f"{label} 的 restore-keys 全部限定了 exe 名，无跨名回退")

# 3) 模拟展开，确认不撞
RUNNER, PY, HASH = "Windows", "3.13", "H"
mk = f"{RUNNER}-nuitka-build-{PY}-F HamLog 2-{HASH}"
pk = f"{RUNNER}-nuitka-build-{PY}-F HamLog 2 Preview-{HASH}"
log("")
log(f"展开示例 main    : {mk}")
log(f"展开示例 preview : {pk}")
if mk != pk:
    good("两键展开后不同（不会互相作废）")
else:
    fail("两键展开后相同！")

# 4) 前缀匹配模拟：确认各自 restore 只捞自己
log("")
log("前缀匹配模拟（源码变动后各自恢复上一份）：")
existing = [
    f"{RUNNER}-nuitka-build-{PY}-F HamLog 2-OLDH",
    f"{RUNNER}-nuitka-build-{PY}-F HamLog 2 Preview-OLDH",
]
for label, rk, want in (
    ("main.yml", f"{RUNNER}-nuitka-build-{PY}-F HamLog 2-", "F HamLog 2-OLDH"),
    ("preview.yml", f"{RUNNER}-nuitka-build-{PY}-F HamLog 2 Preview-", "F HamLog 2 Preview-OLDH"),
):
    hits = [k for k in existing if k.startswith(rk)]
    got = hits[0] if hits else None
    if got and got.endswith(want):
        good(f"{label} 只命中自己: {got}")
    elif got:
        fail(f"{label} 串到了: {got}")
    else:
        # 注意 "F HamLog 2-" 也会前缀匹配 "F HamLog 2 Preview-..."
        # 但因为 preview 键里 exe 名写在 python 版本之后，需检查真实匹配
        fail(f"{label} 未命中任何缓存")

log("")
log("=" * 78)
log("三、run 步骤 PowerShell 语法")
log("=" * 78)
for n, d in docs.items():
    for i, s in enumerate(d["jobs"][list(d["jobs"])[0]]["steps"], 1):
        r = s.get("run")
        if not isinstance(r, str) or not r.strip():
            continue
        tmp = ROOT / "__parse_tmp.ps1"
        tmp.write_text(r, encoding="utf-8-sig")
        cmd = (
            "$t=$null;$e=$null;"
            f"$r=[System.Management.Automation.Language.Parser]::ParseFile('{tmp}',[ref]$t,[ref]$e);"
            "if($e -and $e.Count -gt 0){$e|%{Write-Output ('ERR: '+$_.Message)}}else{Write-Output 'OK'}"
        )
        rr = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (rr.stdout or "").strip()
        if "OK" in out and "ERR" not in out:
            good(f"{n} step{i} OK")
        else:
            fail(f"{n} step{i}: {out}")
        tmp.unlink(missing_ok=True)

log("")
log("=" * 78)
log("结论：" + ("全部通过" if ok else "存在失败项"))
log("=" * 78)

Path("__cache_verify_out.txt").write_text("\n".join(lines), encoding="utf-8")
