"""Streamlit dataframe / data_editor 列头菜单中文化.

Streamlit 1.x 列菜单(排序/固定/隐藏等)为英文硬编码;
在页面注入 MutationObserver,菜单弹出时替换为中文。
"""
from __future__ import annotations

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
    "Filter": "筛选",
    "Group": "分组",
    "Copy": "复制",
    "Download as CSV": "下载 CSV",
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
    st.markdown(
        f"""
        <script>
        (function () {{
          const MAP = {{
            {mapping_js}
          }};
          const doc = document;
          if (doc.__presonDfMenuZh) return;
          doc.__presonDfMenuZh = true;

          function patchText(text) {{
            let out = text;
            for (const [en, zh] of Object.entries(MAP)) {{
              if (out.includes(en)) out = out.split(en).join(zh);
            }}
            return out;
          }}

          function patchEl(el) {{
            if (!el) return;
            if (el.childNodes.length === 1 && el.childNodes[0].nodeType === Node.TEXT_NODE) {{
              const next = patchText(el.textContent || "");
              if (next !== el.textContent) el.textContent = next;
              return;
            }}
            el.childNodes.forEach((node) => {{
              if (node.nodeType === Node.TEXT_NODE) {{
                const next = patchText(node.textContent || "");
                if (next !== node.textContent) node.textContent = next;
              }}
            }});
          }}

          function patchMenus(root) {{
            (root || doc).querySelectorAll('[role="menuitem"], [data-baseweb="menu"] li').forEach(patchEl);
          }}

          const obs = new MutationObserver((mutations) => {{
            for (const m of mutations) {{
              if (m.type !== 'childList') continue;
              m.addedNodes.forEach((node) => {{
                if (node.nodeType !== Node.ELEMENT_NODE) return;
                if (node.getAttribute && node.getAttribute('role') === 'menuitem') {{
                  patchEl(node);
                }}
                if (node.querySelectorAll) patchMenus(node);
              }});
            }}
          }});
          obs.observe(doc.body, {{ childList: true, subtree: true }});
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )
