"""Single-ticker industry panels for Single-Stock Analysis (V5.2)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from industry.constants import LAYER_SHORT
from industry.loader import (
    events_for,
    insight_for,
    latest_earnings,
    load_accelerator_ecosystem,
    market_share_rows,
    resolve_company,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
    trend_label,
)


def _money(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(x) >= 1e9:
        return f"${x / 1e9:.1f}B"
    if abs(x) >= 1e6:
        return f"${x / 1e6:.0f}M"
    return f"${x:,.0f}"


def _pct(v: Any, *, signed: bool = False, digits: int = 0) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(x) <= 1.5 and x != 0:
        x *= 100.0
    if signed:
        return f"{x:+.{digits}f}%"
    return f"{x:.{digits}f}%"


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f}pp"


def render_earnings_panel(ticker: str) -> None:
    """财报与业务 — moved from AI Industry「收入与盈利」."""
    c = resolve_company(ticker)
    earn = latest_earnings(ticker)
    if not c:
        st.caption("暂无产业分类数据")
    if not earn:
        st.info("暂无季度财报快照。")
        return

    st.caption(f"{ticker} · {earn.get('fiscal_period')} · {earn.get('report_date')}")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Revenue", _money(earn.get("total_revenue")))
    m2.metric("YoY", _pct(earn.get("revenue_growth_yoy"), signed=True))
    m3.metric("Operating Income", _money(earn.get("operating_income")))
    m4.metric("Operating Margin", _pct(earn.get("operating_margin")))
    m5.metric("FCF", _money(earn.get("free_cash_flow")))
    m6.metric("CapEx", _money(earn.get("capex")))
    if earn.get("capex_as_pct_revenue") is not None:
        st.caption(f"CapEx / Revenue：{_pct(earn.get('capex_as_pct_revenue'))}")

    segs = earn.get("segments") or []
    if segs:
        st.markdown("**Revenue Mix**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Segment": s.get("name"),
                        "Revenue": _money(s.get("revenue")),
                        "%": s.get("percentage_of_total"),
                        "YoY": _pct(s.get("yoy_growth"), signed=True),
                    }
                    for s in segs
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    e1, e2 = st.columns(2)
    with e1:
        st.caption("Current Profit Engine")
        st.write((c or {}).get("main_revenue_engine") or "—")
        cur = (c or {}).get("current_profit_layers") or []
        if cur:
            st.caption("、".join(LAYER_SHORT.get(x, x) for x in cur))
    with e2:
        st.caption("Future Expansion")
        st.write((c or {}).get("next_expansion") or "—")
        fut = (c or {}).get("future_expansion_layers") or []
        if fut:
            st.caption("、".join(LAYER_SHORT.get(x, x) for x in fut))


def _share_block(market: str, title: str, *, company_filter: Optional[set] = None) -> None:
    st.markdown(f"**{title}**")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据")
        return
    out = []
    for r in rows:
        company = str(r.get("company") or "")
        if company_filter:
            # Keep full market table for context, but title is company-relevant
            pass
        share = r.get("share_pct")
        out.append(
            {
                "Company": company,
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


def render_position_panel(ticker: str) -> None:
    """行业地位 — company-relevant modules only."""
    watch = [str(ticker or "").upper()]
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
        rows: List[Dict[str, Any]] = []
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
        t = watch[0]
        if t in {"ANET", "AVGO", "NVDA"}:
            rows.append(
                {
                    "Name": "Arista Networks",
                    "Role": "Data-center / AI cluster networking",
                    "External / Internal": "External",
                    "Revenue status": "Networking equipment revenue",
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if not any_mod:
        st.info("该公司暂无关联的 Cloud / Memory / Compute 行业地位模块。")


def render_events_panel(ticker: str) -> None:
    """重大事件 — company events + catalyst/risk."""
    range_label = st.selectbox(
        "时间范围",
        ["Current quarter", "30D", "90D"],
        key=f"ss_event_range_{ticker}",
    )
    key_map = {"Current quarter": "current_quarter", "30D": "30D", "90D": "90D"}
    rk = key_map[range_label]

    event_rows = []
    for ev in events_for(ticker, limit=10, range_key=rk):
        event_rows.append(
            {
                "Date": ev.get("event_date"),
                "Event": ev.get("headline"),
                "Impact": ev.get("impact_label") or "Neutral",
            }
        )
    if event_rows:
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("所选范围内暂无事件。")

    ins = insight_for(ticker)
    c1, c2, c3 = st.columns(3)
    c1.metric("Quarter trend", trend_label(ins.get("quarter_trend")))
    c2.write("**Catalyst**")
    c2.write(ins.get("catalyst") or "—")
    c3.write("**Risk**")
    c3.write(ins.get("risk") or "—")
    if ins.get("quarter_reason"):
        st.caption(ins.get("quarter_reason"))
