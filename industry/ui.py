"""V5.2.1 Industry views — panorama map + market landscape (no nested tabs)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Sequence

import pandas as pd
import streamlit as st

from industry.loader import (
    load_accelerator_ecosystem,
    load_meta,
    market_share_rows,
    normalize_watchlist_tickers,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
)

_PANORAMA = Path(__file__).resolve().parent.parent / "assets" / "ai_industry_panorama.jpg"


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


def _share_block(market: str, title: str) -> None:
    st.markdown(f"**{title}**")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据")
        return
    out = []
    for r in rows:
        share = r.get("share_pct")
        out.append(
            {
                "Company": r.get("company"),
                "Share": (
                    f"{float(share):.1f}%"
                    if share is not None
                    else (r.get("tier") or r.get("leader_status") or "Not separately disclosed")
                ),
                "Previous": f"{float(r['previous_share_pct']):.1f}%" if r.get("previous_share_pct") is not None else "—",
                "Change": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "Rank": r.get("rank") if r.get("rank") is not None else "—",
            }
        )
    st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)


def render_tab_landscape(watch: List[str]) -> None:
    """市场格局 — watchlist-gated Cloud / Memory / Compute modules."""
    if not watch:
        _empty_watchlist_message()
        return
    any_mod = False
    if show_cloud_module(watch):
        any_mod = True
        _share_block("cloud_infrastructure", "Cloud")
    if show_memory_module(watch):
        any_mod = True
        _share_block("dram", "Memory · DRAM")
        _share_block("hbm", "Memory · HBM")
    if show_compute_module(watch):
        any_mod = True
        st.markdown("**AI Compute / Networking**")
        eco = load_accelerator_ecosystem()
        rows = []
        for row in eco:
            rows.append(
                {
                    "Name": row.get("name"),
                    "Role": row.get("product"),
                    "External / Internal": (
                        "External"
                        if row.get("external_market")
                        else ("Internal" if row.get("internal_only") else "Cloud-specific")
                    ),
                    "Revenue status": row.get("current_revenue_status"),
                }
            )
        if any(t in {"ANET", "AVGO", "NVDA"} for t in watch):
            rows.append(
                {
                    "Name": "Arista Networks",
                    "Role": "Data-center / AI cluster networking",
                    "External / Internal": "External",
                    "Revenue status": "Networking equipment revenue",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
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
