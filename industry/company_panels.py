"""单股分析内嵌面板：财报与业务 + 最新事件 teaser（V5.4）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from industry.constants import LAYER_SHORT_ZH
from industry.earnings_helpers import get_latest_reported_quarter
from industry.events_provider import get_company_events, range_bounds
from industry.loader import resolve_company


def _money(v: Any, currency: str = "USD") -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    symbol = "¥" if currency == "CNY" else "$"
    if abs(x) >= 1e9:
        return f"{symbol}{x / 1e9:.1f}B"
    if abs(x) >= 1e6:
        return f"{symbol}{x / 1e6:.0f}M"
    return f"{symbol}{x:,.0f}"


def _pct(v: Any, *, signed: bool = False, digits: int = 0, ratio: bool = False) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if ratio or (abs(x) <= 1.5 and x != 0):
        x *= 100.0
    if signed:
        return f"{x:+.{digits}f}%"
    return f"{x:.{digits}f}%"


def render_earnings_inline(ticker: str) -> None:
    """最新已正式公布季度财报 + 收入构成 + 利润引擎 / 扩张。"""
    c = resolve_company(ticker)
    earn = get_latest_reported_quarter(ticker)
    if not earn:
        st.markdown("#### 最新财报")
        st.info("暂无已正式公布的季度财报快照。")
        return

    period = earn.get("latest_reported_period") or earn.get("fiscal_period") or "—"
    import re
    period_match = re.search(r'(FY|CY)?(\d{4})\s*Q([1-4])', period)
    display_period = (f"Q{period_match[3]} {period_match[2]}" + ('（财政年度）' if period_match[1] == 'FY' else '')) if period_match else period
    st.markdown(f"#### 最新财报 · {display_period}")
    report_date = earn.get("latest_report_date") or earn.get("report_date") or "—"
    st.caption(f"发布日期：{report_date} · 期间结束：{earn.get('period_end') or '未核实'}")
    if str(earn.get("data_status") or "").upper() == "STALE_DATA":
        age = earn.get("data_age_days")
        age_txt = f"（已过 {age} 天）" if age is not None else ""
        st.warning(f"STALE_DATA · 财报数据可能过期{age_txt}")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    ratio = earn.get('snapshot_collection') == 'company_quarter_snapshots'
    m1.metric("营收", _money(earn.get("total_revenue"), earn.get("currency", "USD")))
    m2.metric("同比", _pct(earn.get("revenue_growth_yoy"), signed=True, ratio=ratio))
    m3.metric("营业利润", _money(earn.get("operating_income"), earn.get("currency", "USD")))
    m4.metric("营业利润率", _pct(earn.get("operating_margin"), ratio=ratio))
    m5.metric("自由现金流", _money(earn.get("free_cash_flow"), earn.get("currency", "USD")))
    m6.metric("资本开支", _money(earn.get("capex"), earn.get("currency", "USD")))
    if earn.get('currency') == 'CNY':
        st.caption('本快照金额单位为人民币。')
    if earn.get('notes'):
        st.caption(earn['notes'])
    if earn.get('missing_data_note'):
        st.caption(earn['missing_data_note'])
    if earn.get('source_url'):
        st.markdown(f"[官方财报原文]({earn['source_url']}) · 核验日期：{earn.get('last_verified_at') or '—'}")
    if earn.get("capex_as_pct_revenue") is not None:
        st.caption(f"资本开支 / 营收：{_pct(earn.get('capex_as_pct_revenue'), ratio=ratio)}")

    segs = earn.get("segments") or []
    if segs:
        st.markdown("**收入构成**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "分部": s.get("name"),
                        "营收": _money(s.get("revenue"), earn.get("currency", "USD")),
                        "占比%": s.get("percentage_of_total"),
                        "同比": _pct(s.get("yoy_growth"), signed=True, ratio=ratio),
                    }
                    for s in segs
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    if earn.get('narrative_note'):
        st.caption(earn['narrative_note'])
    e1, e2 = st.columns(2)
    with e1:
        st.caption("当前利润引擎")
        st.write(earn.get('current_profit_engine') or (c or {}).get("main_revenue_engine") or "—")
        cur = (c or {}).get("current_profit_layers") or []
        if cur:
            st.caption("、".join(LAYER_SHORT_ZH.get(x, x) for x in cur))
    with e2:
        st.caption("未来扩张方向")
        st.write(earn.get('future_expansion') or (c or {}).get("next_expansion") or "—")
        fut = (c or {}).get("future_expansion_layers") or []
        if fut:
            st.caption("、".join(LAYER_SHORT_ZH.get(x, x) for x in fut))

    st.caption("查看相关市场格局 → 请切换至一级导航「市场格局」")


def render_latest_event_teaser(ticker: str, *, open_headlines_cb=None) -> None:
    """最多 1 条最新重大事件标题 + 跳转头等大事（不复制全文）。"""
    st.markdown("#### 最新重大事件")
    bounds = range_bounds("本季度")
    rows = get_company_events(
        [ticker],
        start_time=bounds["start_time"],
        end_time=bounds["end_time"],
        include_upcoming=False,
        range_key="本季度",
    )
    if not rows:
        from finnhub_service import get_finnhub_provider
        st.caption("本季度暂无重大事件。" if get_finnhub_provider().configured() else "实时新闻源未配置。")
    else:
        material = [row for row in rows if row.get("importance") in {"重大", "重要"}]
        ev = max(material or rows, key=lambda row: str(row.get('event_time') or row.get('event_date') or ''))
        st.caption(ev.get("conclusion") or ev.get("short_summary") or "")
        st.write(
            f"**{ev.get('ticker')}** · {ev.get('event_date')} · {ev.get('importance')} · "
            f"{ev.get('headline')}"
        )
    if open_headlines_cb is not None:
        if rows and st.button("查看详情 →", key=f"ss_to_headlines_{ticker}"):
            st.session_state['headline_selected_event'] = ev
            open_headlines_cb(ticker, ev.get('event_id'))
    else:
        st.caption("查看该股票全部头等大事 → 一级导航「头等大事」")


# Backward-compatible names for any residual imports
def render_earnings_panel(ticker: str) -> None:
    render_earnings_inline(ticker)


def render_position_panel(ticker: str) -> None:
    st.info("行业地位已移至「市场格局」页面。")


def render_events_panel(ticker: str) -> None:
    render_latest_event_teaser(ticker)
