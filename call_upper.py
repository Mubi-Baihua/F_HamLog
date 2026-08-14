"""呼号输入统一转大写的工具（统一方案）。

- UpperCallDelegate：用于 QTableWidget 中呼号行的单元格编辑
  （如「新建日志」「更多信息」「批量记录」里的己方/对方呼号）。
- connect_callsign_upper：用于 QLineEdit（如「搜索」「查找替换」「设置-我的呼号」），
  仅当 field_getter() 返回的字段是呼号时才实时转大写；
  若希望始终转大写（如设置里的“我的呼号”），可传入恒定字段名。

使用方式：
    import call_upper
    delegate = call_upper.UpperCallDelegate()
    table.setItemDelegateForRow(2, delegate)   # 己方呼号行
    table.setItemDelegateForRow(3, delegate)   # 对方呼号行
    table._upper_call_delegate = delegate       # 保持引用，防止被回收

    call_upper.connect_callsign_upper(edit, lambda: combo.currentData())
"""
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit

# 需要强制大写的字段（己方呼号 / 对方呼号）
CALL_FIELDS = ('m_call', 'o_call')


def _upper_in_place(editor, text):
    """把编辑器里的文本原地转成大写，并尽量保持光标位置。"""
    up = text.upper()
    if up != text:
        pos = editor.cursorPosition()
        editor.setText(up)
        editor.setCursorPosition(pos)


class UpperCallDelegate(QStyledItemDelegate):
    """单元格编辑器（QLineEdit）实时转大写的委托。"""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        # 编辑时实时转大写；其余行不使用本委托，不受影响
        editor.textChanged.connect(lambda text: _upper_in_place(editor, text))
        return editor


def connect_callsign_upper(edit, field_getter):
    """让 QLineEdit 在“当前字段为呼号”时实时转大写。

    field_getter 返回一个字段名（如 'm_call' / 'o_call'）。
    若希望该输入框始终转大写，可传入 lambda: 'm_call'。
    """
    def handler(text):
        if field_getter() in CALL_FIELDS:
            _upper_in_place(edit, text)
    edit.textChanged.connect(handler)
