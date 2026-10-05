"""Streamlit UI for AI Industry Intelligence Map (V5) — 中文界面."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import streamlit as st

from industry.constants import (
    CAPEX_INTENSITY_ZH,
    EVENT_IMPACT_ZH,
    EVENT_TYPE_ZH,
    LAYER_MAP_ORDER,
    LAYER_SHORT,
    MAG7,
    MARKET_ZH,
    MONETIZATION_ZH,
    PAGE_TITLE,
    PRESENCE_ZH,
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
        x = x * 100.0
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f}个百分点"


def _zh_presence(v: Any) -> str:
    key = str(v or "").strip()
    return PRESENCE_ZH.get(key, key or "—")


def _zh_monetization(v: Any) -> str:
    key = str(v or "").strip().upper()
    return MONETIZATION_ZH.get(key, key or "—")


def _zh_capex(v: Any) -> str:
    key = str(v or "").strip()
    return CAPEX_INTENSITY_ZH.get(key, key or "—")


def _zh_impact(v: Any) -> str:
    key = str(v or "").strip()
    return EVENT_IMPACT_ZH.get(key, key or "—")


def _zh_event_type(v: Any) -> str:
    key = str(v or "").strip()
    return EVENT_TYPE_ZH.get(key, key or "—")


def _zh_layers(layers: Any) -> str:
    vals = []
    for item in layers or []:
        vals.append(LAYER_SHORT.get(str(item), str(item)))
    return "、".join(vals) if vals else "—"


def _freshness_banner() -> None:
    meta = load_meta()
    c1, c2, c3 = st.columns(3)
    c1.caption(f"数据覆盖至：**{meta.get('data_through') or '—'}**")
    c2.caption(f"最近刷新：**{meta.get('last_refreshed_at') or '—'}**")
    c3.caption("产业研究视图 · 不构成买卖建议")


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
        if c.get("public_private") == "private":
            ticker = "非上市公司"
        else:
            ticker = c.get("ticker") or "—"
        opts.append(f"{cid} · {name}（{ticker}）")
    return opts


def _parse_company_option(label: str) -> str:
    return str(label or "").split("·", 1)[0].strip()


def render_industry_map_tab() -> None:
    st.markdown("#### AI 产业链四层结构")
    st.caption("星级表示业务/战略存在感，不是投资评分。")
    for layer in LAYER_MAP_ORDER:
        with st.container(border=True):
            st.markdown(f"**{LAYER_SHORT.get(layer, layer)}**")
            comps = companies_touching_layer(layer)
            cols = st.columns(4)
            for i, c in enumerate(comps):
                presence = (c.get("layer_presence") or {}).get(layer) or {}
                stars = int(presence.get("stars") or 0)
                if stars <= 0 and c.get("primary_layer") != layer and layer not in (c.get("secondary_layers") or []):
                    continue
                tag = PROFIT_TAGS.get(str(presence.get("profit_tag") or ""), "")
                with cols[i % 4]:
                    st.markdown(f"**{c.get('company_id')}** {stars_to_text(stars)}")
                    if tag:
                        st.caption(tag)
                    if st.button("查看详情", key=f"map_{layer}_{c.get('company_id')}", use_container_width=True):
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
                val = {"status": f"估值暂不可用（{type(exc).__name__}）"}
        rows.append(
            {
                "代码": vt or cid,
                "公司": c.get("company_name"),
                "现价": val.get("price_display") or val.get("price") or "—",
                "市值": val.get("market_cap_display") or "—",
                "收入增速": _pct(earn.get("revenue_growth_yoy"), signed=True),
                "主要利润引擎": c.get("main_revenue_engine"),
                "云敞口": _zh_presence((c.get("strategic_presence") or {}).get("cloud")),
                "AI 基建敞口": _zh_presence((c.get("strategic_presence") or {}).get("infrastructure")),
                "AI 变现": _zh_monetization(c.get("ai_monetization_status")),
                "资本开支": _money(earn.get("capex")),
                "公允价值": val.get("fair_value_display") or "—",
                "估值状态": val.get("status") or "—",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("公允价值 / 估值状态来自现有「单股分析」，本页不重新计算估值。")

    st.markdown("##### 七巨头战略矩阵")
    strat = []
    for c in mag7_companies():
        sp = c.get("strategic_presence") or {}
        strat.append(
            {
                "公司": c.get("company_id"),
                "基础设施": _zh_presence(sp.get("infrastructure")),
                "云": _zh_presence(sp.get("cloud")),
                "模型/平台": _zh_presence(sp.get("model_platform")),
                "应用": _zh_presence(sp.get("applications")),
                "当前主利润": c.get("main_revenue_engine"),
                "下一步扩张": c.get("next_expansion"),
                "AI 资本开支强度": _zh_capex(c.get("ai_capex_intensity")),
            }
        )
    st.dataframe(pd.DataFrame(strat), use_container_width=True, hide_index=True)


def render_earnings_tab() -> None:
    labels = []
    for c in load_companies():
        if latest_earnings(c.get("company_id") or ""):
            labels.append(f"{c.get('company_id')} · {c.get('company_name')}")
    if not labels:
        st.warning("暂无财报快照数据。")
        return
    choice = st.selectbox("公司", labels, key="ind_earn_company")
    cid = _parse_company_option(choice)
    earn = latest_earnings(cid)
    if not earn:
        st.info("该公司尚无季度快照。")
        return
    st.markdown(
        f"**{cid}** · {earn.get('fiscal_period')} · 披露日 {earn.get('report_date')}  \n"
        f"来源：{', '.join(earn.get('source_urls') or [])}"
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("收入", _money(earn.get("total_revenue")), _pct(earn.get("revenue_growth_yoy"), signed=True))
    m2.metric("营业利润率", _pct(earn.get("operating_margin")))
    m3.metric(
        "资本开支",
        _money(earn.get("capex")),
        _pct(earn.get("capex_yoy"), signed=True) if earn.get("capex_yoy") is not None else None,
    )
    m4.metric("自由现金流", _money(earn.get("free_cash_flow")))
    if earn.get("capex_as_pct_revenue") is not None:
        st.caption(f"资本开支 / 收入：{_pct(earn.get('capex_as_pct_revenue'))}")

    segs = earn.get("segments") or []
    if segs:
        st.markdown("##### 收入构成")
        df = pd.DataFrame(
            [
                {
                    "分部": s.get("name"),
                    "收入": _money(s.get("revenue")),
                    "占总收入%": s.get("percentage_of_total"),
                    "同比": _pct(s.get("yoy_growth"), signed=True),
                }
                for s in segs
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
        chart_df = pd.DataFrame(
            {
                "分部": [s.get("name") for s in segs],
                "占比": [float(s.get("percentage_of_total") or 0) for s in segs],
            }
        ).set_index("分部")
        st.bar_chart(chart_df)
        st.caption(f"口径版本：`{earn.get('segment_schema_version')}` · 数据质量：`{earn.get('data_quality')}`")

    st.markdown("##### AI 基础设施资本开支对比（超大规模云厂商）")
    spend_rows = []
    for sid in ["MSFT", "GOOG", "AMZN", "META", "ORCL"]:
        e = latest_earnings(sid) or {}
        c = resolve_company(sid) or {}
        spend_rows.append(
            {
                "公司": sid,
                "资本开支": _money(e.get("capex")),
                "同比": _pct(e.get("capex_yoy"), signed=True) if e.get("capex_yoy") is not None else "—",
                "资本开支/收入": _pct(e.get("capex_as_pct_revenue")) if e.get("capex_as_pct_revenue") is not None else "—",
                "强度标签": _zh_capex(c.get("ai_capex_intensity")),
            }
        )
    st.dataframe(pd.DataFrame(spend_rows), use_container_width=True, hide_index=True)


def _share_table(market: str, title: str) -> None:
    st.markdown(f"##### {title}")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据。")
        return
    period = rows[0].get("period")
    st.caption(f"期间：{period} · 凡展示精确占比必须有来源")
    out = []
    for r in rows:
        share = r.get("share_pct")
        out.append(
            {
                "公司": r.get("company"),
                "份额": (
                    f"{float(share):.1f}%"
                    if share is not None
                    else (r.get("tier") or r.get("leader_status") or "不适用")
                ),
                "上期": f"{float(r['previous_share_pct']):.1f}%" if r.get("previous_share_pct") is not None else "—",
                "变动": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "排名": r.get("rank") if r.get("rank") is not None else "—",
                "来源": r.get("source"),
            }
        )
    st.dataframe(pd.DataFrame(out), use_container_width=True, hide_index=True)


def render_market_share_tab() -> None:
    _share_table("cloud_infrastructure", "云基础设施份额")
    _share_table("dram", "DRAM 份额")
    _share_table("hbm", "HBM（仅排名/领先地位，不编造精确占比）")
    st.markdown("##### AI 加速器生态（非伪市场份额饼图）")
    eco = load_accelerator_ecosystem()
    zh_rows = []
    for row in eco:
        zh_rows.append(
            {
                "名称": row.get("name"),
                "公司ID": row.get("company_id"),
                "产品": row.get("product"),
                "外部市场": "是" if row.get("external_market") else "否",
                "仅内部": "是" if row.get("internal_only") else "否",
                "商用芯片": "是" if row.get("merchant_chip") else "否",
                "云厂商专用": "是" if row.get("cloud_specific") else "否",
                "收入状态": row.get("current_revenue_status"),
                "来源": row.get("source"),
            }
        )
    st.dataframe(pd.DataFrame(zh_rows), use_container_width=True, hide_index=True)
    st.caption("区分商用芯片与内部/云专用芯片。无可靠来源时不展示 NVDA/AMD 精确份额。")


def render_infrastructure_tab() -> None:
    infra = [
        c
        for c in load_companies()
        if c.get("primary_layer") == "infrastructure"
        or ((c.get("layer_presence") or {}).get("infrastructure") or {}).get("stars", 0) >= 3
    ]
    rows = []
    for c in infra:
        p = (c.get("layer_presence") or {}).get("infrastructure") or {}
        rows.append(
            {
                "公司": c.get("company_id"),
                "名称": c.get("company_name"),
                "存在感": stars_to_text(int(p.get("stars") or 0)),
                "盈利标签": PROFIT_TAGS.get(str(p.get("profit_tag") or ""), p.get("profit_tag")),
                "主引擎": c.get("main_revenue_engine"),
                "AI 变现": _zh_monetization(c.get("ai_monetization_status")),
                "进入估值？": "是" if c.get("include_in_valuation") else "仅作产业参考",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    _share_table("dram", "存储份额")
    _share_table("hbm", "HBM 排名")


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
                "公司": c.get("company_id"),
                "名称": c.get("company_name"),
                "存在感": stars_to_text(int(p.get("stars") or 0)),
                "盈利标签": PROFIT_TAGS.get(str(p.get("profit_tag") or ""), p.get("profit_tag")),
                "主引擎": c.get("main_revenue_engine"),
                "AI 变现": _zh_monetization(c.get("ai_monetization_status")),
                "下一步扩张": c.get("next_expansion"),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_events_tab() -> None:
    range_label = st.selectbox("时间范围", ["本季度至今", "近30天", "近90天", "年初至今"], key="ind_event_range")
    key_map = {
        "本季度至今": "current_quarter",
        "近30天": "30D",
        "近90天": "90D",
        "年初至今": "YTD",
    }
    rk = key_map[range_label]
    labels = _company_select_options()
    choice = st.selectbox("公司", labels, key="ind_event_company")
    cid = _parse_company_option(choice)
    evs = events_for(cid, limit=8, range_key=rk)
    if not evs:
        st.info("所选范围内暂无重大事件。")
        return
    for ev in evs:
        with st.container(border=True):
            st.markdown(
                f"**{ev.get('event_date')}** · `{_zh_impact(ev.get('impact_label'))}` · {_zh_event_type(ev.get('event_type'))}  \n"
                f"{ev.get('headline')}"
            )
            st.caption(ev.get("summary") or "")
            st.caption(
                f"影响：{ev.get('strategic_impact') or '—'} · 来源：{ev.get('source_name') or ev.get('source_url')}"
            )


def render_company_detail(company_id: str, valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    c = resolve_company(company_id)
    if not c:
        st.error("未找到该公司。")
        return
    st.markdown(f"### {c.get('company_name')}（{c.get('company_id')}）")
    st.caption(
        f"主层级：**{LAYER_SHORT.get(c.get('primary_layer'), c.get('primary_layer'))}** · "
        f"AI 变现：**{_zh_monetization(c.get('ai_monetization_status'))}** · "
        f"{'上市公司' if c.get('public_private') == 'public' else '非上市参考公司'}"
    )
    left, right = st.columns([2, 1])
    with left:
        st.markdown("**在 AI 栈中的角色**")
        for role in c.get("industry_roles") or []:
            st.write(f"- {role}")
        st.markdown("**当前利润层** vs **未来扩张层**")
        st.write(
            {
                "当前利润层": _zh_layers(c.get("current_profit_layers")),
                "未来扩张层": _zh_layers(c.get("future_expansion_layers")),
            }
        )
        presence_rows = []
        for layer in LAYER_MAP_ORDER[::-1]:
            p = (c.get("layer_presence") or {}).get(layer) or {}
            presence_rows.append(
                {
                    "层级": LAYER_SHORT.get(layer),
                    "存在感": stars_to_text(int(p.get("stars") or 0)),
                    "标签": PROFIT_TAGS.get(str(p.get("profit_tag") or ""), ""),
                    "备注": p.get("note") or "",
                }
            )
        st.dataframe(pd.DataFrame(presence_rows), use_container_width=True, hide_index=True)

        earn = latest_earnings(c.get("company_id"))
        if earn:
            st.markdown(f"**最新财报** · {earn.get('fiscal_period')}")
            segs = earn.get("segments") or []
            if segs:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "分部": s.get("name"),
                                "收入": _money(s.get("revenue")),
                                "占比%": s.get("percentage_of_total"),
                                "同比": _pct(s.get("yoy_growth"), signed=True),
                            }
                            for s in segs
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            st.caption(f"来源：{', '.join(earn.get('source_urls') or [])}")

        st.markdown("**近期重大事件**")
        for ev in events_for(c.get("company_id"), limit=5, range_key="90D"):
            st.write(
                f"- {ev.get('event_date')}：{ev.get('headline')}（`{_zh_impact(ev.get('impact_label'))}`）"
            )

    with right:
        vt = valuation_ticker_for(c.get("company_id"))
        if vt and valuation_loader:
            try:
                val = valuation_loader(vt) or {}
            except Exception as exc:
                val = {"status": f"暂不可用（{type(exc).__name__}）"}
            st.markdown("**当前估值摘要**")
            st.write(
                {
                    "代码": vt,
                    "现价": val.get("price_display") or val.get("price"),
                    "公允价值": val.get("fair_value_display"),
                    "状态": val.get("status"),
                    "置信度": val.get("confidence"),
                }
            )
            if st.button("打开单股分析", type="primary", key=f"open_sa_{vt}"):
                _open_stock_analysis(vt)
        elif not vt:
            st.info("参考公司 — 不接入单股估值。")
        else:
            st.caption("本会话估值加载器不可用。")

        st.markdown("**市场份额位置**")
        hits = []
        for market in ("cloud_infrastructure", "dram", "hbm", "ai_accelerator"):
            for r in market_share_rows(market):
                if str(r.get("company_id") or "").upper() == str(c.get("company_id")).upper():
                    hits.append(
                        {
                            "市场": MARKET_ZH.get(market, market),
                            "份额": r.get("share_pct"),
                            "排名": r.get("rank"),
                            "说明": r.get("leader_status") or r.get("tier"),
                            "来源": r.get("source"),
                        }
                    )
        if hits:
            st.dataframe(pd.DataFrame(hits), use_container_width=True, hide_index=True)
        else:
            st.caption("该公司暂无带来源的市场份额记录。")


def render_industry_page(valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    st.subheader(f"{PAGE_TITLE}情报")
    _freshness_banner()

    if st.session_state.pop("industry_force_detail", None) and st.session_state.get("industry_detail_id"):
        default_tab = "公司详情"
    else:
        default_tab = "产业链地图"

    tabs = [
        "产业链地图",
        "七巨头",
        "财报与收入构成",
        "市场份额",
        "基础设施",
        "应用层",
        "重大事件",
        "公司详情",
    ]
    if hasattr(st, "segmented_control"):
        tab = (
            st.segmented_control(
                "产业页签",
                tabs,
                default=default_tab if default_tab in tabs else tabs[0],
                key="industry_tab",
            )
            or tabs[0]
        )
    else:
        tab = st.radio("产业页签", tabs, horizontal=True, key="industry_tab")

    if tab == "产业链地图":
        render_industry_map_tab()
    elif tab == "七巨头":
        render_mag7_tab(valuation_loader)
    elif tab == "财报与收入构成":
        render_earnings_tab()
    elif tab == "市场份额":
        render_market_share_tab()
    elif tab == "基础设施":
        render_infrastructure_tab()
    elif tab == "应用层":
        render_applications_tab()
    elif tab == "重大事件":
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
        choice = st.selectbox("公司", labels, index=idx, key="ind_detail_select")
        render_company_detail(_parse_company_option(choice), valuation_loader)

    st.divider()
    e1, e2, e3 = st.columns(3)
    e1.button("导出产业链地图", disabled=True, help="V5.5 待做")
    e2.button("导出公司卡片", disabled=True, help="V5.5 待做")
    e3.button("导出七巨头摘要", disabled=True, help="V5.5 待做")
    with st.expander("PPT 用 JSON 预览（导出占位）", expanded=False):
        payload = build_industry_map_export()
        st.json(
            {
                "schema_version": payload.get("schema_version"),
                "层级数": len(payload.get("layers") or []),
                "公司数": len(payload.get("companies") or []),
                "市场份额条数": len(payload.get("market_share") or []),
                "事件条数": len(payload.get("events") or []),
            }
        )
