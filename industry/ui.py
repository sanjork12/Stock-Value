"""V5.1 Watchlist-driven Industry Intelligence UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd
import streamlit as st

from industry.constants import (
    CAPEX_INTENSITY_LABEL,
    LAYER_SHORT,
    MAG7,
)
from industry.loader import (
    events_for,
    insight_for,
    latest_earnings,
    layer_label_for_profile,
    load_accelerator_ecosystem,
    load_meta,
    market_share_rows,
    normalize_watchlist_tickers,
    resolve_company,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
    trend_label,
    valuation_ticker_for,
)

_PANORAMA = Path(__file__).resolve().parent.parent / "assets" / "ai_industry_panorama.jpg"


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


def _pct(v: Any, *, signed: bool = False) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(x) <= 1.5 and x != 0:
        x *= 100.0
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f}pp"


def _capex_label(raw: Any) -> str:
    key = str(raw or "").strip().lower().replace(" ", "_")
    return CAPEX_INTENSITY_LABEL.get(key, str(raw or "—"))


def _open_stock(ticker: str) -> None:
    vt = valuation_ticker_for(ticker) or str(ticker).upper()
    st.session_state.selected_ticker = vt
    st.session_state._pending_nav_page = "单股分析"
    try:
        st.query_params["ticker"] = vt
    except Exception:
        pass
    st.rerun()


def _freshness_line() -> None:
    meta = load_meta()
    st.caption(
        f"数据：{meta.get('data_through') or '—'} · "
        f"最近更新：{str(meta.get('last_refreshed_at') or '—')[:10]} · "
        f"研究用途，不构成投资建议"
    )


def _empty_watchlist_message() -> None:
    st.info("你的自选股目前为空。添加股票后，这里会自动生成产业链与基本面视图。")


def render_tab_map(watch: List[str]) -> None:
    """「我的产业链」：仅展示用户提供的 AI 产业链全景图。"""
    if not watch:
        _empty_watchlist_message()
    if not _PANORAMA.exists():
        st.error(f"未找到全景图：`{_PANORAMA}`")
        return
    st.image(str(_PANORAMA), use_container_width=True)


def _valuation_status(ticker: str, valuation_loader: Optional[Callable[[str], Dict[str, Any]]]) -> str:
    if not valuation_loader:
        return "—"
    vt = valuation_ticker_for(ticker)
    if not vt:
        return "—"
    try:
        snap = valuation_loader(vt) or {}
        return str(snap.get("status") or "—")
    except Exception as exc:
        return f"暂不可用（{type(exc).__name__}）"


def _overview_row(
    ticker: str,
    *,
    row_group: str,
    valuation_loader: Optional[Callable[[str], Dict[str, Any]]],
) -> Dict[str, Any]:
    c = resolve_company(ticker)
    earn = latest_earnings(ticker) if c else None
    insight = insight_for(ticker)
    unclassified = c is None
    return {
        "分组": row_group,
        "股票": valuation_ticker_for(ticker) or ticker,
        "公司": (c or {}).get("company_name") or ticker,
        "产业层级": layer_label_for_profile(c) if c else "Other / Unclassified",
        "主要利润引擎": (c or {}).get("main_revenue_engine") or ("暂无产业分类数据" if unclassified else "—"),
        "收入增速": _pct((earn or {}).get("revenue_growth_yoy"), signed=True) if earn else "—",
        "季度变化": trend_label(insight.get("quarter_trend")),
        "AI 变现": (c or {}).get("ai_monetization_status") or "—",
        "CapEx 强度": _capex_label((c or {}).get("ai_capex_intensity")) if c else "—",
        "估值状态": _valuation_status(ticker, valuation_loader),
        "未来扩张": (c or {}).get("next_expansion") or "—",
        "Catalyst": insight.get("catalyst") or "—",
        "Risk": insight.get("risk") or "—",
        "_unclassified": unclassified,
    }


def render_tab_watchlist(
    watch: List[str],
    valuation_loader: Optional[Callable[[str], Dict[str, Any]]],
) -> None:
    if not watch:
        _empty_watchlist_message()
        return

    show_bench = st.checkbox("显示七巨头对照（Benchmark）", value=False, key="ind_v51_benchmark")
    rows = [_overview_row(t, row_group="My Watchlist", valuation_loader=valuation_loader) for t in watch]
    if show_bench:
        watch_keys = set(watch) | ({"GOOG", "GOOGL"} if ("GOOG" in watch or "GOOGL" in watch) else set())
        for mid in MAG7:
            # Avoid duplicate if already in watchlist
            if mid in watch_keys or (mid == "GOOG" and ("GOOG" in watch_keys or "GOOGL" in watch_keys)):
                continue
            rows.append(_overview_row(mid, row_group="Benchmark", valuation_loader=valuation_loader))

    show_adv = st.checkbox("显示高级列（公司 / 未来扩张 / Catalyst / Risk）", value=False, key="ind_v51_adv")
    base_cols = ["分组", "股票", "产业层级", "主要利润引擎", "收入增速", "季度变化", "AI 变现", "CapEx 强度", "估值状态"]
    if show_adv:
        base_cols = ["分组", "股票", "公司", "产业层级", "主要利润引擎", "收入增速", "季度变化", "AI 变现", "CapEx 强度", "估值状态", "未来扩张", "Catalyst", "Risk"]

    df = pd.DataFrame(rows)
    for flag in df.get("_unclassified", []):
        pass
    if any(r.get("_unclassified") for r in rows):
        st.caption("部分自选股暂无产业分类数据，已标为 Other / Unclassified。")
    view = df[[c for c in base_cols if c in df.columns]]
    st.dataframe(view, use_container_width=True, hide_index=True)

    jump = st.selectbox("打开单股分析", [r["股票"] for r in rows if r.get("分组") == "My Watchlist"], key="ind_v51_jump")
    if st.button("前往单股分析", type="primary", key="ind_v51_jump_btn"):
        _open_stock(jump)


def render_tab_earnings(watch: List[str]) -> None:
    if not watch:
        _empty_watchlist_message()
        return
    choice = st.selectbox("选择股票", watch, key="ind_v51_earn_ticker")
    c = resolve_company(choice)
    earn = latest_earnings(choice)
    if not c:
        st.warning("暂无产业分类数据")
    if not earn:
        st.info("暂无季度财报快照。")
        return

    st.markdown(f"**{choice}** · {earn.get('fiscal_period')} · 披露日 {earn.get('report_date')}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Revenue", _money(earn.get("total_revenue")), _pct(earn.get("revenue_growth_yoy"), signed=True))
    m2.metric("Op. income", _money(earn.get("operating_income")))
    m3.metric("Op. margin", _pct(earn.get("operating_margin")))
    m4.metric("FCF", _money(earn.get("free_cash_flow")))
    m5.metric("CapEx", _money(earn.get("capex")))
    if earn.get("capex_as_pct_revenue") is not None:
        st.caption(
            f"CapEx / Revenue：{_pct(earn.get('capex_as_pct_revenue'))}"
            + (f" · CapEx YoY：{_pct(earn.get('capex_yoy'), signed=True)}" if earn.get("capex_yoy") is not None else "")
            + " · 用于观察 AI 基础设施投入强度，不代表投入回报。"
        )

    segs = earn.get("segments") or []
    if segs:
        st.markdown("**收入构成**")
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

    st.markdown("**当前主要赚钱来源**")
    st.write((c or {}).get("main_revenue_engine") or "—")
    st.markdown("**未来新增收入方向**")
    st.write((c or {}).get("next_expansion") or "—")
    # Explicit separation
    cur = (c or {}).get("current_profit_layers") or []
    fut = (c or {}).get("future_expansion_layers") or []
    st.caption(
        "当前利润层："
        + ("、".join(LAYER_SHORT.get(x, x) for x in cur) or "—")
        + " ｜ 未来扩张层："
        + ("、".join(LAYER_SHORT.get(x, x) for x in fut) or "—")
    )


def _share_block(market: str, title: str) -> None:
    st.markdown(f"**{title}**")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据")
        return
    st.caption(f"Period：{rows[0].get('period')}")
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
                "Period": r.get("period"),
            }
        )
    st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)


def render_tab_position(watch: List[str]) -> None:
    if not watch:
        _empty_watchlist_message()
        return
    any_mod = False
    if show_cloud_module(watch):
        any_mod = True
        _share_block("cloud_infrastructure", "Cloud Market Share")
    if show_memory_module(watch):
        any_mod = True
        _share_block("dram", "DRAM Market Share")
        _share_block("hbm", "HBM Ranking（无可靠百分比则不展示假份额）")
    if show_compute_module(watch):
        any_mod = True
        st.markdown("**AI Compute / Networking Ecosystem**")
        eco = load_accelerator_ecosystem()
        # Always include ANET as networking if relevant — from companies note via eco + AVGO/NVDA
        rows = []
        for row in eco:
            rows.append(
                {
                    "Name": row.get("name"),
                    "Role": row.get("product"),
                    "External / Internal": (
                        "External" if row.get("external_market") else ("Internal" if row.get("internal_only") else "Cloud-specific")
                    ),
                    "Revenue status": row.get("current_revenue_status"),
                    "Ecosystem position": (
                        "Merchant" if row.get("merchant_chip") else ("Cloud-specific" if row.get("cloud_specific") else "Internal")
                    ),
                }
            )
        # ANET networking row (not in accelerator list)
        if any(t in {"ANET", "AVGO", "NVDA"} for t in watch):
            rows.append(
                {
                    "Name": "Arista Networks",
                    "Role": "Data-center / AI cluster networking",
                    "External / Internal": "External",
                    "Revenue status": "Networking equipment revenue",
                    "Ecosystem position": "Merchant networking",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("不提供无来源的精确 accelerator 市场份额。")
    if not any_mod:
        st.info("当前自选股暂无关联的 Cloud / Memory / AI Compute 模块。")


def render_tab_changes(watch: List[str]) -> None:
    if not watch:
        _empty_watchlist_message()
        return
    range_label = st.selectbox("时间范围", ["Current quarter", "30D", "90D"], key="ind_v51_event_range")
    key_map = {"Current quarter": "current_quarter", "30D": "30D", "90D": "90D"}
    rk = key_map[range_label]

    event_rows = []
    insight_rows = []
    for t in watch:
        for ev in events_for(t, limit=3, range_key=rk):
            event_rows.append(
                {
                    "Date": ev.get("event_date"),
                    "Ticker": t,
                    "Event": ev.get("headline"),
                    "Impact": ev.get("impact_label") or "Neutral",
                }
            )
        ins = insight_for(t)
        insight_rows.append(
            {
                "Ticker": t,
                "Quarter trend": trend_label(ins.get("quarter_trend")),
                "原因": ins.get("quarter_reason"),
                "Catalyst": ins.get("catalyst"),
                "Risk": ins.get("risk"),
            }
        )

    st.markdown("**最新事件（仅自选股）**")
    if event_rows:
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("所选范围内暂无事件。")

    st.markdown("**Catalyst / Risk / 季度变化**")
    st.dataframe(pd.DataFrame(insight_rows), use_container_width=True, hide_index=True)


def render_industry_page(
    valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None,
    watchlist_tickers: Optional[Sequence[Any]] = None,
) -> None:
    watch = normalize_watchlist_tickers(watchlist_tickers)

    st.subheader("我的 AI 产业链情报")
    st.caption("基于当前自选股，查看产业位置、收入结构、市场份额与最新变化")
    _freshness_line()

    tabs = ["我的产业链", "我的自选股", "收入与盈利", "行业地位", "最新变化"]
    if hasattr(st, "segmented_control"):
        tab = st.segmented_control("产业页签", tabs, default=tabs[0], key="ind_v51_tabs") or tabs[0]
    else:
        tab = st.radio("产业页签", tabs, horizontal=True, key="ind_v51_tabs")

    if tab == "我的产业链":
        render_tab_map(watch)
    elif tab == "我的自选股":
        render_tab_watchlist(watch, valuation_loader)
    elif tab == "收入与盈利":
        render_tab_earnings(watch)
    elif tab == "行业地位":
        render_tab_position(watch)
    else:
        render_tab_changes(watch)
