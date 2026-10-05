"""V5.1.1 Watchlist-driven Industry UI — compact decision-first layout."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd
import streamlit as st

from industry.constants import (
    CAPEX_INTENSITY_LABEL,
    MAG7,
    MONETIZATION_ZH,
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

# Default core columns (decision-first order). Do not reorder lightly.
CORE_WATCHLIST_COLS = [
    "股票",
    "主要利润引擎",
    "最新收入增速",
    "季度变化",
    "AI变现",
    "CapEx强度",
    "当前估值状态",
]

ADVANCED_WATCHLIST_COLS = [
    "产业层级",
    "未来扩张",
    "Catalyst",
    "Risk",
    "公司",
]


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
    """Format growth/rates as +18% / -5% (not 0.18 or 18.0000%)."""
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


def _capex_label(raw: Any) -> str:
    key = str(raw or "").strip().lower().replace(" ", "_")
    return CAPEX_INTENSITY_LABEL.get(key, str(raw or "—") if raw else "—")


def _monetization_zh(raw: Any) -> str:
    key = str(raw or "").strip().upper()
    if not key:
        return "—"
    return MONETIZATION_ZH.get(key, key)


def _open_stock(ticker: str) -> None:
    vt = valuation_ticker_for(ticker) or str(ticker).upper()
    st.session_state.selected_ticker = vt
    st.session_state._pending_nav_page = "单股分析"
    try:
        st.query_params["ticker"] = vt
    except Exception:
        pass
    st.rerun()


def _footer_meta() -> None:
    meta = load_meta()
    period = meta.get("data_through") or "—"
    refreshed = str(meta.get("last_refreshed_at") or "—")[:10]
    with st.expander("数据说明", expanded=False):
        st.caption(f"数据周期：{period} · 更新：{refreshed} · 研究用途")
    st.caption("研究工具，不构成个性化投资建议。")


def _empty_watchlist_message() -> None:
    st.info("你的自选股目前为空。添加股票后，这里会自动生成产业链与基本面视图。")


def render_tab_map(watch: List[str]) -> None:
    """「我的产业链」：全景图直出，无额外说明标题。"""
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
    reason = insight.get("quarter_reason") or ""
    return {
        "_group": row_group,
        "股票": valuation_ticker_for(ticker) or ticker,
        "公司": (c or {}).get("company_name") or ticker,
        "产业层级": layer_label_for_profile(c) if c else "Other / Unclassified",
        "主要利润引擎": (c or {}).get("main_revenue_engine") or ("—" if unclassified else "—"),
        "最新收入增速": _pct((earn or {}).get("revenue_growth_yoy"), signed=True) if earn else "—",
        "季度变化": trend_label(insight.get("quarter_trend")),
        "_quarter_reason": reason,
        "AI变现": _monetization_zh((c or {}).get("ai_monetization_status")) if c else "—",
        "CapEx强度": _capex_label((c or {}).get("ai_capex_intensity")) if c else "—",
        "当前估值状态": _valuation_status(ticker, valuation_loader),
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

    # Compact same-row toggles
    t1, t2, _ = st.columns([1.2, 1.0, 4.0])
    with t1:
        show_bench = st.checkbox("七巨头对照", value=False, key="ind_v51_benchmark")
    with t2:
        show_adv = st.checkbox("更多信息", value=False, key="ind_v51_adv")

    rows = [_overview_row(t, row_group="My Watchlist", valuation_loader=valuation_loader) for t in watch]
    if show_bench:
        watch_keys = set(watch) | ({"GOOG", "GOOGL"} if ("GOOG" in watch or "GOOGL" in watch) else set())
        for mid in MAG7:
            if mid in watch_keys or (mid == "GOOG" and ("GOOG" in watch_keys or "GOOGL" in watch_keys)):
                continue
            rows.append(_overview_row(mid, row_group="Benchmark", valuation_loader=valuation_loader))

    unclassified = [r["股票"] for r in rows if r.get("_unclassified") and r.get("_group") == "My Watchlist"]
    if unclassified:
        with st.expander(f"⚠ {len(unclassified)}只未分类", expanded=False):
            st.caption("、".join(unclassified))

    cols = list(CORE_WATCHLIST_COLS)
    if show_adv:
        cols = cols + list(ADVANCED_WATCHLIST_COLS)

    df = pd.DataFrame(rows)
    view = df[[c for c in cols if c in df.columns]]

    # Column config: keep core columns narrow enough for first-screen (no large)
    col_cfg: Dict[str, Any] = {
        "股票": st.column_config.TextColumn("股票", width="small"),
        "主要利润引擎": st.column_config.TextColumn("主要利润引擎", width="medium"),
        "最新收入增速": st.column_config.TextColumn("最新收入增速", width="small"),
        "季度变化": st.column_config.TextColumn("季度变化", width="small", help="原因见「更多信息」或最新变化 Tab"),
        "AI变现": st.column_config.TextColumn(
            "AI变现",
            width="small",
            help="直接=DIRECT · 间接=INDIRECT · 起步=EMERGING · 期权=OPTIONALITY",
        ),
        "CapEx强度": st.column_config.TextColumn("CapEx强度", width="small"),
        "当前估值状态": st.column_config.TextColumn("当前估值状态", width="medium"),
        "产业层级": st.column_config.TextColumn("产业层级", width="medium"),
        "未来扩张": st.column_config.TextColumn("未来扩张", width="medium"),
        "Catalyst": st.column_config.TextColumn("Catalyst", width="medium"),
        "Risk": st.column_config.TextColumn("Risk", width="medium"),
        "公司": st.column_config.TextColumn("公司", width="medium"),
    }
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={k: v for k, v in col_cfg.items() if k in view.columns},
    )

    j1, j2 = st.columns([3, 1])
    with j1:
        jump = st.selectbox(
            "打开单股分析",
            [r["股票"] for r in rows if r.get("_group") == "My Watchlist"],
            key="ind_v51_jump",
            label_visibility="collapsed",
        )
    with j2:
        if st.button("单股分析", type="primary", key="ind_v51_jump_btn", use_container_width=True):
            _open_stock(jump)


def render_tab_earnings(watch: List[str]) -> None:
    if not watch:
        _empty_watchlist_message()
        return
    choice = st.selectbox("选择股票", watch, key="ind_v51_earn_ticker")
    c = resolve_company(choice)
    earn = latest_earnings(choice)
    if not c:
        st.caption("暂无产业分类数据")
    if not earn:
        st.info("暂无季度财报快照。")
        return

    st.caption(f"{choice} · {earn.get('fiscal_period')} · {earn.get('report_date')}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Revenue", _money(earn.get("total_revenue")))
    m2.metric("YoY", _pct(earn.get("revenue_growth_yoy"), signed=True))
    m3.metric("Operating Margin", _pct(earn.get("operating_margin")))
    m4.metric("FCF", _money(earn.get("free_cash_flow")))
    capex_rev = earn.get("capex_as_pct_revenue")
    if capex_rev is not None:
        m5.metric("CapEx / Revenue", _pct(capex_rev))
    else:
        m5.metric("CapEx / Revenue", "—")

    segs = earn.get("segments") or []
    if segs:
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
        st.caption("主要利润引擎")
        st.write((c or {}).get("main_revenue_engine") or "—")
    with e2:
        st.caption("未来扩张")
        st.write((c or {}).get("next_expansion") or "—")

    # CapEx detail lives here (not in core watchlist table)
    if earn.get("capex") is not None:
        st.caption(
            f"CapEx：{_money(earn.get('capex'))}"
            + (f" · CapEx YoY：{_pct(earn.get('capex_yoy'), signed=True)}" if earn.get("capex_yoy") is not None else "")
        )


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


def render_tab_position(watch: List[str]) -> None:
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
        st.markdown("**Compute**")
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
                    "Ecosystem position": (
                        "Merchant"
                        if row.get("merchant_chip")
                        else ("Cloud-specific" if row.get("cloud_specific") else "Internal")
                    ),
                }
            )
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
    if not any_mod:
        st.info("当前自选股暂无关联的 Cloud / Memory / Compute 模块。")


def render_tab_changes(watch: List[str]) -> None:
    if not watch:
        _empty_watchlist_message()
        return
    range_label = st.selectbox("时间范围", ["Current quarter", "30D", "90D"], key="ind_v51_event_range")
    key_map = {"Current quarter": "current_quarter", "30D": "30D", "90D": "90D"}
    rk = key_map[range_label]

    event_rows = []
    for t in watch:
        for ev in events_for(t, limit=3, range_key=rk):
            event_rows.append(
                {
                    "Ticker": t,
                    "Date": ev.get("event_date"),
                    "Event": ev.get("headline"),
                    "Impact": ev.get("impact_label") or "Neutral",
                }
            )

    if event_rows:
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("所选范围内暂无事件。")

    with st.expander("Catalyst / Risk", expanded=False):
        insight_rows = []
        for t in watch:
            ins = insight_for(t)
            insight_rows.append(
                {
                    "Ticker": t,
                    "季度变化": trend_label(ins.get("quarter_trend")),
                    "原因": ins.get("quarter_reason"),
                    "Catalyst": ins.get("catalyst"),
                    "Risk": ins.get("risk"),
                }
            )
        st.dataframe(pd.DataFrame(insight_rows), use_container_width=True, hide_index=True)


def render_industry_page(
    valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None,
    watchlist_tickers: Optional[Sequence[Any]] = None,
) -> None:
    watch = normalize_watchlist_tickers(watchlist_tickers)

    tabs = ["我的产业链", "我的自选股", "收入与盈利", "行业地位", "最新变化"]
    if hasattr(st, "segmented_control"):
        tab = (
            st.segmented_control(
                "产业页签",
                tabs,
                default=tabs[0],
                key="ind_v51_tabs",
                label_visibility="collapsed",
            )
            or tabs[0]
        )
    else:
        tab = st.radio(
            "产业页签",
            tabs,
            horizontal=True,
            key="ind_v51_tabs",
            label_visibility="collapsed",
        )

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

    with st.expander("高级工具", expanded=False):
        st.caption("Export / PPT JSON / 公司卡片导出 — 暂未启用")

    _footer_meta()
