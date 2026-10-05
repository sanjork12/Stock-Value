"""V5.2.1 Industry views — panorama map + compact market landscape (中文 UI)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Sequence

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

# 角色展示（公司名保留原文；角色说明用中文）
_COMPUTE_ROLES = (
    ("NVDA", "AI 加速芯片"),
    ("AVGO", "网络 / 定制硅"),
    ("ANET", "网络设备"),
    ("Google TPU", "内部 / 云自研"),
    ("AWS Trainium", "内部 / 云自研"),
)

_HBM_ROLE_SHORT = {
    "SK hynix": "领先者",
    "Samsung": "主要供应商",
    "Micron": "挑战者",
}


def _pp(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.1f} 百分点"


def _source_zh(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    mapping = {
        "Synergy Research Group / Canalys industry reports (curated)": "Synergy / Canalys 行业报告（整理）",
        "Industry reports often fold Oracle into Others; do not invent precise %": "行业报告常将 Oracle 并入「其他」；不编造精确份额",
        "Residual after AWS/Azure/GCP curated shares": "AWS/Azure/GCP 整理份额后的残差",
        "TrendForce DRAM supplier revenue share (curated)": "TrendForce DRAM 供应商收入份额（整理）",
        "Residual after top-3 curated shares": "前三名整理份额后的残差",
        "Industry commentary / company disclosures (rank-level; no precise % invented)": "行业评述 / 公司披露（仅排名，不编造精确份额）",
        "Industry commentary (rank-level)": "行业评述（仅排名）",
        "Micron IR HBM commentary + industry notes (rank-level)": "美光投资者关系 HBM 评述 + 行业笔记（仅排名）",
        "Company disclosures + industry commentary — precise merchant share % not asserted without primary source table": "公司披露 + 行业评述（无一手份额表时不给出精确商用份额）",
        "Company IR (no standardized industry share table used)": "公司投资者关系（无标准化行业份额表）",
    }
    return mapping.get(text, text)


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


def _share_chart_and_table(market: str, title: str) -> None:
    """云计算 / DRAM：横向条形图 + 公司/份额/变化/排名简表。"""
    st.markdown(f"**{title}**")
    rows = market_share_rows(market)
    if not rows:
        st.caption("暂无数据")
        return

    numeric = [r for r in rows if r.get("share_pct") is not None]
    if numeric:
        cdf = pd.DataFrame(
            {
                "公司": [str(r.get("company") or "") for r in numeric],
                "份额%": [float(r["share_pct"]) for r in numeric],
            }
        )
        try:
            st.bar_chart(cdf, x="份额%", y="公司", horizontal=True, height=220)
        except TypeError:
            st.bar_chart(cdf.set_index("公司")["份额%"], height=220)

    table_rows = []
    sources = []
    for r in rows:
        share = r.get("share_pct")
        tier = r.get("tier")
        share_txt = f"{float(share):.1f}%" if share is not None else (
            str(tier) if tier else "未单独披露"
        )
        table_rows.append(
            {
                "公司": r.get("company"),
                "份额": share_txt,
                "变化": _pp(r.get("change_pp")) if r.get("change_pp") is not None else "—",
                "排名": r.get("rank") if r.get("rank") is not None else "—",
                "来源": _source_zh(r.get("source")),
            }
        )
        src = _source_zh(r.get("source"))
        if src and src != "—" and src not in sources:
            sources.append(src)
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    if sources:
        st.caption("来源：" + "；".join(sources[:3]))


def _hbm_role_list() -> None:
    """HBM：仅定性角色，不编造百分比。"""
    st.markdown("**存储 · HBM**")
    rows = market_share_rows("hbm")
    if not rows:
        for name, role in (
            ("SK hynix", "领先者"),
            ("Samsung", "主要供应商"),
            ("Micron", "挑战者"),
        ):
            st.markdown(f"**{name}** — {role}")
        return
    for r in sorted(rows, key=lambda x: (x.get("rank") is None, x.get("rank") or 99)):
        company = str(r.get("company") or "")
        if not company or company.lower() == "none":
            continue
        role = _HBM_ROLE_SHORT.get(company)
        if not role:
            raw = str(r.get("leader_status") or "")
            if "Leader" in raw or "#1" in raw:
                role = "领先者"
            elif "Major" in raw:
                role = "主要供应商"
            elif "challenger" in raw.lower() or "Challenger" in raw:
                role = "挑战者"
            else:
                role = "—"
        st.markdown(f"**{company}** — {role}")


def _compute_role_list() -> None:
    """AI 算力 / 网络角色列表。"""
    st.markdown("**AI 算力 / 网络**")
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
        _share_chart_and_table("cloud_infrastructure", "云计算")
    if show_memory_module(watch):
        any_mod = True
        _share_chart_and_table("dram", "存储 · DRAM")
        _hbm_role_list()
    if show_compute_module(watch):
        any_mod = True
        _compute_role_list()
    if not any_mod:
        st.info("当前自选股暂无关联的云计算 / 存储 / AI 算力市场格局模块。")


def _footer_meta() -> None:
    meta = load_meta()
    period = meta.get("data_through") or "—"
    refreshed = str(meta.get("last_refreshed_at") or "—")[:10]
    note = meta.get("market_share_note") or ""
    policy = meta.get("update_policy") or ""
    disclaimer = meta.get("disclaimer") or "仅供产业研究参考，不构成投资建议。"
    with st.expander("数据说明", expanded=False):
        st.caption(f"数据周期：{period}")
        st.caption(f"最近更新：{refreshed}")
        if note:
            st.caption(note)
        if policy:
            st.caption(policy)
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
