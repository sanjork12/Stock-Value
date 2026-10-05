"""Streamlit UI for AI Industry Intelligence Map (V5)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import streamlit as st

from industry.constants import (
    LAYER_MAP_ORDER,
    LAYER_SHORT,
    MAG7,
    PROFIT_TAGS,
)
from industry.loader import (
    build_industry_map_export,
    companies_touching_layer,
    events_for,
    latest_earnings,
    load_accelerator_ecosystem,
    load_companies,
    load_meta,
    mag7_companies,
    market_share_rows,
    resolve_company,
    stars_to_text,
    valuation_ticker_for,
)


def _money(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(x) >= 1e9:
        return f"${x/1e9:.1f}B"
    if abs(x) >= 1e6:
        return f"${x/1e6:.0f}M"
    return f"${x:,.0f}"


def _pct(v: Any, *, signed: bool = False) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(x) <= 1.5 and abs(x) != 0:
        # treat as ratio
        x = x * 100.0
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f}pp"


def _freshness_banner() -> None:
    meta = load_meta()
    c1, c2, c3 = st.columns(3)
    c1.caption(f"Data through: **{meta.get('data_through') or '—'}**")
    c2.caption(f"Last refreshed: **{meta.get('last_refreshed_at') or '—'}**")
    c3.caption("Industry research only — not a buy/sell signal.")


def _open_stock_analysis(ticker: str) -> None:
    vt = valuation_ticker_for(ticker) or ticker
    st.session_state.selected_ticker = vt
    st.session_state._pending_nav_page = "单股分析"
    try:
        st.query_params["ticker"] = vt
    except Exception:
        pass
    st.rerun()


def _company_select_options() -> List[str]:
    opts = []
    for c in load_companies():
        cid = c.get("company_id")
        name = c.get("company_name")
        ticker = c.get("ticker") or ("private" if c.get("public_private") == "private" else "")
        opts.append(f"{cid} · {name} ({ticker})")
    return opts


def _parse_company_option(label: str) -> str:
    return str(label or "").split("·", 1)[0].strip()


def render_industry_map_tab() -> None:
    st.markdown("#### AI stack (4 layers)")
    st.caption("Stars = business / strategic presence (not an investment score).")
    for layer in LAYER_MAP_ORDER:
        with st.container(border=True):
            st.markdown(f"**{LAYER_SHORT.get(layer, layer)}**")
            comps = companies_touching_layer(layer)
            # compact chips
            cols = st.columns(4)
            for i, c in enumerate(comps):
                presence = (c.get("layer_presence") or {}).get(layer) or {}
                stars = int(presence.get("stars") or 0)
                if stars <= 0 and c.get("primary_layer") != layer and layer not in (c.get("secondary_layers") or []):
                    continue
                tag = PROFIT_TAGS.get(str(presence.get("profit_tag") or ""), "")
                with cols[i % 4]:
                    label = f"{c.get('company_id')}"
                    st.markdown(f"**{label}** {stars_to_text(stars)}")
                    if tag:
                        st.caption(tag)
                    if st.button("Detail", key=f"map_{layer}_{c.get('company_id')}", use_container_width=True):
                        st.session_state.industry_detail_id = c.get("company_id")
                        st.session_state.industry_force_detail = True
                        st.rerun()


def render_mag7_tab(valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    rows = []
    for c in mag7_companies():
        cid = c.get("company_id")
        earn = latest_earnings(cid) or {}
        val: Dict[str, Any] = {}
        vt = valuation_ticker_for(cid)
        if valuation_loader and vt:
            try:
                val = valuation_loader(vt) or {}
            except Exception as exc:
                val = {"status": f"valuation unavailable ({type(exc).__name__})"}
        rows.append(
            {
                "Ticker": vt or cid,
                "Company": c.get("company_name"),
                "Price": val.get("price_display") or val.get("price") or "—",
                "Market Cap": val.get("market_cap_display") or "—",
                "Revenue Growth": _pct(earn.get("revenue_growth_yoy"), signed=True),
                "Main Profit Engine": c.get("main_revenue_engine"),
                "Cloud Exposure": (c.get("strategic_presence") or {}).get("cloud"),
                "AI Infra Exposure": (c.get("strategic_presence") or {}).get("infrastructure"),
                "AI Monetization": c.get("ai_monetization_status"),
                "CapEx": _money(earn.get("capex")),
                "Fair Value": val.get("fair_value_display") or "—",
                "Valuation Status": val.get("status") or "—",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Fair Value / Status come from existing Stock Analysis (`analysis_service`). No re-valuation in Industry Map.")

    st.markdown("##### Magnificent Seven strategy matrix")
    strat = []
    for c in mag7_companies():
        sp = c.get("strategic_presence") or {}
        strat.append(
            {
                "Company": c.get("company_id"),
                "Infrastructure": sp.get("infrastructure"),
                "Cloud": sp.get("cloud"),
                "Model/Platform": sp.get("model_platform"),
                "Applications": sp.get("applications"),
                "Current Main Profit": c.get("main_revenue_engine"),
                "Next Expansion": c.get("next_expansion"),
                "AI CapEx intensity": c.get("ai_capex_intensity"),
            }
        )
    st.dataframe(pd.DataFrame(strat), use_container_width=True, hide_index=True)


def render_earnings_tab() -> None:
    opts = [c for c in load_companies() if c.get("include_in_valuation") is not False or c.get("company_id") in MAG7]
    # Prefer companies that have earnings rows
    labels = []
    for c in load_companies():
        if latest_earnings(c.get("company_id") or ""):
            labels.append(f"{c.get('company_id')} · {c.get('company_name')}")
    if not labels:
        st.warning("No earnings snapshots loaded.")
        return
    choice = st.selectbox("Company", labels, key="ind_earn_company")
    cid = _parse_company_option(choice)
    earn = latest_earnings(cid)
    if not earn:
        st.info("No quarter snapshot for this company yet.")
        return
    st.markdown(
        f"**{cid}** · {earn.get('fiscal_period')} · reported {earn.get('report_date')}  \n"
        f"Sources: {', '.join(earn.get('source_urls') or [])}"
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Revenue", _money(earn.get("total_revenue")), _pct(earn.get("revenue_growth_yoy"), signed=True))
    m2.metric("Op. margin", _pct(earn.get("operating_margin")))
    m3.metric("CapEx", _money(earn.get("capex")), _pct(earn.get("capex_yoy"), signed=True) if earn.get("capex_yoy") is not None else None)
    m4.metric("FCF", _money(earn.get("free_cash_flow")))
    if earn.get("capex_as_pct_revenue") is not None:
        st.caption(f"CapEx / Revenue: {_pct(earn.get('capex_as_pct_revenue'))}")

    segs = earn.get("segments") or []
    if segs:
        st.markdown("##### Revenue Mix")
        df = pd.DataFrame(
            [
                {
                    "Segment": s.get("name"),
                    "Revenue": _money(s.get("revenue")),
                    "% of total": s.get("percentage_of_total"),
                    "YoY": _pct(s.get("yoy_growth"), signed=True),
                }
                for s in segs
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
        chart_df = pd.DataFrame(
            {"segment": [s.get("name") for s in segs], "pct": [float(s.get("percentage_of_total") or 0) for s in segs]}
        ).set_index("segment")
        st.bar_chart(chart_df)
        st.caption(f"Schema: `{earn.get('segment_schema_version')}` · quality: `{earn.get('data_quality')}`")

    st.markdown("##### AI Infrastructure Spending (hyperscalers)")
    spend_ids = ["MSFT", "GOOG", "AMZN", "META", "ORCL"]
    spend_rows = []
    for sid in spend_ids:
        e = latest_earnings(sid) or {}
        c = resolve_company(sid) or {}
        spend_rows.append(
            {
                "Company": sid,
                "CapEx": _money(e.get("capex")),
                "YoY": _pct(e.get("capex_yoy"), signed=True) if e.get("capex_yoy") is not None else "—",
                "CapEx/Revenue": _pct(e.get("capex_as_pct_revenue")) if e.get("capex_as_pct_revenue") is not None else "—",
                "Intensity tag": c.get("ai_capex_intensity"),
            }
        )
    st.dataframe(pd.DataFrame(spend_rows), use_container_width=True, hide_index=True)


def _share_table(market: str, title: str) -> None:
    st.markdown(f"##### {title}")
    rows = market_share_rows(market)
    if not rows:
        st.caption("No rows.")
        return
    period = rows[0].get("period")
    st.caption(f"Period: {period} · source required for every percentage")
    out = []
    for r in rows:
        share = r.get("share_pct")
        out.append(
            {
                "Company": r.get("company"),
                "Share": f"{float(share):.1f}%" if share is not None else (r.get("tier") or r.get("leader_status") or "n/a"),
                "Previous": f"{float(r['previous_share_pct']):.1f}%" if r.get("previous_share_pct") is not None else "—",
                "Change": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "Rank": r.get("rank") if r.get("rank") is not None else "—",
                "Source": r.get("source"),
            }
        )
    st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)


def render_market_share_tab() -> None:
    _share_table("cloud_infrastructure", "Cloud infrastructure")
    _share_table("dram", "DRAM")
    _share_table("hbm", "HBM (rank / leader — no invented %)")
    st.markdown("##### AI accelerator ecosystem (not a fake share pie)")
    eco = load_accelerator_ecosystem()
    st.dataframe(pd.DataFrame(eco), use_container_width=True, hide_index=True)
    st.caption("Merchant vs internal/cloud-specific chips are separated. Precise NVDA/AMD % only if sourced.")


def render_infrastructure_tab() -> None:
    infra = [c for c in load_companies() if c.get("primary_layer") == "infrastructure" or ((c.get("layer_presence") or {}).get("infrastructure") or {}).get("stars", 0) >= 3]
    rows = []
    for c in infra:
        p = (c.get("layer_presence") or {}).get("infrastructure") or {}
        rows.append(
            {
                "Company": c.get("company_id"),
                "Name": c.get("company_name"),
                "Presence": stars_to_text(int(p.get("stars") or 0)),
                "Profit tag": PROFIT_TAGS.get(str(p.get("profit_tag") or ""), p.get("profit_tag")),
                "Main engine": c.get("main_revenue_engine"),
                "AI monetization": c.get("ai_monetization_status"),
                "In valuation?": "yes" if c.get("include_in_valuation") else "reference only",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    _share_table("dram", "Memory share")
    _share_table("hbm", "HBM ranking")


def render_applications_tab() -> None:
    apps = [
        c
        for c in load_companies()
        if c.get("primary_layer") == "applications"
        or ((c.get("layer_presence") or {}).get("applications") or {}).get("stars", 0) >= 3
    ]
    rows = []
    for c in apps:
        p = (c.get("layer_presence") or {}).get("applications") or {}
        rows.append(
            {
                "Company": c.get("company_id"),
                "Name": c.get("company_name"),
                "Presence": stars_to_text(int(p.get("stars") or 0)),
                "Profit tag": PROFIT_TAGS.get(str(p.get("profit_tag") or ""), p.get("profit_tag")),
                "Main engine": c.get("main_revenue_engine"),
                "AI monetization": c.get("ai_monetization_status"),
                "Next expansion": c.get("next_expansion"),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_events_tab() -> None:
    range_key = st.selectbox("Range", ["Current quarter", "30D", "90D", "YTD"], key="ind_event_range")
    key_map = {"Current quarter": "current_quarter", "30D": "30D", "90D": "90D", "YTD": "YTD"}
    rk = key_map[range_key]
    labels = _company_select_options()
    choice = st.selectbox("Company", labels, key="ind_event_company")
    cid = _parse_company_option(choice)
    evs = events_for(cid, limit=8, range_key=rk)
    if not evs:
        st.info("No events in selected range.")
        return
    for ev in evs:
        with st.container(border=True):
            st.markdown(
                f"**{ev.get('event_date')}** · `{ev.get('impact_label')}` · {ev.get('event_type')}  \n"
                f"{ev.get('headline')}"
            )
            st.caption(ev.get("summary") or "")
            st.caption(f"Impact: {ev.get('strategic_impact') or '—'} · Source: {ev.get('source_name') or ev.get('source_url')}")


def render_company_detail(company_id: str, valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    c = resolve_company(company_id)
    if not c:
        st.error("Company not found.")
        return
    st.markdown(f"### {c.get('company_name')} ({c.get('company_id')})")
    st.caption(
        f"Primary: **{LAYER_SHORT.get(c.get('primary_layer'), c.get('primary_layer'))}** · "
        f"AI monetization: **{c.get('ai_monetization_status')}** · "
        f"{'Public' if c.get('public_private')=='public' else 'Private reference'}"
    )
    left, right = st.columns([2, 1])
    with left:
        st.markdown("**Role in AI stack**")
        for role in c.get("industry_roles") or []:
            st.write(f"- {role}")
        st.markdown("**Current profit layers** vs **future expansion**")
        st.write(
            {
                "current_profit_layers": c.get("current_profit_layers"),
                "future_expansion_layers": c.get("future_expansion_layers"),
            }
        )
        presence_rows = []
        for layer in LAYER_MAP_ORDER[::-1]:
            p = (c.get("layer_presence") or {}).get(layer) or {}
            presence_rows.append(
                {
                    "Layer": LAYER_SHORT.get(layer),
                    "Presence": stars_to_text(int(p.get("stars") or 0)),
                    "Tag": PROFIT_TAGS.get(str(p.get("profit_tag") or ""), ""),
                    "Note": p.get("note") or "",
                }
            )
        st.dataframe(pd.DataFrame(presence_rows), use_container_width=True, hide_index=True)

        earn = latest_earnings(c.get("company_id"))
        if earn:
            st.markdown(f"**Latest earnings** · {earn.get('fiscal_period')}")
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
            st.caption(f"Sources: {', '.join(earn.get('source_urls') or [])}")

        st.markdown("**Latest major events**")
        for ev in events_for(c.get("company_id"), limit=5, range_key="90D"):
            st.write(f"- {ev.get('event_date')}: {ev.get('headline')} (`{ev.get('impact_label')}`)")

    with right:
        vt = valuation_ticker_for(c.get("company_id"))
        if vt and valuation_loader:
            try:
                val = valuation_loader(vt) or {}
            except Exception as exc:
                val = {"status": f"unavailable ({type(exc).__name__})"}
            st.markdown("**Current valuation summary**")
            st.write(
                {
                    "ticker": vt,
                    "price": val.get("price_display") or val.get("price"),
                    "fair_value": val.get("fair_value_display"),
                    "status": val.get("status"),
                    "confidence": val.get("confidence"),
                }
            )
            if st.button("Open Stock Analysis", type="primary", key=f"open_sa_{vt}"):
                _open_stock_analysis(vt)
        elif not vt:
            st.info("Reference company — not linked to Stock Analysis valuation.")
        else:
            st.caption("Valuation loader unavailable in this session.")

        st.markdown("**Market share positions**")
        hits = []
        for market in ("cloud_infrastructure", "dram", "hbm", "ai_accelerator"):
            for r in market_share_rows(market):
                if str(r.get("company_id") or "").upper() == str(c.get("company_id")).upper():
                    hits.append(
                        {
                            "market": market,
                            "share": r.get("share_pct"),
                            "rank": r.get("rank"),
                            "note": r.get("leader_status") or r.get("tier"),
                            "source": r.get("source"),
                        }
                    )
        if hits:
            st.dataframe(pd.DataFrame(hits), use_container_width=True, hide_index=True)
        else:
            st.caption("No sourced market-share rows for this company.")


def render_industry_page(valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    st.subheader("AI Industry Intelligence")
    _freshness_banner()

    if st.session_state.pop("industry_force_detail", None) and st.session_state.get("industry_detail_id"):
        default_tab = "Company Detail"
    else:
        default_tab = "Industry Map"

    tabs = [
        "Industry Map",
        "Magnificent Seven",
        "Earnings & Revenue Mix",
        "Market Share",
        "Infrastructure",
        "Applications",
        "Events",
        "Company Detail",
    ]
    # segmented for compactness
    if hasattr(st, "segmented_control"):
        tab = st.segmented_control("Industry tabs", tabs, default=default_tab if default_tab in tabs else tabs[0], key="industry_tab") or tabs[0]
    else:
        tab = st.radio("Industry tabs", tabs, horizontal=True, key="industry_tab")

    if tab == "Industry Map":
        render_industry_map_tab()
    elif tab == "Magnificent Seven":
        render_mag7_tab(valuation_loader)
    elif tab == "Earnings & Revenue Mix":
        render_earnings_tab()
    elif tab == "Market Share":
        render_market_share_tab()
    elif tab == "Infrastructure":
        render_infrastructure_tab()
    elif tab == "Applications":
        render_applications_tab()
    elif tab == "Events":
        render_events_tab()
    else:
        labels = _company_select_options()
        pre = st.session_state.get("industry_detail_id")
        idx = 0
        if pre:
            for i, lab in enumerate(labels):
                if lab.startswith(str(pre)):
                    idx = i
                    break
        choice = st.selectbox("Company", labels, index=idx, key="ind_detail_select")
        render_company_detail(_parse_company_option(choice), valuation_loader)

    st.divider()
    e1, e2, e3 = st.columns(3)
    e1.button("Export Industry Map", disabled=True, help="TODO V5.5")
    e2.button("Export Company Card", disabled=True, help="TODO V5.5")
    e3.button("Export Mag7 Summary", disabled=True, help="TODO V5.5")
    with st.expander("PPT-ready JSON preview (export stub)", expanded=False):
        payload = build_industry_map_export()
        st.json(
            {
                "schema_version": payload.get("schema_version"),
                "layers_count": len(payload.get("layers") or []),
                "companies_count": len(payload.get("companies") or []),
                "market_share_count": len(payload.get("market_share") or []),
                "events_count": len(payload.get("events") or []),
            }
        )
