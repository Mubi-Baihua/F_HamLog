# -*- coding: utf-8 -*-
"""扫描项目源码，抽出面向界面的中文字符串（f-string 组装为 {} 模板），
输出 TSV：次数 / 上下文 / 中文模板。结果写 test/__i18n_ui_out.txt（已被 .gitignore 的 `__*_out.txt` 覆盖）。

排除：文档字符串、以 # 开头的注释型配置头、纯打印/写文件路径等明显非界面串另作标记。
"""
import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CJK = re.compile(r'[\u4e00-\u9fff]')

FILES = [
    'main.py', 'set.py', 'project.py', 'batch_project.py', 'satellite_window.py',
    'satellite_map_window.py', 'mutual_window.py', 'tle_source_window.py',
    'pack_set.py', 'input_fhl.py', 'input_adi.py', 'input_HAM_tolls.py',
    'output_adi.py', 'output_excel.py', 'export_adi.py', 'backup.py',
    'fhl_rw.py', 'toast_tip.py', 'theme.py', 'satellite_pred.py',
    'satellite_auto_update.py', 'call_upper.py',
]

# 明显的非界面上下文（打印、写盘等）——仍列出但标注，便于人工取舍
NON_UI = {'print', 'write', 'writelines', 'dumps', 'dump', 'join',
          'assign:?', 'assign:fn', 'assign:DRIVER'}


def docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, 'body', None)
            if body and isinstance(body[0], ast.Expr) and \
               isinstance(body[0].value, ast.Constant) and \
               isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def call_name(parent, node):
    if isinstance(parent, ast.Call):
        f = parent.func
        name = getattr(f, 'attr', None) or getattr(f, 'id', None) or ''
        for kw in parent.keywords:
            if kw.value is node and kw.arg:
                return '%s(%s=)' % (name, kw.arg)
        return name
    if isinstance(parent, ast.keyword):
        return 'kw:%s' % parent.arg
    return type(parent).__name__


def joined_to_template(node):
    """ast.JoinedStr -> '...{}...' 模板字符串。"""
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(v.value)
        elif isinstance(v, ast.FormattedValue):
            parts.append('{}')
    return ''.join(parts)


def main():
    strings = {}
    for fn in FILES:
        path = os.path.join(ROOT, fn)
        if not os.path.exists(path):
            continue
        tree = ast.parse(io.open(path, 'r', encoding='utf-8').read())
        docs = docstrings(tree)
        parents = {}
        for n in ast.walk(tree):
            for ch in ast.iter_child_nodes(n):
                parents[id(ch)] = n
        for n in ast.walk(tree):
            text = None
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and id(n) not in docs:
                text = n.value
            elif isinstance(n, ast.JoinedStr):
                text = joined_to_template(n)
            if not text or not CJK.search(text):
                continue
            parent = parents.get(id(n))
            ctx = call_name(parent, n)
            # 忽略字符串里嵌套的代码片段（如 subprocess 引导串）
            if 'subprocess' in text or 'def ' in text and '\n' in text:
                continue
            rec = strings.setdefault(text, {'n': 0, 'ctx': set(), 'files': set()})
            rec['n'] += 1
            rec['ctx'].add(ctx)
            rec['files'].add(fn)

    out = io.open(os.path.join(ROOT, 'test', '__i18n_ui_out.txt'), 'w', encoding='utf-8')
    out.write('# unique=%d\n' % len(strings))
    out.write('# non_ui=1 表示只出现在 print/write 等非界面上下文\n')
    for s in sorted(strings, key=lambda x: (-strings[x]['n'], x)):
        r = strings[s]
        ui = 0 if r['ctx'] <= NON_UI else 1
        flat = s.replace('\\n', ' / ').replace('\n', ' / ').replace('\t', ' ')
        out.write('%d\t%d\t%s\t%s\n' % (ui, r['n'], ','.join(sorted(r['ctx'])[:5]), flat))
    out.close()
    print('unique:', len(strings))
    print('ui-like:', sum(1 for s in strings if not strings[s]['ctx'] <= NON_UI))


if __name__ == '__main__':
    sys.exit(main())
