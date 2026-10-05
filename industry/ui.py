"""V5.2.1 Industry views — panorama map + compact market landscape."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Sequence

import pandas as pd
import streamlit as st

from industry.loader import (
    load_meta,
    market_share_rows,
    normalize_watchlist_tickers,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
)

_PANORAMA = Path(__file__).resolve().parent.parent / "assets" / "ai_industry_panorama.jpg"

# Presentation roles for AI Compute / Networking (no invented % shares)
_COMPUTE_ROLES = (
    ("NVDA", "AI accelerator"),
    ("AVGO", "networking/custom silicon"),
    ("ANET", "networking"),
    ("Google TPU", "internal/cloud"),
    ("AWS Trainium", "internal/cloud"),
)

# HBM qualitative roles when precise % unavailable
_HBM_ROLE_SHORT = {
    "SK hynix": "Leader",
    "Samsung": "Major supplier",
    "Micron": "Challenger",
}


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f}pp"


def _empty_watchlist_message() -> None:
    st.info("你的自选股目前为空。添加股票后，这里会按自选股显示相关市场格局。")


def render_tab_map(watch: List[str]) -> None:
    """产业链地图 — 仅展示 AI 产业链全景图。"""
    if not watch:
        _empty_watchlist_message()
    if not _PANORAMA.exists():
        st.error(f"未找到全景图：`{_PANORAMA}`")
        return
    st.image(str(_PANORAMA), use_container_width=True)


def _share_chart_and_table(market: str, title: str) -> None:
    """Cloud / DRAM: horizontal bar + short Company/Share/Change/Rank table."""
    st.markdown(f"**{title}**")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据")
        return

    numeric = [r for r in rows if r.get("share_pct") is not None]
    if numeric:
        cdf = pd.DataFrame(
            {
                "Company": [str(r.get("company") or "") for r in numeric],
                "Share": [float(r["share_pct"]) for r in numeric],
            }
        )
        try:
            st.bar_chart(cdf, x="Share", y="Company", horizontal=True, height=220)
        except TypeError:
            # Older Streamlit without horizontal=
            st.bar_chart(cdf.set_index("Company")["Share"], height=220)

    table_rows = []
    for r in rows:
        share = r.get("share_pct")
        table_rows.append(
            {
                "Company": r.get("company"),
                "Share": f"{float(share):.1f}%" if share is not None else (r.get("tier") or "—"),
                "Change": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "Rank": r.get("rank") if r.get("rank") is not None else "—",
            }
        )
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)


def _hbm_role_list() -> None:
    """HBM: qualitative roles only — no invented percentage table."""
    st.markdown("**Memory · HBM**")
    rows = market_share_rows("hbm")
    if not rows:
        # Fallback fixed presentation order from curated research notes
        for name, role in (
            ("SK hynix", "Leader"),
            ("Samsung", "Major supplier"),
            ("Micron", "Challenger"),
        ):
            st.markdown(f"**{name}** — {role}")
        return
    for r in sorted(rows, key=lambda x: (x.get("rank") is None, x.get("rank") or 99)):
        company = str(r.get("company") or "")
        if not company or company.lower() == "none":
            continue
        role = _HBM_ROLE_SHORT.get(company)
        if not role:
            raw = str(r.get("leader_status") or "")
            if "Leader" in raw or "#1" in raw:
                role = "Leader"
            elif "Major" in raw:
                role = "Major supplier"
            elif "challenger" in raw.lower() or "Challenger" in raw:
                role = "Challenger"
            else:
                role = raw or "—"
        st.markdown(f"**{company}** — {role}")


def _compute_role_list() -> None:
    """AI Compute / Networking as role lines — skip empty/None rows."""
    st.markdown("**AI Compute / Networking**")
    for name, role in _COMPUTE_ROLES:
        if not name or str(name).lower() == "none":
            continue
        if not role or str(role).lower() == "none":
            continue
        st.markdown(f"**{name}** — {role}")


def render_tab_landscape(watch: List[str]) -> None:
    """市场格局 — watchlist-gated modules; charts + role lists."""
    if not watch:
        _empty_watchlist_message()
        return
    any_mod = False
    if show_cloud_module(watch):
        any_mod = True
        _share_chart_and_table("cloud_infrastructure", "Cloud")
    if show_memory_module(watch):
        any_mod = True
        _share_chart_and_table("dram", "Memory · DRAM")
        _hbm_role_list()
    if show_compute_module(watch):
        any_mod = True
        _compute_role_list()
    if not any_mod:
        st.info("当前自选股暂无关联的 Cloud / Memory / AI Compute 市场格局模块。")


def _footer_meta() -> None:
    meta = load_meta()
    period = meta.get("data_through") or "—"
    refreshed = str(meta.get("last_refreshed_at") or "—")[:10]
    with st.expander("数据说明", expanded=False):
        st.caption(f"数据周期：{period} · 更新：{refreshed} · 研究用途")


def render_industry_page(
    valuation_loader: Optional[Any] = None,
    watchlist_tickers: Optional[Sequence[Any]] = None,
    mode: str = "map",
) -> None:
    """
    Industry views without nested secondary tabs.

    mode:
      - "map": 产业链地图（全景图）
      - "landscape": 市场格局
    """
    del valuation_loader
    watch = normalize_watchlist_tickers(watchlist_tickers)
    key = str(mode or "map").strip().lower()
    if key in {"landscape", "市场格局"}:
        render_tab_landscape(watch)
    else:
        render_tab_map(watch)
    _footer_meta()
