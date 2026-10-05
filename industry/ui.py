"""V5.2 Industry page — structure & market landscape only."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import streamlit as st

from industry.constants import LAYER_MAP_ORDER, LAYER_SHORT
from industry.loader import (
    companies_touching_layer,
    company_in_watchlist,
    display_ticker_for_company,
    load_accelerator_ecosystem,
    load_meta,
    market_share_rows,
    normalize_watchlist_tickers,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
    valuation_ticker_for,
    watchlist_keys,
)


def _open_stock(ticker: str) -> None:
    vt = valuation_ticker_for(ticker) or str(ticker).upper()
    st.session_state.selected_ticker = vt
    st.session_state._pending_nav_page = "单股分析"
    try:
        st.query_params["ticker"] = vt
    except Exception:
        pass
    st.rerun()


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f}pp"


def _empty_watchlist_message() -> None:
    st.info("你的自选股目前为空。添加股票后，这里会高亮你的产业位置。")


def render_tab_map(watch: List[str]) -> None:
    """产业链地图 — four layers, ticker/name only; watchlist highlighted."""
    if not watch:
        _empty_watchlist_message()
    keys = watchlist_keys(watch)

    for layer in LAYER_MAP_ORDER:
        label = LAYER_SHORT.get(layer, layer)
        st.markdown(f"**{label}**")
        companies = companies_touching_layer(layer)
        if not companies:
            st.caption("—")
            continue
        # Compact chip row: watchlist first (emphasized), then reference (muted)
        watch_cos = [c for c in companies if company_in_watchlist(c, keys)]
        ref_cos = [c for c in companies if not company_in_watchlist(c, keys)]
        chips: List[str] = []
        for c in watch_cos:
            t = display_ticker_for_company(c)
            chips.append(f"**{t}**")
        for c in ref_cos:
            t = display_ticker_for_company(c)
            chips.append(f'<span style="color:#888">{t}</span>')
        st.markdown(" · ".join(chips), unsafe_allow_html=True)

        # Clickable open — watchlist companies first
        openable = watch_cos + ref_cos
        labels = [display_ticker_for_company(c) for c in openable]
        if not labels:
            continue
        cols = st.columns(min(8, len(labels)))
        for i, lab in enumerate(labels):
            with cols[i % len(cols)]:
                if st.button(lab, key=f"ind_map_{layer}_{lab}", use_container_width=True):
                    _open_stock(lab)


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


def render_industry_page(
    valuation_loader: Optional[Any] = None,
    watchlist_tickers: Optional[Sequence[Any]] = None,
) -> None:
    """AI产业链 — only 产业链地图 / 市场格局."""
    del valuation_loader  # valuation lives on 自选股 / 单股分析
    watch = normalize_watchlist_tickers(watchlist_tickers)

    tabs = ["产业链地图", "市场格局"]
    if hasattr(st, "segmented_control"):
        tab = (
            st.segmented_control(
                "产业页签",
                tabs,
                default=tabs[0],
                key="ind_v52_tabs",
                label_visibility="collapsed",
            )
            or tabs[0]
        )
    else:
        tab = st.radio(
            "产业页签",
            tabs,
            horizontal=True,
            key="ind_v52_tabs",
            label_visibility="collapsed",
        )

    if tab == "产业链地图":
        render_tab_map(watch)
    else:
        render_tab_landscape(watch)

    meta = load_meta()
    period = meta.get("data_through") or "—"
    refreshed = str(meta.get("last_refreshed_at") or "—")[:10]
    with st.expander("数据说明", expanded=False):
        st.caption(f"数据周期：{period} · 更新：{refreshed} · 研究用途")
