# -*- coding: utf-8 -*-
"""校验 i18n 词表：
1) 重复键（同一字面量在 dict 里写了多次）
2) 键里残留 % 格式化占位符（应为 {} 形式）
3) 词表里有、但源码中找不到（疑似写错/形状不对）
4) 源码里的界面中文，词表还没收（漏收，仅提示）
结果打印到 stdout。
"""
import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

CJK = re.compile(r'[\u4e00-\u9fff]')
PLACEHOLDER = re.compile(r'\{\}|\{\d+\}|\{[A-Za-z_][A-Za-z0-9_]*\}')

FILES = [
    'main.py', 'set.py', 'project.py', 'batch_project.py', 'satellite_window.py',
    'satellite_map_window.py', 'mutual_window.py', 'tle_source_window.py',
    'pack_set.py', 'input_fhl.py', 'input_adi.py', 'input_HAM_tolls.py',
    'output_adi.py', 'output_excel.py', 'export_adi.py', 'backup.py',
    'fhl_rw.py', 'toast_tip.py', 'theme.py', 'satellite_pred.py',
    'satellite_auto_update.py', 'call_upper.py',
]


def catalog_keys():
    src = io.open(os.path.join(ROOT, 'i18n_zh_en.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    keys = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and \
           any(getattr(t, 'id', '') == 'TRANSLATIONS' for t in node.targets):
            for k in node.value.keys:
                keys.append((k.value, k.lineno))
    return keys


def _template_of(node):
    """把「字符串常量 / f-string / 若干段拼接」折叠成一个 {} 模板；不是字符串则 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(v.value)
            else:
                parts.append('{}')
        return ''.join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _template_of(node.left)
        right = _template_of(node.right)
        if left is None or right is None:
            return None
        return left + right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ('str', 'repr'):
        return '{}' if node.args else None
    return None


def source_strings():
    """源码里所有含中文的「完整文案」（拼接后的形状，f-string 组装为 {} 模板）。"""
    out = {}
    for fn in FILES:
        path = os.path.join(ROOT, fn)
        if not os.path.exists(path):
            continue
        tree = ast.parse(io.open(path, encoding='utf-8').read())
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, 'body', None)
                if body and isinstance(body[0], ast.Expr) and \
                   isinstance(body[0].value, ast.Constant) and \
                   isinstance(body[0].value.value, str):
                    docs.add(id(body[0].value))
        parents = {}
        for n in ast.walk(tree):
            for ch in ast.iter_child_nodes(n):
                parents[id(ch)] = n
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and id(n) in docs:
                continue
            p = parents.get(id(n))
            if isinstance(p, ast.JoinedStr):
                continue
            # 常量：若父级是可折叠的字符串拼接，则由父级统一记录
            if isinstance(n, ast.Constant) and isinstance(p, ast.BinOp) \
                    and isinstance(p.op, ast.Add) and _template_of(p) is not None:
                continue
            t = _template_of(n)
            if t and CJK.search(t):
                out.setdefault(t, fn)
    return out


def norm_percent(s):
    """把 %s/%d/%.2f/%% 归一成 {}（用于和词表形状比对）。"""
    s = re.sub(r'%%', '%', s)
    s = re.sub(r'%[-+ 0#]*\d*(?:\.\d+)?[diufFeEgGsxXr]', '{}', s)
    return s


def main():
    keys = catalog_keys()
    seen = {}
    dups = []
    for k, ln in keys:
        if k in seen:
            dups.append((k, seen[k], ln))
        seen[k] = ln

    src = source_strings()
    src_norm = {}
    for s, fn in src.items():
        src_norm.setdefault(s, fn)
        src_norm.setdefault(norm_percent(s), fn)

    print('词表条目数:', len(keys), ' 去重后:', len(seen))
    if dups:
        print('\n[重复键] %d 处：' % len(dups))
        for k, l1, l2 in dups:
            print('  L%-5d L%-5d %s' % (l1, l2, k.replace('\n', '\\n')[:70]))

    # %p% 是 Qt 进度条占位符，不算问题
    pct = [(k, l) for k, l in keys
           if re.search(r'%[-+ 0#]*\d*(?:\.\d+)?[diufFeEgGsxXr%]', k.replace('%p%', ''))]
    if pct:
        print('\n[键里残留 %% 占位符] %d 处：' % len(pct))
        for k, l in pct:
            print('  L%-5d %s' % (l, k.replace('\n', '\\n')[:80]))

    missing = [(k, l) for k, l in keys if k not in src_norm]
    if missing:
        print('\n[词表里有、源码里找不到] %d 处：' % len(missing))
        for k, l in missing:
            print('  L%-5d %s' % (l, k.replace('\n', '\\n')[:80]))

    not_covered = [s for s in src if s not in seen and norm_percent(s) not in seen]
    print('\n[源码里的中文串未收录] %d 条：' % len(not_covered))
    for s in sorted(not_covered):
        print('   %s' % s.replace('\n', ' / ')[:100])


if __name__ == '__main__':
    main()
