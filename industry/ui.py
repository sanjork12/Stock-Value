"""AI 产业链页：仅展示全景图。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

import streamlit as st

_PANORAMA = Path(__file__).resolve().parent.parent / "assets" / "ai_industry_panorama.jpg"


def render_industry_page(valuation_loader: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    del valuation_loader  # 本页不再接入估值摘要
    st.subheader("AI 产业链全景图")
    st.caption("从基础设施到应用的完整生态 · 仅供研究参考，不构成投资建议")
    if not _PANORAMA.exists():
        st.error(f"未找到全景图文件：`{_PANORAMA}`")
        return
    st.image(str(_PANORAMA), use_container_width=True)
