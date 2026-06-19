"""Streamlit dataframe / data_editor 列头菜单中文化.

Streamlit 1.x 的列菜单文案(排序/固定/隐藏等)目前为英文硬编码,
通过 parent document 上的 MutationObserver 在菜单弹出时替换为中文。
"""
from __future__ import annotations

import streamlit.components.v1 as components

_MENU_ZH = {
    "Sort ascending": "升序排序",
    "Sort descending": "降序排序",
    "Autosize": "自动列宽",
    "Pin column": "固定列",
    "Unpin column": "取消固定",
    "Hide column": "隐藏列",
    "Show all columns": "显示全部列",
    "Clear sort": "清除排序",
    "Reset columns": "重置列",
}

_INJECTED_KEY = "_dataframe_menu_zh_injected"


def inject_zh_column_menu() -> None:
    """在整页注入一次列菜单中文化脚本(幂等)。"""
    import streamlit as st

    if st.session_state.get(_INJECTED_KEY):
        return
    st.session_state[_INJECTED_KEY] = True

    mapping_js = ",\n".join(
        f'"{k}": "{v}"' for k, v in _MENU_ZH.items()
    )
    components.html(
        f"""
        <script>
        (function () {{
          const MAP = {{
            {mapping_js}
          }};
          const doc = window.parent.document;
          if (!doc || doc.__presonDfMenuZh) return;
          doc.__presonDfMenuZh = true;

          function patchNode(node) {{
            if (!node || node.nodeType !== Node.TEXT_NODE) return;
            let text = node.textContent;
            for (const [en, zh] of Object.entries(MAP)) {{
              if (text.includes(en)) {{
                text = text.replace(en, zh);
              }}
            }}
            if (text !== node.textContent) node.textContent = text;
          }}

          function patchMenus() {{
            doc.querySelectorAll('[role="menuitem"]').forEach((el) => {{
              el.childNodes.forEach(patchNode);
            }});
          }}

          const obs = new MutationObserver(patchMenus);
          obs.observe(doc.body, {{ childList: true, subtree: true }});
          patchMenus();
        }})();
        </script>
        """,
        height=0,
        width=0,
    )
