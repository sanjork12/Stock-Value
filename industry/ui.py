"""V5.2.2 Industry views — panorama map + compact market landscape charts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import altair as alt
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

# Investment-facing display order (named players first, residual last).
_CLOUD_ORDER = ("AWS", "Azure", "Google Cloud", "Others", "其他")
_DRAM_ORDER = ("Samsung", "SK hynix", "Micron", "Others", "其他")

_COMPUTE_ROLES = (
    ("NVIDIA", "Merchant AI accelerator"),
    ("Broadcom", "Networking / Custom silicon"),
    ("Arista", "Data-center networking"),
    ("Google TPU", "Internal / Cloud"),
    ("AWS Trainium", "Internal / Cloud"),
    ("Meta MTIA", "Internal"),
)

_HBM_ROLES = (
    ("SK hynix", "Leader"),
    ("Samsung", "Major supplier"),
    ("Micron", "Challenger"),
)

_HBM_ROLE_FALLBACK = {
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


def _pct_txt(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _display_company(name: Any) -> str:
    raw = str(name or "").strip()
    if raw in {"其他", "Others"}:
        return "Others"
    return raw or "—"


def _is_oracle(row: Dict[str, Any]) -> bool:
    company = str(row.get("company") or "").strip().lower()
    cid = str(row.get("company_id") or "").strip().upper()
    return company == "oracle" or cid == "ORCL"


def _has_numeric_share(row: Dict[str, Any]) -> bool:
    return row.get("share_pct") is not None


def format_period_label(period: Any) -> str:
    """CY2025 Q2 / FY2025 Q2 → 2025 Q2 (display only; does not alter source data)."""
    text = str(period or "").strip()
    if not text:
        return "—"
    cleaned = (
        text.replace("CY", "")
        .replace("FY", "")
        .replace("  ", " ")
        .strip()
    )
    return cleaned or text


def period_for_market(market: str, rows: Optional[List[Dict[str, Any]]] = None) -> str:
    rows = rows if rows is not None else market_share_rows(market)
    for r in rows:
        if r.get("period"):
            return format_period_label(r.get("period"))
    return "—"


def chart_rows_for_market(market: str, rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Numeric share rows for bar chart only — excludes Oracle / null share_pct."""
    rows = rows if rows is not None else market_share_rows(market)
    out: List[Dict[str, Any]] = []
    for r in rows:
        if _is_oracle(r):
            continue
        if not _has_numeric_share(r):
            continue
        out.append(
            {
                "公司": _display_company(r.get("company")),
                "份额": float(r["share_pct"]),
                "rank": r.get("rank"),
            }
        )
    order = _CLOUD_ORDER if market == "cloud_infrastructure" else _DRAM_ORDER
    rank = {name: i for i, name in enumerate(order)}

    def _key(item: Dict[str, Any]):
        name = str(item.get("公司") or "")
        if name in rank:
            return (0, rank[name])
        # Unknown named players: by share desc, then rank.
        return (1, -(float(item.get("份额") or 0)), item.get("rank") or 999)

    out.sort(key=_key)
    return out


def table_rows_for_market(market: str, rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Minimal table: 公司 / 当前份额 / 上季份额 / QoQ变化 / 排名."""
    rows = rows if rows is not None else market_share_rows(market)
    out: List[Dict[str, Any]] = []
    for r in rows:
        company = _display_company(r.get("company"))
        if _is_oracle(r):
            out.append(
                {
                    "公司": "Oracle",
                    "当前份额": "Tier 2 / not separately disclosed",
                    "上季份额": "—",
                    "QoQ变化": "—",
                    "排名": "—",
                }
            )
            continue
        if not _has_numeric_share(r) and not r.get("tier"):
            # Skip pure qualitative rows that belong to other modules (e.g. HBM).
            if market in {"cloud_infrastructure", "dram"}:
                continue
        out.append(
            {
                "公司": company,
                "当前份额": _pct_txt(r.get("share_pct")),
                "上季份额": _pct_txt(r.get("previous_share_pct")),
                "QoQ变化": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "排名": r.get("rank") if r.get("rank") is not None else "—",
            }
        )
    # Stable display: chart order for numeric, Oracle after named, residual last.
    order = list(_CLOUD_ORDER if market == "cloud_infrastructure" else _DRAM_ORDER)
    order_rank = {name: i for i, name in enumerate(order)}

    def _tkey(item: Dict[str, Any]):
        name = str(item.get("公司") or "")
        if name == "Oracle":
            return (2, 0)
        if name in order_rank:
            return (0, order_rank[name])
        return (1, name)

    out.sort(key=_tkey)
    return out


def collect_sources(rows: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for r in rows:
        src = str(r.get("source") or "").strip()
        if not src:
            continue
        if src not in seen:
            seen.append(src)
    return seen


def hbm_role_rows(rows: Optional[List[Dict[str, Any]]] = None) -> List[Tuple[str, str]]:
    """Ranking / role only — never invent share_pct."""
    rows = rows if rows is not None else market_share_rows("hbm")
    if not rows:
        return list(_HBM_ROLES)
    out: List[Tuple[str, str]] = []
    for r in sorted(rows, key=lambda x: (x.get("rank") is None, x.get("rank") or 99)):
        company = str(r.get("company") or "").strip()
        if not company or company.lower() == "none":
            continue
        role = _HBM_ROLE_FALLBACK.get(company)
        if not role:
            raw = str(r.get("leader_status") or "")
            if "Leader" in raw or "领先" in raw or "#1" in raw or "第一" in raw:
                role = "Leader"
            elif "Major" in raw or "主要" in raw:
                role = "Major supplier"
            elif "challenger" in raw.lower() or "挑战" in raw:
                role = "Challenger"
            else:
                role = raw or "—"
        out.append((company, role))
    return out or list(_HBM_ROLES)


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


def _horizontal_share_chart(chart_rows: List[Dict[str, Any]], *, height: int = 180) -> None:
    """Horizontal bars, company labels left (no rotation), % at bar end."""
    if not chart_rows:
        return
    df = pd.DataFrame(chart_rows)
    # Preserve explicit order from chart_rows_for_market.
    order = list(df["公司"])
    max_share = float(df["份额"].max()) if len(df) else 40.0
    domain_max = max(40.0, max_share * 1.18)

    base = alt.Chart(df).encode(
        y=alt.Y(
            "公司:N",
            sort=order,
            title=None,
            axis=alt.Axis(labelLimit=160, labelAngle=0, ticks=False, domain=False),
        ),
        x=alt.X(
            "份额:Q",
            title=None,
            scale=alt.Scale(domain=[0, domain_max]),
            axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False),
        ),
    )
    bars = base.mark_bar(cornerRadiusEnd=3, color="#4F86C6").encode(
        tooltip=[
            alt.Tooltip("公司:N", title="公司"),
            alt.Tooltip("份额:Q", title="份额", format=".1f"),
        ]
    )
    label_df = df.copy()
    label_df["标签"] = [f"{float(v):.1f}%" for v in label_df["份额"]]
    labels = (
        alt.Chart(label_df)
        .mark_text(align="left", baseline="middle", dx=6, fontSize=12, color="#1f2937")
        .encode(
            y=alt.Y("公司:N", sort=order, title=None),
            x=alt.X("份额:Q", scale=alt.Scale(domain=[0, domain_max])),
            text="标签:N",
        )
    )
    chart = (
        (bars + labels)
        .properties(height=height, padding={"left": 4, "right": 28, "top": 4, "bottom": 4})
        .configure_view(strokeWidth=0)
        .configure_axis(labelFontSize=12)
    )
    st.altair_chart(chart, use_container_width=True)


def _module_source_line(period: str, sources: List[str], *, key: str) -> None:
    del key
    st.caption(f"数据：{period} · 来源")
    with st.expander("来源详情", expanded=False):
        if sources:
            for s in sources:
                st.caption(s)
        else:
            st.caption("—")


def _share_module(market: str, title_prefix: str) -> None:
    """Title + period → horizontal chart → minimal table → compact source."""
    rows = market_share_rows(market)
    period = period_for_market(market, rows)
    st.markdown(f"**{title_prefix} · {period}**")

    chart_rows = chart_rows_for_market(market, rows)
    _horizontal_share_chart(chart_rows, height=44 * max(len(chart_rows), 1) + 16)

    if market == "cloud_infrastructure" and any(_is_oracle(r) for r in rows):
        st.caption("Oracle：公开市场份额通常未单独披露")

    table = table_rows_for_market(market, rows)
    if table:
        st.dataframe(
            pd.DataFrame(table),
            use_container_width=True,
            hide_index=True,
            height=38 * (len(table) + 1),
        )

    sources = collect_sources(rows)
    _module_source_line(period, sources, key=f"src_{market}")


def _hbm_role_list() -> None:
    """HBM：仅定性角色，不画百分比 bar、不编造份额。"""
    rows = market_share_rows("hbm")
    period = period_for_market("hbm", rows)
    st.markdown(f"**HBM Market Share · {period}**")
    # Hard rule: no % chart when share_pct is missing.
    if any(_has_numeric_share(r) for r in rows):
        # Still do not invent — only chart true numeric shares if present.
        numeric = chart_rows_for_market("hbm", rows)
        if numeric:
            _horizontal_share_chart(numeric, height=44 * len(numeric) + 16)
    for name, role in hbm_role_rows(rows):
        st.markdown(f"**{name}** — {role}")
    sources = collect_sources(rows)
    _module_source_line(period, sources, key="src_hbm")


def _compute_role_list() -> None:
    """AI Compute / Networking — role list only; never show None / empty table."""
    st.markdown("**AI Compute / Networking**")
    for name, role in _COMPUTE_ROLES:
        if not name or str(name).lower() == "none":
            continue
        if not role or str(role).lower() == "none":
            continue
        st.markdown(f"**{name}** — {role}")


def render_tab_landscape(watch: List[str]) -> None:
    """市场格局 — 按自选股动态显示模块。"""
    if not watch:
        _empty_watchlist_message()
        return
    any_mod = False
    if show_cloud_module(watch):
        any_mod = True
        _share_module("cloud_infrastructure", "Cloud Market Share")
    if show_memory_module(watch):
        any_mod = True
        _share_module("dram", "DRAM Market Share")
        _hbm_role_list()
    if show_compute_module(watch):
        any_mod = True
        _compute_role_list()
    if not any_mod:
        st.info("当前自选股暂无关联的云计算 / 存储 / AI 算力市场格局模块。")


def _footer_meta() -> None:
    meta = load_meta()
    refreshed = str(meta.get("last_refreshed_at") or "—")[:10]
    disclaimer = meta.get("disclaimer") or "仅供产业研究参考，不构成投资建议。"
    with st.expander("数据说明", expanded=False):
        st.caption(f"最近更新：{refreshed}")
        st.caption(disclaimer)


def render_industry_page(
    valuation_loader: Optional[Any] = None,
    watchlist_tickers: Optional[Sequence[Any]] = None,
    mode: str = "map",
) -> None:
    del valuation_loader
    watch = normalize_watchlist_tickers(watchlist_tickers)
    key = str(mode or "map").strip().lower()
    if key in {"landscape", "市场格局"}:
        render_tab_landscape(watch)
    else:
        render_tab_map(watch)
    _footer_meta()
