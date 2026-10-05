"""单股分析 — 财报 / 行业地位 / 重大事件面板（中文 UI）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from industry.constants import LAYER_SHORT_ZH
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
    return f"{x:+.1f} 百分点"


def render_earnings_panel(ticker: str) -> None:
    c = resolve_company(ticker)
    earn = latest_earnings(ticker)
    if not c:
        st.caption("暂无产业分类数据")
    if not earn:
        st.info("暂无季度财报快照。")
        return

    st.caption(f"{ticker} · {earn.get('fiscal_period')} · {earn.get('report_date')}")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("营收", _money(earn.get("total_revenue")))
    m2.metric("同比", _pct(earn.get("revenue_growth_yoy"), signed=True))
    m3.metric("营业利润", _money(earn.get("operating_income")))
    m4.metric("营业利润率", _pct(earn.get("operating_margin")))
    m5.metric("自由现金流", _money(earn.get("free_cash_flow")))
    m6.metric("资本开支", _money(earn.get("capex")))
    if earn.get("capex_as_pct_revenue") is not None:
        st.caption(f"资本开支 / 营收：{_pct(earn.get('capex_as_pct_revenue'))}")

    segs = earn.get("segments") or []
    if segs:
        st.markdown("**收入构成**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "分部": s.get("name"),
                        "营收": _money(s.get("revenue")),
                        "占比%": s.get("percentage_of_total"),
                        "同比": _pct(s.get("yoy_growth"), signed=True),
                    }
                    for s in segs
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    e1, e2 = st.columns(2)
    with e1:
        st.caption("当前利润引擎")
        st.write((c or {}).get("main_revenue_engine") or "—")
        cur = (c or {}).get("current_profit_layers") or []
        if cur:
            st.caption("、".join(LAYER_SHORT_ZH.get(x, x) for x in cur))
    with e2:
        st.caption("未来扩张方向")
        st.write((c or {}).get("next_expansion") or "—")
        fut = (c or {}).get("future_expansion_layers") or []
        if fut:
            st.caption("、".join(LAYER_SHORT_ZH.get(x, x) for x in fut))


def _share_block(market: str, title: str) -> None:
    st.markdown(f"**{title}**")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据")
        return
    out = []
    for r in rows:
        company = str(r.get("company") or "")
        share = r.get("share_pct")
        out.append(
            {
                "公司": company,
                "份额": (
                    f"{float(share):.1f}%"
                    if share is not None
                    else (r.get("tier") or r.get("leader_status") or "未单独披露")
                ),
                "此前": f"{float(r['previous_share_pct']):.1f}%" if r.get("previous_share_pct") is not None else "—",
                "变化": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "排名": r.get("rank") if r.get("rank") is not None else "—",
            }
        )
    st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)


def render_position_panel(ticker: str) -> None:
    watch = [str(ticker or "").upper()]
    any_mod = False
    if show_cloud_module(watch):
        any_mod = True
        _share_block("cloud_infrastructure", "云计算")
    if show_memory_module(watch):
        any_mod = True
        _share_block("dram", "存储 · DRAM")
        _share_block("hbm", "存储 · HBM")
    if show_compute_module(watch):
        any_mod = True
        st.markdown("**AI 算力 / 网络**")
        eco = load_accelerator_ecosystem()
        rows: List[Dict[str, Any]] = []
        for row in eco:
            name = row.get("name") or row.get("company")
            role = row.get("product") or row.get("leader_status")
            if not name or str(name).lower() == "none":
                continue
            if row.get("market") in {"cloud_infrastructure", "dram", "hbm"} and not row.get("product"):
                continue
            ext = (
                "外部市场"
                if row.get("external_market")
                else ("内部自用" if row.get("internal_only") else "云厂商定制")
            )
            rows.append(
                {
                    "名称": name,
                    "角色": role or "—",
                    "外部/内部": ext,
                    "收入状态": row.get("current_revenue_status") or "—",
                }
            )
        t = watch[0]
        if t in {"ANET", "AVGO", "NVDA"}:
            rows.append(
                {
                    "名称": "Arista Networks",
                    "角色": "数据中心 / AI 集群网络",
                    "外部/内部": "外部市场",
                    "收入状态": "网络设备收入",
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if not any_mod:
        st.info("该公司暂无关联的云计算 / 存储 / 算力行业地位模块。")


def render_events_panel(ticker: str) -> None:
    range_label = st.selectbox(
        "时间范围",
        ["本季度", "近30天", "近90天"],
        key=f"ss_event_range_{ticker}",
    )
    key_map = {"本季度": "current_quarter", "近30天": "30D", "近90天": "90D"}
    rk = key_map[range_label]

    impact_zh = {
        "Positive": "正面",
        "Neutral": "中性",
        "Risk": "风险",
        "Strategic": "战略",
    }

    event_rows = []
    for ev in events_for(ticker, limit=10, range_key=rk):
        event_rows.append(
            {
                "日期": ev.get("event_date"),
                "事件": ev.get("headline"),
                "影响": impact_zh.get(str(ev.get("impact_label") or ""), ev.get("impact_label") or "中性"),
            }
        )
    if event_rows:
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("所选范围内暂无事件。")

    ins = insight_for(ticker)
    c1, c2, c3 = st.columns(3)
    c1.metric("季度趋势", trend_label(ins.get("quarter_trend")))
    c2.write("**催化剂**")
    c2.write(ins.get("catalyst") or "—")
    c3.write("**风险**")
    c3.write(ins.get("risk") or "—")
    if ins.get("quarter_reason"):
        st.caption(ins.get("quarter_reason"))
