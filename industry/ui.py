"""V5.2.2 Industry views — panorama map + latest-quarter market snapshot."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from industry.loader import (
    load_meta,
    load_market_snapshot,
    market_snapshot_block,
    normalize_watchlist_tickers,
    show_cloud_module,
    show_memory_module,
)

_PANORAMA = Path(__file__).resolve().parent.parent / "assets" / "ai_industry_panorama.jpg"

# Named players first; Others last. Oracle never appears in percentage charts.
_CLOUD_ORDER = ("AWS", "Microsoft", "Google Cloud", "Others")
_DRAM_ORDER = ("Samsung", "SK hynix", "Micron", "Others")

_QOQ_SHORT = {
    "Google Cloud": "Google",
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


def _is_others(name: Any) -> bool:
    return str(name or "").strip().lower() in {"others", "其他"}


def _is_oracle_name(name: Any) -> bool:
    return str(name or "").strip().lower() == "oracle"


def snapshot_chart_rows(block: Dict[str, Any], *, order: Sequence[str]) -> List[Dict[str, Any]]:
    """Percentage bar inputs from snapshot companies — excludes Oracle / null share."""
    companies = list(block.get("companies") or [])
    out: List[Dict[str, Any]] = []
    for c in companies:
        name = str(c.get("name") or "").strip()
        if not name or _is_oracle_name(name):
            continue
        if c.get("share") is None:
            continue
        out.append({"公司": name, "份额": float(c["share"]), "rank": c.get("rank")})
    rank = {n: i for i, n in enumerate(order)}

    def _key(item: Dict[str, Any]):
        name = str(item.get("公司") or "")
        if name in rank:
            return (0, rank[name])
        return (1, -(float(item.get("份额") or 0)), item.get("rank") or 999)

    out.sort(key=_key)
    return out


def snapshot_table_rows(block: Dict[str, Any], *, order: Sequence[str]) -> List[Dict[str, Any]]:
    companies = list(block.get("companies") or [])
    out: List[Dict[str, Any]] = []
    for c in companies:
        name = str(c.get("name") or "").strip()
        if not name or _is_oracle_name(name):
            continue
        out.append(
            {
                "公司": name,
                "当前份额": _pct_txt(c.get("share")),
                "上季份额": _pct_txt(c.get("previous_share")),
                "QoQ变化": _pp(c.get("change_pp")) if c.get("change_pp") is not None else "—",
                "排名": c.get("rank") if c.get("rank") is not None else "—",
            }
        )
    rank = {n: i for i, n in enumerate(order)}
    out.sort(key=lambda r: (0, rank[r["公司"]]) if r["公司"] in rank else (1, r["公司"]))
    return out


def snapshot_qoq_summary(block: Dict[str, Any], *, order: Sequence[str]) -> List[Tuple[str, str]]:
    """One-line QoQ chips for named players (exclude Others / Oracle)."""
    by_name = {str(c.get("name") or ""): c for c in (block.get("companies") or [])}
    out: List[Tuple[str, str]] = []
    for name in order:
        if _is_others(name) or _is_oracle_name(name):
            continue
        c = by_name.get(name)
        if not c or c.get("change_pp") is None:
            continue
        label = _QOQ_SHORT.get(name, name)
        out.append((label, _pp(c.get("change_pp"))))
    return out


def snapshot_hbm_roles(block: Optional[Dict[str, Any]] = None) -> List[Tuple[str, str]]:
    block = block if block is not None else market_snapshot_block("hbm")
    roles = block.get("roles") or []
    out: List[Tuple[str, str]] = []
    for r in roles:
        name = str(r.get("name") or "").strip()
        role = str(r.get("role") or "").strip()
        if not name or name.lower() == "none":
            continue
        if not role or role.lower() == "none":
            continue
        # Never invent percentages for HBM.
        if r.get("share") is not None:
            continue
        out.append((name, role))
    return out


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
    if not chart_rows:
        return
    df = pd.DataFrame(chart_rows)
    order = list(df["公司"])
    max_share = float(df["份额"].max()) if len(df) else 40.0
    domain_max = max(40.0, max_share * 1.18)

    bars = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3, color="#4F86C6")
        .encode(
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
            tooltip=[
                alt.Tooltip("公司:N", title="公司"),
                alt.Tooltip("份额:Q", title="份额", format=".1f"),
            ],
        )
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


def _module_source(block: Dict[str, Any]) -> None:
    period = str(block.get("period") or "—")
    st.caption(f"数据：{period} · 来源")
    with st.expander("来源详情", expanded=False):
        st.caption(str(block.get("source") or "—"))
        url = str(block.get("source_url") or "").strip()
        if url:
            st.caption(url)
        for note in block.get("notes") or []:
            st.caption(str(note))


def _share_snapshot_module(key: str, title_prefix: str, order: Sequence[str]) -> None:
    block = market_snapshot_block(key)
    if not block:
        st.caption(f"{title_prefix}：暂无快照数据")
        return
    period = str(block.get("period") or "—")
    st.markdown(f"**{title_prefix} · {period}**")

    chart_rows = snapshot_chart_rows(block, order=order)
    _horizontal_share_chart(chart_rows, height=44 * max(len(chart_rows), 1) + 16)

    qoq = snapshot_qoq_summary(block, order=order)
    if qoq:
        st.caption("　".join(f"{name} {chg}" for name, chg in qoq))

    if key == "cloud":
        st.caption("Oracle：公开市场份额通常未单独披露。")

    table = snapshot_table_rows(block, order=order)
    if table:
        st.dataframe(
            pd.DataFrame(table),
            use_container_width=True,
            hide_index=True,
            height=38 * (len(table) + 1),
        )
    _module_source(block)


def _hbm_snapshot_module() -> None:
    block = market_snapshot_block("hbm")
    period = str(block.get("period") or "—")
    st.markdown(f"**HBM Competitive Position · {period}**")
    roles = snapshot_hbm_roles(block)
    if not roles:
        st.caption("暂无 HBM 角色数据")
    for name, role in roles:
        st.markdown(f"**{name}** — {role}")
    _module_source(block)


def render_tab_landscape(watch: List[str]) -> None:
    """市场格局 — latest-quarter Cloud / DRAM / HBM snapshot only."""
    # Ensure JSON is loadable (UI reads snapshot, not hard-coded shares).
    _ = load_market_snapshot()
    if not watch:
        _empty_watchlist_message()
        return
    any_mod = False
    if show_cloud_module(watch):
        any_mod = True
        _share_snapshot_module("cloud", "Cloud Market Share", _CLOUD_ORDER)
    if show_memory_module(watch):
        any_mod = True
        _share_snapshot_module("dram", "DRAM Market Share", _DRAM_ORDER)
        _hbm_snapshot_module()
    if not any_mod:
        st.info("当前自选股暂无关联的云计算 / 存储市场格局模块。")


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
