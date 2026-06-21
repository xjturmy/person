"""市场 Tab · ① 康波周期定位卡(静态 yaml 驱动)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import _load_kondratieff


def _section_kondratieff_card() -> None:
    kdf = _load_kondratieff()
    if not kdf:
        st.caption("⚠️ 康波周期 yaml 缺失:.tools/dashboard/data/kondratieff.yaml")
        return

    cycle = kdf.get("cycle", "—")
    phase = kdf.get("phase", "—")
    phase_range = kdf.get("phase_range", "—")
    phase_emoji = kdf.get("phase_emoji", "🟡")
    conflicts = kdf.get("core_conflicts", [])
    strategy = kdf.get("strategy_summary", "")
    key_node = kdf.get("key_node", {}) or {}
    last_updated = kdf.get("last_updated", "—")

    with st.container(border=True):
        st.markdown(
            f"#### {phase_emoji} {cycle} · **{phase}** ({phase_range})"
        )
        if conflicts:
            for line in conflicts:
                st.markdown(f"- {line}")
        if strategy:
            st.markdown(f"**📌 策略**:{strategy}")
        if key_node.get("date"):
            st.markdown(
                f"**⏰ 关键节点**:{key_node['date']} — {key_node.get('description', '')}"
            )

        with st.expander("📚 完整四阶段时间表 + 数据源", expanded=False):
            phases = kdf.get("phases_table", [])
            if phases:
                pdf = pd.DataFrame(phases)
                if "current" in pdf.columns:
                    pdf["current"] = pdf["current"].fillna(False).map(
                        lambda v: "✅ 当前" if v else ""
                    )
                st.dataframe(pdf, hide_index=True, use_container_width=True)
            st.caption(
                f"📅 数据更新:{last_updated} · "
                f"📖 来源:{kdf.get('source_md', '—')}"
            )
