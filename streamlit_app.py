from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import os
import traceback

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="股票公允价值监控",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Compact app chrome (toolbar-like header, less landing-page whitespace)
st.markdown(
    """
<style>
  h1 {
    font-size: 1.75rem !important; /* ~28px */
    line-height: 1.2 !important;
    margin: 0.15rem 0 0.35rem 0 !important;
    padding: 0 !important;
  }
  div[data-testid="stVerticalBlockBorderWrapper"] {
    margin-top: 0.25rem !important;
  }
  div[data-testid="stMetric"] {
    background: transparent;
  }
</style>
""",
    unsafe_allow_html=True,
)

try:
    import extra_streamlit_components as stx
    from supabase import create_client, Client

    from mag7_monitor import (
        add_indicators,
        get_history,
        get_live_fundamentals,
        fnum,
    )
    from finnhub_admin_diagnostics import is_cloud_runtime, verified_admin, render_diagnostics
    from financial_forensics_admin import render_financial_diagnostics
    from peer_diagnostic_admin import render_peer_diagnostics
    from production_snapshot_admin import render_snapshot_export
    from market_reference_provider import format_consensus_target
    from analysis_service import (
        analyze_ticker,
        build_snapshot_record,
        fetch_historical_snapshot,
        format_fair_value,
        is_schema_cache_error,
        legacy_snapshot_record,
    )
    from remember_session import seal_remember_payload, unseal_remember_payload
    from valuation_engine import (
        MODEL_DISPLAY_NAMES,
        MODEL_VERSION,
        is_legacy_snapshot,
        normalize_ticker,
        primary_valuation_view,
    )
except Exception as _boot_exc:
    st.error(f"应用启动失败：{type(_boot_exc).__name__}: {_boot_exc}")
    st.code(traceback.format_exc())
    st.stop()

# V5 industry layer — optional so core Stock Analysis still boots if deploy is mid-update.
try:
    from analysis_service import industry_valuation_snapshot
    from industry.ui import render_industry_page

    _INDUSTRY_MAP_AVAILABLE = True
    _INDUSTRY_IMPORT_ERROR = None
except Exception as _industry_exc:
    industry_valuation_snapshot = None  # type: ignore[assignment]
    render_industry_page = None  # type: ignore[assignment]
    _INDUSTRY_MAP_AVAILABLE = False
    _INDUSTRY_IMPORT_ERROR = _industry_exc

logger = logging.getLogger("stock_fair_value_monitor")

# Industry second-level tabs promoted into top nav (no nested industry menu).
NAV_PAGES = ["产业链地图", "市场格局", "自选股", "单股分析", "头等大事"]
# V5.3: single-stock is one continuous page — no second-level tabs.
SINGLE_STOCK_TABS: list[str] = []
REMEMBER_COOKIE = "stock_monitor_refresh"
REMEMBER_DAYS = 30
_LEGACY_NAV = {
    "AI产业链": "产业链地图",
    "AI 产业链": "产业链地图",
    "AI Industry Map": "产业链地图",
    "历史快照": "单股分析",
    "账户": "自选股",
}


def format_trim_zone(exit_zone: dict | None) -> str:
    """Dashboard/single-stock formatter; precise prices only when Exit Reliability Guard allows."""
    if not isinstance(exit_zone, dict):
        return "—"
    mode = exit_zone.get("display_mode")
    if mode and mode != "precise":
        return "—"
    if exit_zone.get("eligible_for_precise_exit") is False:
        return "—"
    trim = fnum(exit_zone.get("trim_price"))
    extreme = fnum(exit_zone.get("extreme_price"))
    if trim is None or extreme is None:
        return "—"
    return f"${trim:,.0f} - ${extreme:,.0f}"


def format_extreme_zone(exit_zone: dict | None) -> str:
    if not isinstance(exit_zone, dict):
        return "—"
    mode = exit_zone.get("display_mode")
    if mode and mode != "precise":
        return "—"
    if exit_zone.get("eligible_for_precise_exit") is False:
        return "—"
    extreme = fnum(exit_zone.get("extreme_price"))
    if extreme is None:
        return "—"
    return f">${extreme:,.0f}"


def inject_layout_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="stSidebarCollapsedControl"] {display: none;}
        [data-testid="stHeader"] {background: transparent;}
        .block-container {
            padding-top: 0.55rem;
            padding-bottom: 0.6rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
            max-width: 100%;
        }
        div[data-testid="stVerticalBlock"] > div { gap: 0.35rem; }
        h1, h2, h3 { margin-top: 0.15rem !important; margin-bottom: 0.25rem !important; }
        div[data-testid="stPopover"] > button {
            min-height: 2.1rem;
            padding: 0.15rem 0.55rem;
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.85rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_layout_css()

NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "AMZN": "Amazon",
    "NVDA": "Nvidia",
    "META": "Meta",
    "TSLA": "Tesla",
    "AVGO": "Broadcom",
    "MU": "Micron",
    "JPM": "JPMorgan",
    "PLTR": "Palantir",
    "COIN": "Coinbase",
    "BMNR": "BitMine",
    "TEM": "Tempus AI",
    "SPCX": "SPCX",
    "UBER": "Uber",
    "NFLX": "Netflix",
    "BABA": "Alibaba",
    "ORCL": "Oracle",
}

STATUS_META = {
    "深度价值区": ("#DCFCE7", "#166534", "🟢"),
    "核心买入区": ("#D1FAE5", "#047857", "🟢"),
    "第一批区": ("#FEF3C7", "#92400E", "🟡"),
    "接近第一批区": ("#E0F2FE", "#075985", "🔵"),
    "合理持有区": ("#F3F4F6", "#4B5563", "⚪"),
    "偏高估区": ("#FFEDD5", "#C2410C", "🟠"),
    "减仓参考区": ("#FED7AA", "#9A3412", "🟠"),
    "明显高估区": ("#FECACA", "#B91C1C", "🔴"),
    "估值偏高（低置信度）": ("#FFEDD5", "#9A3412", "🟠"),
    "估值偏高（模型分歧较大）": ("#FFEDD5", "#C2410C", "🟠"),
    "估值偏低（低置信度）": ("#DCFCE7", "#166534", "🟢"),
    "观察 / 等回调": ("#F3F4F6", "#4B5563", "⚪"),
    "仅技术观察": ("#F3F4F6", "#4B5563", "⚪"),
    "低于深度价值区": ("#BBF7D0", "#14532D", "🟢"),
    "参考关注区": ("#FEF3C7", "#92400E", "🟡"),
    "参考折价区": ("#D1FAE5", "#047857", "🟢"),
    "深度折价区": ("#DCFCE7", "#166534", "🟢"),
    "低于深度折价区": ("#BBF7D0", "#14532D", "🟢"),
    "数据不足": ("#FEE2E2", "#991B1B", "🔴"),
}


def money(x):
    if x is None:
        return "—"
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "—"


def money_conf(x, confidence: str | None = None):
    if x is None:
        return "—"
    try:
        v = float(x)
    except Exception:
        return "—"
    if str(confidence or "").upper() == "LOW":
        return f"${v:,.0f}"
    return f"${v:,.2f}"


def dashboard_fair_text(r: dict) -> str:
    return format_fair_value(r)


def pct(v):
    if v is None:
        return "—"
    return f"{float(v):+.1f}%"


def delta_pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (float(a) / float(b) - 1) * 100


def get_secret(name: str):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


class AuthSessionError(RuntimeError):
    """Current Streamlit user no longer has a valid Supabase Auth session."""


def _user_id_of(user) -> str | None:
    if user is None:
        return None
    if isinstance(user, dict):
        value = user.get("id")
    else:
        value = getattr(user, "id", None)
    return str(value) if value else None


def _session_tokens(session) -> tuple[str | None, str | None]:
    if session is None:
        return None, None
    if isinstance(session, dict):
        return session.get("access_token"), session.get("refresh_token")
    return getattr(session, "access_token", None), getattr(session, "refresh_token", None)


def _client_options():
    try:
        from supabase import ClientOptions
    except ImportError:
        from supabase.lib.client_options import ClientOptions
    return ClientOptions(persist_session=False, auto_refresh_token=False)


def make_anon_client() -> Client:
    """Public client for signup/login only. Never cache a user-authenticated client."""
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error("Supabase 尚未配置。请先按 README 设置 SUPABASE_URL 和 SUPABASE_ANON_KEY。")
        st.stop()
    try:
        return create_client(url, key, options=_client_options())
    except (TypeError, ImportError, ValueError):
        return create_client(url, key)


def persist_auth_session(user, session) -> None:
    access_token, refresh_token = _session_tokens(session)
    session_user = None
    if session is not None:
        session_user = session.get("user") if isinstance(session, dict) else getattr(session, "user", None)
    user_id = _user_id_of(user) or _user_id_of(session_user)
    st.session_state["authenticated"] = bool(user_id and access_token and refresh_token)
    st.session_state["auth_user"] = user or session_user
    st.session_state["user_id"] = user_id
    st.session_state["access_token"] = access_token
    st.session_state["refresh_token"] = refresh_token


def clear_auth_session() -> None:
    st.session_state["authenticated"] = False
    st.session_state["auth_user"] = None
    st.session_state["user_id"] = None
    st.session_state["access_token"] = None
    st.session_state["refresh_token"] = None
    st.session_state["_profile_ensured"] = False
    st.session_state.pop("last_analysis", None)


def _remember_secret() -> str | None:
    secret = get_secret("SESSION_COOKIE_SECRET")
    if not secret:
        return None
    text = str(secret).strip()
    if not text or text.upper() in {"YOUR_SESSION_COOKIE_SECRET", "CHANGE_ME"}:
        return None
    return text


def _seal_remember_payload(refresh_token: str) -> str | None:
    return seal_remember_payload(refresh_token, _remember_secret(), ttl_days=REMEMBER_DAYS)


def _unseal_remember_payload(value: str | None) -> str | None:
    return unseal_remember_payload(value, _remember_secret())


def _apply_access_token(client: Client, access_token: str) -> None:
    """A newly created client is anonymous until the user JWT is attached to PostgREST."""
    try:
        client.postgrest.auth(access_token)
    except Exception:
        logger.warning("failed to apply access token to postgrest client")


def _save_remember_cookie(cookie_manager, refresh_token: str, widget_key: str) -> None:
    if not cookie_manager or not refresh_token:
        return
    sealed = _seal_remember_payload(refresh_token)
    if not sealed:
        return
    try:
        cookie_manager.set(
            REMEMBER_COOKIE,
            sealed,
            expires_at=datetime.now(timezone.utc) + timedelta(days=REMEMBER_DAYS),
            key=widget_key,
        )
    except Exception:
        logger.warning("failed to persist remember-me cookie")


def _delete_remember_cookie(cookie_manager, widget_key: str) -> None:
    if not cookie_manager:
        return
    try:
        cookie_manager.delete(REMEMBER_COOKIE, key=widget_key)
    except Exception:
        pass


def _rotate_remember_cookie(cookie_manager, refresh_token: str) -> None:
    if not cookie_manager or not refresh_token:
        return
    try:
        existing = cookie_manager.get(REMEMBER_COOKIE)
    except Exception:
        existing = None
    if existing:
        _save_remember_cookie(cookie_manager, refresh_token, "refresh_cookie_rotate")


def create_authenticated_client() -> Client:
    """
    Build a client for the current Streamlit user only.

    Do not store this client in st.cache_resource, st.cache_data, or a process-global singleton.
    Streamlit servers handle multiple users; a cached authenticated client can leak sessions.
    """
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    current_user_id = st.session_state.get("user_id")

    if not access_token or not refresh_token or not current_user_id:
        raise AuthSessionError("登录会话已失效，请重新登录。")

    client = make_anon_client()
    session = None
    try:
        resp = client.auth.set_session(access_token, refresh_token)
        session = getattr(resp, "session", None)
    except Exception:
        session = None

    if session is None or not getattr(session, "access_token", None):
        try:
            resp = client.auth.refresh_session(refresh_token)
            session = getattr(resp, "session", None)
        except Exception as exc:
            raise AuthSessionError("登录会话已失效，请重新登录。") from exc

    if session is None:
        try:
            session = client.auth.get_session()
        except Exception:
            session = None

    new_access, new_refresh = _session_tokens(session)
    if not new_access or not new_refresh:
        raise AuthSessionError("登录会话已失效，请重新登录。")

    session_user = session.get("user") if isinstance(session, dict) else getattr(session, "user", None)
    persist_auth_session(session_user or st.session_state.get("auth_user"), session)
    _apply_access_token(client, new_access)

    try:
        user_resp = client.auth.get_user()
        verified_user = getattr(user_resp, "user", None) or user_resp
        session_user_id = _user_id_of(verified_user)
    except Exception as exc:
        raise AuthSessionError("登录会话已失效，请重新登录。") from exc

    if not session_user_id or str(session_user_id) != str(current_user_id):
        raise AuthSessionError("登录会话已失效，请重新登录。")

    return client


def assert_live_session(client: Client, current_user_id: str) -> str:
    if not current_user_id or not st.session_state.get("access_token"):
        raise AuthSessionError("登录会话已失效，请重新登录。")

    session_uid = None
    try:
        session = client.auth.get_session()
        session_user = session.get("user") if isinstance(session, dict) else getattr(session, "user", None)
        session_uid = _user_id_of(session_user)
    except Exception:
        session_uid = None

    if not session_uid:
        try:
            user_resp = client.auth.get_user()
            session_uid = _user_id_of(getattr(user_resp, "user", None) or user_resp)
        except Exception as exc:
            raise AuthSessionError("登录会话已失效，请重新登录。") from exc

    if str(session_uid) != str(current_user_id):
        raise AuthSessionError("登录会话已失效，请重新登录。")
    return str(session_uid)


def is_rls_or_auth_error(exc: Exception) -> bool:
    if isinstance(exc, AuthSessionError):
        return True
    code = str(getattr(exc, "code", "") or "")
    text = str(exc).lower()
    return code == "42501" or "42501" in text or "row-level security" in text


def _session_user_id_from_client(client: Client | None) -> str | None:
    if client is None:
        return None
    try:
        session = client.auth.get_session()
        session_user = session.get("user") if isinstance(session, dict) else getattr(session, "user", None)
        return _user_id_of(session_user)
    except Exception:
        return None


def log_protected_error(operation: str, table: str, exc: Exception, client: Client | None = None) -> None:
    logger.warning(
        "protected db error operation=%s table=%s current_user_id=%s has_access_token=%s session_user_id=%s error_type=%s error_code=%s",
        operation,
        table,
        st.session_state.get("user_id"),
        bool(st.session_state.get("access_token")),
        _session_user_id_from_client(client),
        type(exc).__name__,
        getattr(exc, "code", None) or ("42501" if "42501" in str(exc) else None),
    )


def public_db_error(operation: str, table: str, exc: Exception, client: Client | None = None) -> str:
    if is_rls_or_auth_error(exc):
        log_protected_error(operation, table, exc, client=client)
        return "保存失败：登录会话已失效，请重新登录。"
    logger.exception("db operation failed operation=%s table=%s", operation, table)
    return "操作失败，请稍后重试。"


def public_analysis_error(ticker: str, exc: Exception) -> str:
    logger.warning(
        "analysis failed ticker=%s error_type=%s",
        ticker,
        type(exc).__name__,
    )
    text = str(exc).lower()
    if "no price data" in text or "delisted" in text:
        return f"无法分析 {ticker}：没有找到有效行情，请确认代码是否正确。"
    if "timeout" in text or "timed out" in text:
        return f"无法分析 {ticker}：行情数据源超时，请稍后重试。"
    return f"无法分析 {ticker}：行情或财务数据暂时不可用，请稍后重试。"


@st.cache_data(ttl=900, show_spinner=False)
def history_cached(ticker: str, as_of: str | None):
    return add_indicators(get_history(ticker, as_of))


@st.cache_data(ttl=900, show_spinner=False)
def fundamentals_cached(ticker: str):
    return get_live_fundamentals(ticker)


def zone_text(zone):
    if not zone:
        return "—"
    return f"{money(zone[0])} – {money(zone[1])}"


def core_zone_gap(price, zones):
    if not zones or price is None:
        return float("inf")
    core = zones.get("core") or (None, None)
    lo, hi = core
    if lo is None or hi is None:
        return float("inf")
    if lo <= price <= hi:
        return 0.0
    if price < lo:
        return lo - price
    return price - hi


def query_ticker_param():
    try:
        raw = st.query_params.get("ticker")
    except Exception:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    return normalize_ticker(raw)


def query_tab_param():
    """Legacy ?tab= deep link — ignored after V5.3 (no secondary tabs)."""
    try:
        raw = st.query_params.get("tab")
    except Exception:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    return None if raw is None else None


def open_single_stock(ticker: str, *, tab: str | None = None) -> None:
    """Shared jump from 自选股 / 头等大事 → 单股分析 (no secondary tabs)."""
    del tab
    t = normalize_ticker(ticker)
    if not t:
        return
    st.session_state.selected_ticker = t
    st.session_state._last_watch_select = t
    st.session_state._pending_watch_select = t
    st.session_state._pending_nav_page = "单股分析"
    try:
        st.query_params["ticker"] = t
        if "tab" in st.query_params:
            del st.query_params["tab"]
    except Exception:
        pass
    st.rerun()


def open_headlines(ticker: str | None = None, event_id: str | None = None) -> None:
    """Jump to 头等大事. Only pass ticker from single-stock deep link."""
    st.session_state._pending_nav_page = "头等大事"
    st.session_state.headline_selected_event_id = event_id
    if event_id:
        st.session_state.headline_range = "本季度"
    else:
        st.session_state.pop("headline_selected_event", None)
    if ticker:
        t = normalize_ticker(ticker)
        if t:
            st.session_state.headline_filter_ticker = t
            st.session_state._headline_deep_link = True
    else:
        st.session_state.pop("headline_filter_ticker", None)
        st.session_state.pop("headline_ticker_filter", None)
        st.session_state._headline_deep_link = False
    st.rerun()


def render_account_panel(user_email: str, db: Client) -> None:
    st.subheader("账户设置")
    st.write(f"邮箱：**{user_email}**")
    st.caption("密码由 Supabase Auth 管理，不保存在应用数据库中。")
    st.caption("产品能力：自选股数据库 · 行业感知公允价值 · SMA30/50/200 · 成交密集区 · 分层买入区")
    st.caption(f"登录状态：已登录 · {user_email}")
    with st.form("change_password"):
        p1 = st.text_input("新密码", type="password")
        p2 = st.text_input("确认新密码", type="password")
        change = st.form_submit_button("修改密码")
    if change:
        if p1 != p2:
            st.error("两次密码不一致。")
        elif len(p1) < 8:
            st.error("密码至少 8 位。")
        else:
            try:
                db.auth.update_user({"password": p1})
                st.success("密码已更新。")
            except Exception as exc:
                logger.warning("password update failed error_type=%s", type(exc).__name__)
                st.error("修改失败，请重新登录后再试。")
    if st.button("← 返回", key="account_back"):
        st.session_state.account_open = False
        st.rerun()


MODEL_LABELS = {
    "pe": "市盈率",
    "dcf": "现金流折现",
    "growth": "成长 / PEG",
    "forward_pe": "前瞻市盈率",
    "normalized_pe": "归一化市盈率",
    "growth_adjusted_pe": "成长调整市盈率",
    "normalized_fcf_dcf": "归一化自由现金流折现",
    "price_to_book_roe": "市净率 × 净资产收益率",
    "residual_income": "剩余收益",
    "ev_ebitda": "企业价值 / EBITDA",
    "revenue_multiple": "收入倍数",
    "normalized_cycle_earnings": "周期归一化盈利",
    "unsupported": "专项 / 不适用",
    "Forward P/E": "前瞻市盈率",
    "Normalized P/E": "归一化市盈率",
    "Growth-adjusted P/E": "成长调整市盈率",
    "Normalized FCF DCF": "归一化自由现金流折现",
    "P/B × ROE": "市净率 × 净资产收益率",
    "Residual Income": "剩余收益",
    "EV/EBITDA": "企业价值 / EBITDA",
    "Revenue Multiple": "收入倍数",
    "Cycle-normalized Earnings": "周期归一化盈利",
    "Unsupported / specialized": "专项 / 不适用",
}

CONFIDENCE_ZH = {
    "HIGH": "高",
    "MEDIUM": "中",
    "LOW": "低",
    "SPECIALIZED": "专项",
    "UNAVAILABLE": "不可用",
}

CLASS_LABELS_ZH = {
    "mega_cap_tech": "大型科技",
    "mature_growth": "成熟成长",
    "semiconductor_growth": "半导体成长",
    "cyclical_semiconductor": "周期半导体",
    "bank": "银行",
    "fintech_exchange": "金融科技交易所",
    "crypto_treasury": "加密资产金库",
    "high_growth_software": "高成长软件",
    "pre_profit_growth": "未盈利成长",
    "space_optionality": "航天期权",
    "auto_optionality": "汽车期权",
    "consumer_platform": "消费平台",
    "generic_profitable": "通用盈利",
    "unsupported_specialized": "专项 / 不适用",
    "Mega-Cap Tech": "大型科技",
    "Mature Growth": "成熟成长",
    "Semiconductor Growth": "半导体成长",
    "Cyclical Semiconductor": "周期半导体",
    "Bank": "银行",
    "Fintech Exchange": "金融科技交易所",
    "Crypto Treasury": "加密资产金库",
    "High-Growth Software": "高成长软件",
    "Pre-Profit Growth": "未盈利成长",
    "Space Optionality": "航天期权",
    "Auto Optionality": "汽车期权",
    "Consumer Platform": "消费平台",
    "Generic Profitable": "通用盈利",
    "Specialized / Unsupported": "专项 / 不适用",
    "Generic": "通用",
}

EXIT_MODE_ZH = {
    "precise": "精确",
    "qualitative": "定性",
    "unavailable": "不可用",
}


def confidence_zh(value) -> str:
    if value is None or value == "" or value == "—":
        return "—"
    key = str(value).strip().upper()
    return CONFIDENCE_ZH.get(key, str(value))


def class_label_zh(label=None, valuation_class=None) -> str:
    if valuation_class:
        mapped = CLASS_LABELS_ZH.get(str(valuation_class))
        if mapped:
            return mapped
    if label:
        mapped = CLASS_LABELS_ZH.get(str(label))
        if mapped:
            return mapped
        return str(label)
    return "—"


def model_label_zh(obj_or_id) -> str:
    if isinstance(obj_or_id, dict):
        mid = obj_or_id.get("model_id")
        name = obj_or_id.get("name")
        return (
            MODEL_LABELS.get(mid)
            or MODEL_LABELS.get(name)
            or MODEL_DISPLAY_NAMES.get(mid, name or mid or "—")
        )
    return MODEL_LABELS.get(obj_or_id, MODEL_DISPLAY_NAMES.get(obj_or_id, obj_or_id or "—"))


def model_status_text(obj) -> str:
    if not obj:
        return "无数据"
    if obj.get("applicable") is False:
        return "不适用"
    if obj.get("outlier"):
        return "⚠ 偏离过大，已排除"
    if obj.get("valid") is False:
        return "⚠ 数据异常，已从综合估值中排除"
    if obj.get("valid"):
        return f"✓ {confidence_zh(obj.get('confidence') or 'MEDIUM')}"
    return "无数据"


def render_model_explanations(r: dict):
    blend = r.get("blend") or {}
    model_list = blend.get("model_list") or list((blend.get("models") or {}).values())
    if not model_list:
        return
    st.markdown("#### 为什么得到这个估值？")
    for obj in model_list:
        name = model_label_zh(obj)
        applicable = obj.get("applicable") is not False
        usable = applicable and obj.get("valid") and not obj.get("outlier")
        with st.expander(f"{name} — {'纳入' if usable else '排除'}", expanded=False):
            executed = obj.get("executed")
            st.write(f"**是否执行：** {'是' if executed else ('否' if executed is False else '—')}")
            if obj.get("outlier"):
                st.write("**状态：** 已执行，但因偏离过大被排除")
            elif not applicable:
                st.write("**状态：** 不适用 / 未执行")
            elif obj.get("valid") is False:
                st.write("**状态：** 已执行但无效")
            else:
                st.write("**状态：** 已纳入")
            st.write(f"**原因：** {obj.get('applicability_reason') or obj.get('reason') or '—'}")
            st.write(f"**适用性说明：** {obj.get('why_applicable') or '—'}")
            if usable:
                inputs = obj.get("inputs") or {}
                if inputs:
                    st.write("**关键输入：**")
                    for key, value in list(inputs.items())[:8]:
                        st.write(f"- {key}: {value}")
                st.write(
                    f"**结果：** {money(obj.get('low'))} / {money(obj.get('mid'))} / {money(obj.get('high'))}"
                )
                st.write(f"**置信度：** {confidence_zh(obj.get('confidence'))}")
            elif obj.get("outlier"):
                st.write("该模型已执行，但相对其他模型偏离过大，未纳入综合估值。")
            elif executed is False:
                st.caption("未执行计算：适用性检查未通过。")


def render_cycle_panel(r: dict):
    cycle = (r.get("blend") or {}).get("cycle") or r.get("cycle")
    if not cycle:
        return
    st.markdown("#### 周期归一化")
    st.caption(cycle.get("note") or "周期估值使用中周期盈利，而非当前周期峰值/谷值。")
    rows = [
        ("当前 EPS", cycle.get("current_eps")),
        ("前瞻 EPS", cycle.get("forward_eps")),
        ("归一化 EPS", cycle.get("cycle_normalized_eps")),
        ("历史 EPS 中位数", cycle.get("historical_eps_median")),
        ("当前营业利润率", cycle.get("current_operating_margin")),
        ("归一化营业利润率", cycle.get("normalized_operating_margin")),
        ("归一化自由现金流", cycle.get("normalized_fcf")),
    ]
    st.dataframe(
        pd.DataFrame({"指标": [a for a, _ in rows], "值": [b for _, b in rows]}),
        hide_index=True,
        use_container_width=True,
    )
    pe_range = cycle.get("cycle_pe_range")
    if pe_range:
        st.caption(f"周期 PE 区间：{pe_range[0]} – {pe_range[1]}")


def render_market_reference(r: dict):
    ref = r.get("market_reference") or {}
    st.markdown("**市场参考**")
    st.write("Analyst consensus:", format_consensus_target(ref))
    st.caption(f"Range: {money(ref.get('analyst_target_low'))} – {money(ref.get('analyst_target_high'))} · Source: {ref.get('consensus_source') or 'Finnhub'} · Updated: {ref.get('consensus_updated_at') or '未提供'}")
    deviation = ref.get("internal_vs_consensus_pct")
    st.write("Internal vs consensus:", f"{deviation:+.1f}%" if deviation is not None else "—")
    if ref.get("error"):
        st.caption(ref["error"])
    if ref.get("sanity_status") == "HIGH_DIVERGENCE":
        st.warning("⚠ 内部估值与市场一致预期分歧显著")


def render_valuation_diagnostics(r: dict):
    ref = r.get("market_reference") or {}
    st.caption("买入区与减仓区由内部估值、波动率、模型可靠性和安全边际规则推导，并非独立估值模型。")
    st.write("估值模式：", r.get("valuation_mode") or "—")
    if ref.get("analyst_consensus_target") is not None:
        st.write("Market consensus reference：", money(ref.get("analyst_consensus_target")))
    if r.get("valuation_mode") == "SPECIALIZED":
        st.caption("内部估值：专项模型未提供")
    for warning in ref.get("sanity_warnings") or []:
        st.warning(warning)
    st.caption(f"前瞻预测更新：{r.get('forward_estimate_updated_at') or '未提供'} · 一致目标更新：{ref.get('consensus_updated_at') or '未提供'} · 来源：{ref.get('consensus_source') or '—'}")
    st.write({key: (f"{ref[key]:.2f}x" if ref.get(key) is not None else "—") for key in ("current_forward_pe", "internal_implied_forward_pe", "historical_pe_median_3y", "historical_pe_median_5y", "sector_forward_pe")})
    f = r.get("financials") or {}
    blend = r.get("blend") or {}
    profile = blend.get("profile") or {}
    st.caption(
        f"价格时点：{r.get('price_timestamp') or r.get('date') or '—'}（日线）　"
        f"财务期：{f.get('fcf_period') or r.get('financials_period') or '—'}　"
        f"估值运行：{r.get('valuation_run_at') or '—'}　"
        f"快照：{r.get('snapshot_date') or '—（实时，未入库）'}　"
        f"模型：{r.get('model_version') or '—'}"
    )
    with st.expander("估值诊断"):
        from peer_comparable_ui import render_peer_comparable
        render_peer_comparable(r.get("peer_comparable_result"),
                              (r.get("peer_diagnostics") or {}).get("mode", "diagnostic"),
                              diagnostics=r.get("peer_diagnostics"))
        lines = [
            f"**估值类型**: {class_label_zh(profile.get('valuation_class_label') or r.get('valuation_class_label'), profile.get('valuation_class') or r.get('valuation_class'))}",
            f"**置信度**: {confidence_zh(r.get('confidence'))}",
            f"**行业**: {f.get('sector') or '—'} / {f.get('industry') or '—'}",
        ]
        if blend.get("warnings"):
            if "high_valuation_uncertainty" in blend["warnings"]:
                lines.append("**高估值不确定性**：模型分歧超过 60%。")
            lines.append("警告：" + ", ".join(blend["warnings"]))
        model_list = blend.get("model_list") or list((blend.get("models") or {}).values())
        if not model_list:
            model_list = [obj for obj in (r.get("pe"), r.get("dcf"), r.get("growth")) if obj]
        if f.get("eps_proxy") and fnum(f.get("forward_eps")) is None:
            lines.append("**前瞻 EPS 不可用**")
            source = f.get("eps_proxy_source") or ""
            if source in {"statement_trailing_eps", "statement_derived", "ni_over_diluted_shares", "income_statement_diluted_eps"}:
                lines.append("**使用报表推导的 trailing EPS 代理**")
            else:
                lines.append("**使用 trailing EPS 代理**")
        prov = f.get("provenance") or {}
        shares_p = prov.get("shares") or {}
        lines.append("**报价货币**: " + str(prov.get("quote_currency") or f.get("quote_currency") or "—"))
        lines.append("**财务货币**: " + str(prov.get("financial_currency") or f.get("financial_currency") or "—"))
        fwd = prov.get("forward_eps") or {}
        lines.append(f"**前瞻 EPS**: {fwd.get('value')}  来源={fwd.get('source') or f.get('forward_eps_source') or '—'}")
        tr = prov.get("trailing_eps") or {}
        lines.append(f"**Trailing EPS**: {tr.get('value')}  来源={tr.get('source') or f.get('trailing_eps_source') or '—'}")
        st_eps = prov.get("statement_eps") or {}
        lines.append(f"**报表 EPS**: {st_eps.get('value')}  货币={st_eps.get('currency') or f.get('statement_eps_currency') or '—'}")
        px = prov.get("eps_proxy") or {}
        safe = px.get("currency_safe")
        if safe is None:
            safe = f.get("eps_proxy_currency_safe")
        lines.append(
            f"**EPS 代理**: {px.get('value') if px else f.get('eps_proxy')}  "
            f"来源={px.get('source') or f.get('eps_proxy_source') or '—'}  "
            f"货币安全: {'是' if safe else '否'}"
        )
        lines.append(f"**sharesOutstanding**: {shares_p.get('sharesOutstanding') if shares_p else f.get('shares_outstanding')}")
        lines.append(f"**impliedSharesOutstanding**: {shares_p.get('impliedSharesOutstanding') if shares_p else f.get('implied_shares_outstanding')}")
        lines.append(f"**marketCap/price**: {shares_p.get('marketCap/price') if shares_p else f.get('market_cap_over_price')}")
        lines.append(f"**diluted average shares**: {shares_p.get('diluted_average_shares') if shares_p else f.get('diluted_average_shares')}")
        lines.append(
            f"**canonical shares**: {shares_p.get('canonical_shares') if shares_p else f.get('canonical_shares')}  "
            f"source={shares_p.get('canonical_source') if shares_p else f.get('canonical_shares_source') or '—'}"
        )
        for obj in model_list:
            inputs = obj.get("inputs") or {}
            lines.append(f"**{obj.get('name') or obj.get('model_id')}**")
            lines.append(f"- 状态: {model_status_text(obj)} {money(obj.get('mid'))}")
            lines.append(f"- applicable: {'yes' if obj.get('applicable') is not False else 'no'}")
            lines.append(f"- reason: {obj.get('applicability_reason') or obj.get('reason') or '—'}")
            if inputs.get("eps_used") is not None or inputs.get("cycle_eps") is not None or inputs.get("normalized_eps") is not None:
                lines.append(f"- input EPS: {inputs.get('eps_used') or inputs.get('cycle_eps') or inputs.get('normalized_eps')} source={inputs.get('eps_source') or inputs.get('eps_method') or '—'}")
            if inputs.get("shares") is not None:
                lines.append(f"- input shares: {inputs.get('shares')} source={inputs.get('canonical_shares_source') or '—'}")
            if inputs.get("currency") or f.get("quote_currency"):
                lines.append(f"- currency: {inputs.get('currency') or f.get('quote_currency')}")
            if obj.get("reason") and obj.get("reason") != (obj.get("applicability_reason") or obj.get("reason")):
                lines.append(f"- reason: {obj.get('reason')}")
            for key, value in list(inputs.items())[:8]:
                lines.append(f"- {key}: {value}")
        st.markdown("\n".join(lines))


def blend_caption(blend) -> str:
    if not blend:
        return ""
    included = [model_label_zh(name) for name in blend.get("included") or []]
    excluded = [model_label_zh(item.get("name") or item.get("model_id")) for item in blend.get("excluded") or []]
    parts = []
    if included:
        parts.append("综合基于：" + " + ".join(included))
    if excluded:
        parts.append("排除：" + "、".join(excluded))
    if blend.get("specialized"):
        parts.append("需要专项估值模型")
    elif blend.get("insufficient_models"):
        parts.append("有效估值模型不足")
    if "high_valuation_uncertainty" in (blend.get("warnings") or []):
        parts.append("高估值不确定性")
    return "　".join(parts)


def recommendation_label(r):
    from analysis_service import _recommendation_label
    return _recommendation_label(r)


def status_badge(label: str):
    base = str(label).replace("（低置信度）", "")
    bg, fg, icon = STATUS_META.get(base, STATUS_META.get(str(label), ("#F3F4F6", "#4B5563", "⚪")))
    st.markdown(
        f'<span style="background:{bg};color:{fg};padding:0.35rem 0.7rem;border-radius:999px;font-weight:700">{icon} {label}</span>',
        unsafe_allow_html=True,
    )


def style_status(v):
    base = str(v).replace("（低置信度）", "")
    bg, fg, _ = STATUS_META.get(base, STATUS_META.get(str(v), ("#FFFFFF", "#111827", "")))
    return f"background-color:{bg}; color:{fg}; font-weight:700"


def render_valuation_band(r: dict):
    """Continuous valuation band from deep value through extreme overvaluation."""
    zones = {} if r.get("hide_precise_trading_zones") else (r.get("zones") or {})
    exit_zone = r.get("exit_zone") or ((r.get("blend") or {}).get("exit_zone")) or {}
    price = fnum(r.get("price"))
    conf = str(r.get("confidence") or "").upper()
    mode = exit_zone.get("display_mode") if isinstance(exit_zone, dict) else None
    if conf in {"SPECIALIZED", "UNAVAILABLE"}:
        return
    if mode and mode != "precise":
        return
    if isinstance(exit_zone, dict) and exit_zone.get("eligible_for_precise_exit") is False:
        return
    labels = zones.get("labels") or {}
    segments = []
    if zones.get("deep"):
        segments.append((labels.get("deep") or "深度价值区", "#86EFAC", zones["deep"][0], zones["deep"][1]))
    if zones.get("core"):
        segments.append((labels.get("core") or "核心买入区", "#4ADE80", zones["core"][0], zones["core"][1]))
    if zones.get("first"):
        segments.append((labels.get("first") or "第一批区", "#FDE68A", zones["first"][0], zones["first"][1]))
    hold = fnum(exit_zone.get("hold_upper_price"))
    over = fnum(exit_zone.get("overvalued_price"))
    trim = fnum(exit_zone.get("trim_price"))
    extreme = fnum(exit_zone.get("extreme_price"))
    first_hi = (zones.get("first") or (None, None))[1]
    if hold is not None and first_hi is not None:
        segments.append(("合理持有区", "#E5E7EB", first_hi, hold))
    elif hold is not None:
        mid = fnum(r.get("blended_mid") or r.get("fair"))
        if mid is not None:
            segments.append(("合理持有区", "#E5E7EB", mid, hold))
    if hold is not None and trim is not None:
        start = over if over is not None else hold
        segments.append(("偏高估区", "#FED7AA", hold, trim if trim > hold else start))
    if trim is not None and extreme is not None:
        segments.append(("减仓参考区", "#FB923C", trim, extreme))
    if extreme is not None:
        segments.append(("明显高估区", "#F87171", extreme, extreme * 1.08))

    if not segments:
        return

    active = str(r.get("recommendation") or "")
    cells = []
    for name, color, lo, hi in segments:
        lo_f, hi_f = fnum(lo), fnum(hi)
        here = False
        if price is not None and lo_f is not None and hi_f is not None:
            if name == "明显高估区":
                here = price >= lo_f
            else:
                here = lo_f <= price <= hi_f
        if name in active or here:
            border = "3px solid #111827"
            weight = "800"
        else:
            border = "1px solid rgba(0,0,0,0.08)"
            weight = "600"
        sat = "0.55" if conf == "LOW" else "1"
        cells.append(
            f'<div style="flex:1;min-width:72px;background:{color};opacity:{sat};border:{border};'
            f'padding:0.45rem 0.35rem;text-align:center;font-size:0.78rem;font-weight:{weight};color:#111827">'
            f"{name}<br/><span style='font-weight:500'>{money(lo_f)} – {money(hi_f) if name != '明显高估区' else ('>' + money(lo_f))}</span>"
            f"</div>"
        )
    st.markdown(
        '<div style="display:flex;gap:2px;width:100%;border-radius:8px;overflow:hidden;margin:0.4rem 0 0.8rem 0">'
        + "".join(cells)
        + "</div>",
        unsafe_allow_html=True,
    )
    if price is not None:
        st.caption(f"当前价格位置高亮。现价 {money(price)}。减仓参考区基于当前估值模型与安全边际，不代表个性化投资建议。")


def render_exit_diagnostics(r: dict):
    exit_zone = r.get("exit_zone") or ((r.get("blend") or {}).get("exit_zone"))
    conf = str(r.get("confidence") or "").upper()
    rel = (exit_zone or {}).get("exit_reliability") if isinstance(exit_zone, dict) else None
    mode = (exit_zone or {}).get("display_mode") if isinstance(exit_zone, dict) else r.get("exit_display_mode")
    with st.expander("退出区 / 高估诊断"):
        st.caption(
            "退出区仅在估值模型一致性与可靠性达到要求时提供精确价格。"
            "模型分歧较大时，仅显示定性高估提示。"
        )
        if conf in {"SPECIALIZED", "UNAVAILABLE"} or mode == "unavailable":
            st.write("专项/不可用：不生成精确退出区。")
            return
        disp = r.get("dispersion_pct")
        disp_txt = f"{disp*100:.0f}%" if disp is not None else "—"
        lines = [
            f"**估值置信度**: {confidence_zh(conf)}",
            f"**估值可靠性评分**: {r.get('reliability_score') if r.get('reliability_score') is not None else '—'}",
            f"**模型分歧**: {disp_txt}",
            f"**退出置信度**: {confidence_zh((exit_zone or {}).get('exit_confidence') or r.get('exit_confidence'))}",
            f"**显示模式**: {EXIT_MODE_ZH.get(str(mode or ''), mode or '—')}",
            f"**可提供精确退出价**: {'是' if (exit_zone or {}).get('eligible_for_precise_exit') else '否'}",
            f"**原因代码**: {', '.join((exit_zone or {}).get('reason_codes') or r.get('exit_reason_codes') or []) or '—'}",
        ]
        if isinstance(rel, dict):
            lines.append(f"**退出可靠性评分**: {rel.get('exit_reliability_score')}")
            lines.append(f"**退出分歧**: {rel.get('exit_dispersion_pct')}")
        if conf == "LOW" or mode == "qualitative" or not isinstance(exit_zone, dict):
            lines.append("")
            lines.append("精确减仓价格已关闭（定性 / 低可靠性）。")
            st.markdown("\n".join(lines))
            return
        lines.extend([
            "",
            f"**波动率**: {exit_zone.get('volatility_1y')} ({exit_zone.get('volatility_band') or '—'})",
            f"**周期性调整**: {exit_zone.get('cyclical_adj', 0):+.0%}" if exit_zone.get("cyclical_adj") is not None else "**周期性调整**: —",
            f"**分歧调整**: {exit_zone.get('dispersion_adj', 0):+.0%}" if exit_zone.get("dispersion_adj") is not None else "**分歧调整**: —",
            f"**类型调整**: {exit_zone.get('class_adj', 0):+.0%}" if exit_zone.get("class_adj") is not None else "**类型调整**: —",
            f"**调整项**: {', '.join(exit_zone.get('adjustments') or []) or '—'}",
            "",
            f"**持有上限**: {exit_zone.get('hold_upper_pct', 0):.0%}",
            f"**偏高估阈值**: {exit_zone.get('overvalued_pct', 0):.0%}",
            f"**减仓阈值**: {exit_zone.get('trim_pct', 0):.0%}",
            f"**极端高估阈值**: {exit_zone.get('extreme_pct', 0):.0%}",
            "",
            f"**持有上限价**: {money(exit_zone.get('hold_upper_price'))}",
            f"**偏高估价**: {money(exit_zone.get('overvalued_price'))}",
            f"**减仓参考价**: {money(exit_zone.get('trim_price'))}",
            f"**极端高估价**: {money(exit_zone.get('extreme_price'))}",
        ])
        st.markdown("\n".join(lines))
        st.caption("减仓参考区基于当前估值模型与安全边际，不代表个性化投资建议。")


def get_cloud_snapshot(sb: Client, user_id: str, ticker: str, as_of: str):
    current_user_id = assert_live_session(sb, user_id)
    return fetch_historical_snapshot(sb, current_user_id, ticker, as_of)


def analyze_one(ticker: str, as_of: str | None, sb: Client | None = None, user_id: str | None = None):
    def snapshot_loader(t: str, d: str):
        if not sb or not user_id:
            return None
        return get_cloud_snapshot(sb, user_id, t, d)

    def live_analysis():
        return analyze_ticker(
            ticker,
            as_of,
            history_loader=history_cached,
            fundamentals_loader=fundamentals_cached,
            snapshot_loader=snapshot_loader,
        )

    result = live_analysis()
    if as_of or not sb or not user_id:
        return result
    from last_reliable_valuation import resolve_live_result
    try:
        return resolve_live_result(
            result,
            lambda: get_cloud_snapshot(sb, user_id, result['ticker'], date.today().isoformat()),
            lambda live: save_snapshot(sb, user_id, live),
        )
    except Exception as exc:
        if is_rls_or_auth_error(exc):
            raise
        # Storage failure must not suppress a successful live analysis.
        result['source_status'] = 'live'
        result['reliable_cache_status'] = 'storage_unavailable'
        return result


def save_snapshot(sb: Client, user_id: str, r: dict):
    current_user_id = assert_live_session(sb, user_id)
    if r.get('source_status') == 'cached_last_reliable':
        return  # Never renew the reliable timestamp from a cache hit.
    payload = build_snapshot_record(current_user_id, r)
    if payload['raw'].get('last_reliable') is None:
        # Preserve the reliable version when a same-day unavailable run upserts.
        previous = fetch_historical_snapshot(sb, current_user_id, r['ticker'], date.today().isoformat())
        payload['raw']['last_reliable'] = ((previous or {}).get('raw') or {}).get('last_reliable')
    try:
        sb.table("valuation_snapshots").upsert(
            payload, on_conflict="user_id,ticker,snapshot_date"
        ).execute()
    except Exception as exc:
        if is_rls_or_auth_error(exc):
            raise
        if is_schema_cache_error(exc):
            sb.table("valuation_snapshots").upsert(
                legacy_snapshot_record(payload), on_conflict="user_id,ticker,snapshot_date"
            ).execute()
            return
        raise


def list_snapshots(sb: Client, user_id: str, ticker: str):
    current_user_id = assert_live_session(sb, user_id)
    columns = "snapshot_date,price,fair_value,sma30,sma50,sma200,first_low,first_high,core_low,core_high,deep_low,deep_high,status,valuation_class,confidence,model_version,reliability_score,dispersion_pct,blended_low,blended_high"
    legacy = "snapshot_date,price,fair_value,sma30,sma50,sma200,first_low,first_high,core_low,core_high,deep_low,deep_high,status"
    try:
        res = (
            sb.table("valuation_snapshots")
            .select(columns)
            .eq("user_id", current_user_id)
            .eq("ticker", ticker)
            .order("snapshot_date", desc=True)
            .execute()
        )
    except Exception as exc:
        if is_rls_or_auth_error(exc):
            raise
        if is_schema_cache_error(exc):
            res = (
                sb.table("valuation_snapshots")
                .select(legacy)
                .eq("user_id", current_user_id)
                .eq("ticker", ticker)
                .order("snapshot_date", desc=True)
                .execute()
            )
        else:
            raise
    return res.data or []


def get_watchlist(sb: Client, user_id: str):
    current_user_id = assert_live_session(sb, user_id)
    res = (
        sb.table("watchlist")
        .select("id,ticker,nickname,created_at")
        .eq("user_id", current_user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


def add_watchlist(sb: Client, user_id: str, ticker: str, nickname: str = ""):
    current_user_id = assert_live_session(sb, user_id)
    ticker = normalize_ticker(ticker)
    if not ticker:
        raise ValueError("股票代码格式不正确")
    try:
        history_cached(ticker, None)
    except Exception as exc:
        raise ValueError(f"无法验证股票代码 {ticker}") from exc
    sb.table("watchlist").upsert(
        {
            "user_id": current_user_id,
            "ticker": ticker,
            "nickname": nickname.strip() or None,
        },
        on_conflict="user_id,ticker",
    ).execute()


def update_watchlist_note(sb: Client, user_id: str, ticker: str, nickname: str = ""):
    current_user_id = assert_live_session(sb, user_id)
    (
        sb.table("watchlist")
        .update({"nickname": nickname.strip() or None})
        .eq("user_id", current_user_id)
        .eq("ticker", ticker)
        .execute()
    )


def remove_watchlist(sb: Client, user_id: str, ticker: str):
    current_user_id = assert_live_session(sb, user_id)
    (
        sb.table("watchlist")
        .delete()
        .eq("user_id", current_user_id)
        .eq("ticker", ticker)
        .execute()
    )


def ensure_profile(sb: Client, user_id: str, email: str = "") -> None:
    current_user_id = assert_live_session(sb, user_id)
    res = (
        sb.table("profiles")
        .select("user_id")
        .eq("user_id", current_user_id)
        .limit(1)
        .execute()
    )
    if res.data:
        return
    display_name = email.split("@")[0] if email else None
    try:
        sb.table("profiles").insert(
            {"user_id": current_user_id, "display_name": display_name}
        ).execute()
    except Exception as exc:
        code = str(getattr(exc, "code", "") or "")
        text = str(exc).lower()
        if code == "23505" or "23505" in text or "duplicate" in text:
            return
        raise


# ---------------- Authentication ----------------

def _init_auth_state() -> None:
    defaults = {
        "authenticated": False,
        "auth_user": None,
        "user_id": None,
        "access_token": None,
        "refresh_token": None,
        "_profile_ensured": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _user_email(user) -> str:
    if user is None:
        return ""
    if isinstance(user, dict):
        return user.get("email") or ""
    return getattr(user, "email", "") or ""


_init_auth_state()
cookie_manager = stx.CookieManager(key="auth_cookie_manager")


def restore_remembered_session() -> None:
    """Restore tokens from the signed remember-me cookie into this Streamlit session.

    The cookie stores an encrypted refresh-token payload only. Passwords are never stored.
    Persistent remember-me requires SESSION_COOKIE_SECRET; otherwise only this browser session is kept.
    """
    if st.session_state.get("authenticated") and st.session_state.get("access_token"):
        return
    if not _remember_secret():
        return

    try:
        saved = cookie_manager.get(REMEMBER_COOKIE)
    except Exception:
        saved = None
    saved_refresh = _unseal_remember_payload(saved)
    if not saved_refresh:
        if saved:
            _delete_remember_cookie(cookie_manager, "delete_bad_refresh_cookie")
        return

    anon = make_anon_client()
    try:
        resp = anon.auth.refresh_session(saved_refresh)
        if resp and resp.session and resp.user:
            persist_auth_session(resp.user, resp.session)
            _save_remember_cookie(
                cookie_manager,
                resp.session.refresh_token,
                "refresh_cookie_after_restore",
            )
    except Exception:
        logger.warning("remember-me session restore failed")
        _delete_remember_cookie(cookie_manager, "delete_bad_refresh_cookie")
        clear_auth_session()


def login_page():
    st.markdown(
        '<div style="font-size:30px;font-weight:700;line-height:1.15;margin:0.2rem 0">'
        "📈 股票公允价值监控</div>",
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 1.15, 1])
    with center:
        tab_login, tab_signup = st.tabs(["登录", "注册"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("邮箱", placeholder="you@example.com")
                password = st.text_input("密码", type="password")
                remember = st.checkbox(
                    "记住登录状态 30 天",
                    value=bool(_remember_secret()),
                    disabled=not _remember_secret(),
                )
                if not _remember_secret():
                    st.caption("未配置 SESSION_COOKIE_SECRET，仅保留当前浏览器会话。")
                submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
            if submitted:
                try:
                    anon = make_anon_client()
                    resp = anon.auth.sign_in_with_password({"email": email.strip(), "password": password})
                    if not resp or not resp.user or not resp.session:
                        st.error("登录失败：未获得有效会话，请重试。")
                    else:
                        persist_auth_session(resp.user, resp.session)
                        if remember and _remember_secret():
                            _save_remember_cookie(
                                cookie_manager,
                                resp.session.refresh_token,
                                "remember_login_cookie",
                            )
                        else:
                            _delete_remember_cookie(cookie_manager, "clear_remember_cookie")
                        st.rerun()
                except Exception as exc:
                    logger.warning("login failed error_type=%s", type(exc).__name__)
                    st.error("登录失败：邮箱或密码不正确。")

        with tab_signup:
            with st.form("signup_form"):
                new_email = st.text_input("注册邮箱", placeholder="you@example.com")
                new_password = st.text_input("设置密码", type="password")
                new_password2 = st.text_input("确认密码", type="password")
                signup = st.form_submit_button("创建账户", use_container_width=True)
            if signup:
                if new_password != new_password2:
                    st.error("两次输入的密码不一致。")
                elif len(new_password) < 8:
                    st.error("密码至少 8 位。")
                else:
                    try:
                        anon = make_anon_client()
                        resp = anon.auth.sign_up({"email": new_email.strip(), "password": new_password})
                        if resp.session and resp.user:
                            persist_auth_session(resp.user, resp.session)
                            st.success("注册成功并已登录。")
                            st.rerun()
                        else:
                            st.success("注册成功。请先到邮箱完成验证，然后回来登录。")
                    except Exception as exc:
                        logger.warning("signup failed error_type=%s", type(exc).__name__)
                        st.error("注册失败，请稍后重试。")

        st.caption("密码由 Supabase Auth 安全处理；本程序不会把明文密码写入数据库或 GitHub。")


restore_remembered_session()

if not (
    st.session_state.get("authenticated")
    and st.session_state.get("user_id")
    and st.session_state.get("access_token")
    and st.session_state.get("refresh_token")
):
    login_page()
    st.stop()

try:
    db = create_authenticated_client()
except AuthSessionError:
    _delete_remember_cookie(cookie_manager, "invalid_session_clear_cookie")
    clear_auth_session()
    st.warning("登录会话已失效，请重新登录。")
    login_page()
    st.stop()

_rotate_remember_cookie(cookie_manager, st.session_state.get("refresh_token"))
user_id = st.session_state["user_id"]
user_email = _user_email(st.session_state.get("auth_user"))

if not st.session_state.get("_profile_ensured"):
    try:
        ensure_profile(db, user_id, user_email)
        st.session_state._profile_ensured = True
    except Exception as exc:
        if is_rls_or_auth_error(exc):
            log_protected_error("insert", "profiles", exc, client=db)
            _delete_remember_cookie(cookie_manager, "profile_rls_clear_cookie")
            clear_auth_session()
            st.warning("登录会话已失效，请重新登录。")
            login_page()
            st.stop()
        logger.exception("ensure_profile failed")

# Temporary diagnostics: fail closed locally; admin email is verified server-side.
audit_admin = is_cloud_runtime() and verified_admin(db, user_id, st.secrets.get("ADMIN_EMAIL"))
if not audit_admin:
    st.session_state.pop("_v45_export_open", None)
    st.session_state.pop("_v45_export_result", None)
    st.session_state.pop("_peer_diagnostic_open", None)
    st.session_state.pop("_peer_diagnostic_result", None)
    st.session_state.pop("_finnhub_audit_open", None)
    st.session_state.pop("_finnhub_audit_result", None)
    st.session_state.pop("_financial_diagnostic_open", None)
    st.session_state.pop("_financial_diagnostic_result", None)

# ---------------- Main app ----------------

header_left, header_right = st.columns([10, 2], vertical_alignment="center")
with header_left:
    st.markdown(
        '<div style="font-size:30px;font-weight:700;line-height:1.15;margin:0.1rem 0 0.35rem 0">'
        "📈 股票公允价值监控</div>",
        unsafe_allow_html=True,
    )
with header_right:
    email_prefix = (user_email.split("@")[0] if user_email else "用户")
    with st.popover(f"{email_prefix} ▼", help=user_email or "账户"):
        st.caption("已登录")
        st.write(user_email)
        if audit_admin and st.button("Finnhub 能力诊断", use_container_width=True, key="menu_finnhub_audit"):
            st.session_state.pop("_v45_export_open", None)
            st.session_state.pop("_peer_diagnostic_open", None)
            st.session_state._finnhub_audit_open = True
            st.rerun()
        if audit_admin and st.button("财务输入诊断", use_container_width=True, key="menu_financial_diagnostic"):
            st.session_state.pop("_v45_export_open", None)
            st.session_state.pop("_peer_diagnostic_open", None)
            st.session_state._financial_diagnostic_open = True
            st.rerun()
        if audit_admin and st.button("Peer 估值诊断", use_container_width=True, key="menu_peer_diagnostic"):
            st.session_state.pop("_v45_export_open", None)
            st.session_state.pop("_finnhub_audit_open", None)
            st.session_state.pop("_financial_diagnostic_open", None)
            st.session_state._peer_diagnostic_open = True
            st.rerun()
        if audit_admin and st.button("V4.5 估值结构导出", use_container_width=True, key="menu_v45_export"):
            for diagnostic in ("_finnhub_audit_open", "_financial_diagnostic_open", "_peer_diagnostic_open"):
                st.session_state.pop(diagnostic, None)
            st.session_state._v45_export_open = True
            st.rerun()
        if st.button("账户设置", use_container_width=True, key="menu_account_settings"):
            st.session_state.account_open = True
            st.rerun()
        if st.button("修改密码", use_container_width=True, key="menu_change_password"):
            st.session_state.account_open = True
            st.session_state.account_focus = "password"
            st.rerun()
        if st.button("退出登录", use_container_width=True, key="menu_logout"):
            try:
                db.auth.sign_out()
            except Exception:
                pass
            _delete_remember_cookie(cookie_manager, "logout_delete_cookie")
            clear_auth_session()
            st.rerun()

if st.session_state.get("_v45_export_open"):
    v45_reference_rows = {}
    def v45_reference_readonly(ticker):
        if ticker not in v45_reference_rows:
            from datetime import timedelta
            from calibration_snapshot_guard import reference_snapshot
            today_row = get_cloud_snapshot(db, user_id, ticker, date.today().isoformat())
            current_ref = reference_snapshot(today_row, ticker)
            if current_ref and current_ref.get('healthy_reference'):
                v45_reference_rows[ticker] = today_row
            else:
                prior_row = get_cloud_snapshot(db, user_id, ticker, (date.today()-timedelta(days=1)).isoformat())
                prior_ref = reference_snapshot(prior_row, ticker)
                v45_reference_rows[ticker] = prior_row if prior_ref and prior_ref.get('healthy_reference') else today_row
        return v45_reference_rows[ticker]
    def v45_display_readonly(live):
        from production_snapshot_admin import readonly_display
        try:
            return readonly_display(live,
                lambda: get_cloud_snapshot(db, user_id, live['ticker'], date.today().isoformat()))
        except Exception as exc:
            if is_rls_or_auth_error(exc):
                raise
            return dict(live, source_status='live', reliable_cache_status='storage_unavailable')
    render_snapshot_export(st, db, user_id, history_loader=history_cached,
                           fundamentals_loader=fundamentals_cached, display_resolver=v45_display_readonly,
                           reference_loader=v45_reference_readonly)
    st.stop()

if st.session_state.get("_peer_diagnostic_open"):
    def peer_internal_readonly(ticker):
        from peer_diagnostic_admin import _NoPeerRequests
        from last_reliable_valuation import resolve_live_result
        live = analyze_ticker(ticker, history_loader=history_cached,
                              fundamentals_loader=fundamentals_cached,
                              peer_mode="diagnostic", peer_provider=_NoPeerRequests())
        return resolve_live_result(live,
            lambda: get_cloud_snapshot(db, user_id, live['ticker'], date.today().isoformat()),
            lambda result: None)
    render_peer_diagnostics(st, db, user_id, internal_loader=peer_internal_readonly)
    st.stop()

if st.session_state.get("_finnhub_audit_open"):
    render_diagnostics(st, db, user_id)
    st.stop()

if st.session_state.get("_financial_diagnostic_open"):
    render_financial_diagnostics(st, db, user_id)
    st.stop()

if "nav_initialized" not in st.session_state:
    qp_boot = query_ticker_param()
    if qp_boot:
        st.session_state.nav_page = "单股分析"
        st.session_state.selected_ticker = qp_boot
        st.session_state.watch_select = qp_boot
        st.session_state._last_watch_select = qp_boot
    st.session_state.nav_initialized = True

# Apply page jumps before the nav widget is instantiated (cannot mutate widget keys after).
_pending_nav = st.session_state.pop("_pending_nav_page", None)
if _pending_nav in _LEGACY_NAV:
    _pending_nav = _LEGACY_NAV[_pending_nav]
if _pending_nav in NAV_PAGES:
    st.session_state.nav_page = _pending_nav
    st.session_state.account_open = False
# Migrate legacy nav labels still stuck in session
_cur_nav = st.session_state.get("nav_page")
if _cur_nav in _LEGACY_NAV:
    st.session_state.nav_page = _LEGACY_NAV[_cur_nav]
elif _cur_nav not in NAV_PAGES:
    st.session_state.nav_page = "产业链地图"

if hasattr(st, "segmented_control"):
    page = st.segmented_control(
        "页面",
        options=NAV_PAGES,
        default="产业链地图",
        key="nav_page",
        label_visibility="collapsed",
    ) or "产业链地图"
else:
    page = st.radio("页面", NAV_PAGES, horizontal=True, key="nav_page", label_visibility="collapsed")

# Track previous page for headline filter reset (V5.4)
_prev_nav_page = st.session_state.get("_prev_nav_page")
st.session_state._prev_nav_for_headlines = _prev_nav_page
st.session_state._prev_nav_page = page

if st.session_state.get("account_open"):
    render_account_panel(user_email, db)
    st.divider()
    st.caption("研究工具，不构成个性化投资建议。自定义股票使用通用估值假设；重要持仓应进一步校准增长率、折现率与合理估值倍数。")
    st.stop()

if page == "自选股":
    with st.expander("➕ 添加股票", expanded=False):
        with st.form("add_watchlist_form", clear_on_submit=False):
            c1, c2, c3 = st.columns([1, 1.4, 0.7])
            new_ticker = c1.text_input("股票代码", placeholder="例如 AMZN / AMD / PLTR")
            nickname = c2.text_input("备注（可选）", placeholder="例如：长期观察")
            c3.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
            add_btn = c3.form_submit_button("添加", type="primary", use_container_width=True)
        if add_btn:
            parsed = normalize_ticker(new_ticker)
            if not parsed:
                st.error("股票代码格式不正确。仅允许字母、数字、. 和 -。")
            else:
                try:
                    add_watchlist(db, user_id, parsed, nickname)
                    st.success(f"已添加 {parsed}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(public_db_error("insert", "watchlist", e, client=db))

    try:
        watch = get_watchlist(db, user_id)
    except Exception as e:
        st.error(public_db_error("select", "watchlist", e, client=db))
        st.stop()
    if not watch:
        st.info("你的自选股还是空的。可以先添加 AMZN、NVDA、MSFT 等代码。")
        st.stop()

    # Defaults kept in session; auto-save lives under 高级设置 (collapsed)
    if "dash_auto_save" not in st.session_state:
        st.session_state.dash_auto_save = True
    show_advanced_cols = st.checkbox("更多指标", value=False, key="dash_advanced_cols")
    auto_save = bool(st.session_state.dash_auto_save)

    rows = []
    progress = st.progress(0, text="正在更新自选股…")
    for i, item in enumerate(watch, start=1):
        t = item["ticker"]
        try:
            r = analyze_one(t, None, db, user_id)
            if r.get("price") is None:
                rows.append({
                    "股票": t,
                    "价格": None,
                    "状态": "数据不足",
                    "错误": r.get("analysis_error") or "行情数据暂时获取失败",
                    "内部估值": "—",
                    "置信度": "—",
                    "距公允价值%": "—",
                    "第一批区": "—",
                    "核心买入区": "—",
                    "深度价值区": "—",
                    "减仓参考区": "—",
                    "明显高估区": "—",
                    "可靠性": "—",
                    "模型分歧": "—",
                    "SMA30": None,
                    "SMA50": None,
                    "SMA200": None,
                    "备注": item.get("nickname") or "",
                    "估值类型": "—",
                    "_core_gap": float("inf"),
                })
                continue
            from last_reliable_valuation import render_cache_notice
            render_cache_notice(st, r)
            from production_reliability_governance import render_structural_notice
            render_structural_notice(st, r)
            if auto_save and r.get("price") is not None:
                save_snapshot(db, user_id, r)
            conf_u = str(r.get("confidence") or "").upper()
            if r.get("fair") is None or conf_u in {"SPECIALIZED", "UNAVAILABLE"}:
                delta_display = "—"
            else:
                d = delta_pct(r["price"], r["fair"])
                delta_display = "—" if d is None else f"{float(d):.1f}%"
            exit_zone = r.get("exit_zone")
            if conf_u in {"LOW", "SPECIALIZED", "UNAVAILABLE"}:
                trim_txt, extreme_txt = "—", "—"
            else:
                trim_txt = format_trim_zone(exit_zone)
                extreme_txt = format_extreme_zone(exit_zone)
            rows.append({
                "股票": t,
                "价格": r["price"],
                "状态": r["recommendation"],
                "内部估值": dashboard_fair_text(r),
                "市场一致目标": format_consensus_target(r.get("market_reference")),
                "内部 vs 市场": (f"{r['market_reference']['internal_vs_consensus_pct']:+.1f}%" if (r.get("market_reference") or {}).get("internal_vs_consensus_pct") is not None else "—"),
                "估值模式": r.get("valuation_mode") or "—",
                **{key: (f"{r['market_reference'][key]:.2f}x" if (r.get("market_reference") or {}).get(key) is not None else "—") for key in ("current_forward_pe", "internal_implied_forward_pe", "historical_pe_median_3y", "historical_pe_median_5y", "sector_forward_pe")},
                "置信度": confidence_zh(r.get("confidence")),
                "距公允价值%": delta_display,
                "第一批区": zone_text(r["zones"]["first"]) if r["zones"] and not r.get("hide_precise_trading_zones") else "—",
                "核心买入区": zone_text(r["zones"]["core"]) if r["zones"] and not r.get("hide_precise_trading_zones") else "—",
                "深度价值区": zone_text(r["zones"]["deep"]) if r["zones"] and not r.get("hide_precise_trading_zones") else "—",
                "减仓参考区": trim_txt,
                "明显高估区": extreme_txt,
                "可靠性": r.get("reliability_score") if r.get("reliability_score") is not None else "—",
                "模型分歧": f"{r['dispersion_pct']*100:.0f}%" if r.get("dispersion_pct") is not None else "—",
                "SMA30": r["sma30"],
                "SMA50": r["sma50"],
                "SMA200": r["sma200"],
                "备注": item.get("nickname") or "",
                "估值类型": class_label_zh(r.get("valuation_class_label"), r.get("valuation_class")),
                "_core_gap": core_zone_gap(r["price"], r.get("zones")),
            })
        except Exception as e:
            if is_rls_or_auth_error(e):
                err_text = public_db_error("upsert", "valuation_snapshots", e, client=db)
            else:
                err_text = public_analysis_error(t, e)
            rows.append({
                "股票": t,
                "价格": None,
                "状态": "数据不足",
                "错误": err_text,
                "内部估值": "—",
                "置信度": "—",
                "距公允价值%": "—",
                "第一批区": "—",
                "核心买入区": "—",
                "深度价值区": "—",
                "减仓参考区": "—",
                "明显高估区": "—",
                "可靠性": "—",
                "模型分歧": "—",
                "SMA30": None,
                "SMA50": None,
                "SMA200": None,
                "备注": item.get("nickname") or "",
                "估值类型": "—",
                "_core_gap": float("inf"),
            })
        progress.progress(i / len(watch), text=f"正在更新 {i}/{len(watch)}")
    progress.empty()

    st.caption("买入区与减仓区由内部估值、波动率、模型可靠性和安全边际规则推导，并非独立估值模型。偏差绝对值 >35% 表示模型与市场分歧显著，精确区间仅供内部模型参考。")
    df = pd.DataFrame(rows)
    for price_col in ("价格", "SMA30", "SMA50", "SMA200"):
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce").round(2)
    if "_core_gap" in df.columns:
        df = df.drop(columns=["_core_gap"])
    dashboard_columns = [
        "股票",
        "价格",
        "状态",
        "错误",
        "内部估值",
        "市场一致目标",
        "内部 vs 市场",
        "估值模式",
        "距公允价值%",
        "核心买入区",
        "减仓参考区",
        "置信度",
    ]
    if show_advanced_cols:
        dashboard_columns.extend([
            "current_forward_pe", "internal_implied_forward_pe",
            "historical_pe_median_3y", "historical_pe_median_5y", "sector_forward_pe",
            "第一批区",
            "深度价值区",
            "可靠性",
            "模型分歧",
            "SMA30",
            "SMA50",
            "SMA200",
        ])
    # V5.5: free account has no analyst price-target entitlement.
    dashboard_columns = [col for col in dashboard_columns if col not in {"市场一致目标", "内部 vs 市场"}]
    visible = [col for col in dashboard_columns if col in df.columns]
    if "错误" in visible and "错误" in df.columns:
        err_series = df["错误"]
        if err_series.isna().all() or err_series.fillna("").astype(str).str.strip().eq("").all():
            visible = [col for col in visible if col != "错误"]
    df = df.loc[:, visible]
    styled = df.style.map(style_status, subset=["状态"] if "状态" in df.columns else [])
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(560, 48 + 36 * max(len(df), 1)),
        column_config={
            "股票": st.column_config.TextColumn(width=75),
            "价格": st.column_config.NumberColumn(format="$%.2f", width=90),
            "状态": st.column_config.TextColumn(width=180),
            "内部估值": st.column_config.TextColumn(width=120),
            "置信度": st.column_config.TextColumn(width=90),
            "距公允价值%": st.column_config.TextColumn(width=105),
            "第一批区": st.column_config.TextColumn(width=150),
            "核心买入区": st.column_config.TextColumn(width=150),
            "深度价值区": st.column_config.TextColumn(width=150),
            "减仓参考区": st.column_config.TextColumn(width=140),
            "可靠性": st.column_config.TextColumn(width=80),
            "模型分歧": st.column_config.TextColumn(width=90),
            "SMA30": st.column_config.NumberColumn(format="$%.2f", width=90),
            "SMA50": st.column_config.NumberColumn(format="$%.2f", width=90),
            "SMA200": st.column_config.NumberColumn(format="$%.2f", width=90),
            "错误": st.column_config.TextColumn(width=180),
        },
    )

    jump = st.selectbox("打开单股分析", [x["ticker"] for x in watch], key="dashboard_jump_ticker", label_visibility="collapsed")
    j1, j2 = st.columns([3, 1])
    with j1:
        st.caption("选择股票后打开单股分析")
    with j2:
        if st.button("打开单股分析", type="primary", use_container_width=True):
            open_single_stock(jump)

    with st.expander("说明", expanded=False):
        st.caption(
            "可靠性评分衡量数据完整性、模型一致性及适用性，不是股票评级，也不代表未来收益概率。"
            "退出区仅在估值模型一致性与可靠性达到要求时提供精确价格；模型分歧较大时，仅显示定性高估提示。"
        )
        st.caption("颜色说明")
        cols = st.columns(4)
        for col, label in zip(
            cols,
            ["深度价值区", "核心买入区", "第一批区", "合理持有区"],
        ):
            with col:
                status_badge(label)
        cols2 = st.columns(4)
        for col, label in zip(
            cols2,
            ["偏高估区", "减仓参考区", "明显高估区", "低于深度价值区"],
        ):
            with col:
                status_badge(label)

    with st.expander("高级设置", expanded=False):
        st.checkbox(
            "自动保存今天的估值快照",
            key="dash_auto_save",
        )
        st.caption("关闭后仍可在单股分析中手动保存快照。下次刷新自选股时生效。")
        to_remove = st.selectbox("选择要删除的股票", [x["ticker"] for x in watch])
        if st.button("从自选股删除"):
            try:
                remove_watchlist(db, user_id, to_remove)
                st.success(f"已删除 {to_remove}")
                st.rerun()
            except Exception as e:
                st.error(public_db_error("delete", "watchlist", e, client=db))
        note_ticker = st.selectbox("选择要改备注的股票", [x["ticker"] for x in watch], key="note_ticker")
        new_note = st.text_input("新备注", key="watchlist_new_note")
        if st.button("保存备注"):
            try:
                update_watchlist_note(db, user_id, note_ticker, new_note)
                st.success(f"已更新 {note_ticker} 的备注")
                st.rerun()
            except Exception as e:
                st.error(public_db_error("update", "watchlist", e, client=db))

elif page == "单股分析":
    try:
        watch = get_watchlist(db, user_id)
    except Exception as e:
        st.error(public_db_error("select", "watchlist", e, client=db))
        st.stop()
    watch_tickers = [x["ticker"] for x in watch]

    qp_ticker = query_ticker_param()
    if qp_ticker and st.session_state.get("selected_ticker") != qp_ticker:
        st.session_state.selected_ticker = qp_ticker
        if qp_ticker in watch_tickers:
            st.session_state._pending_watch_select = qp_ticker
            st.session_state._last_watch_select = qp_ticker

    if not st.session_state.get("selected_ticker"):
        st.session_state.selected_ticker = watch_tickers[0] if watch_tickers else None

    # Sync selectbox key before the widget exists (cannot mutate after instantiation).
    _pending_watch = st.session_state.pop("_pending_watch_select", None)
    if _pending_watch and _pending_watch in watch_tickers:
        st.session_state.watch_select = _pending_watch
        st.session_state._last_watch_select = _pending_watch

    current = normalize_ticker(st.session_state.get("selected_ticker"))
    in_watch = bool(current and current in watch_tickers)
    idx = watch_tickers.index(current) if in_watch else None

    def _select_ticker(ticker: str):
        st.session_state.selected_ticker = ticker
        if ticker in watch_tickers:
            st.session_state._last_watch_select = ticker
            st.session_state._pending_watch_select = ticker
        try:
            st.query_params["ticker"] = ticker
        except Exception:
            pass

    # Compact one-row chrome: ← | Ticker · Name | → | watchlist | other
    n1, n2, n3, n4, n5 = st.columns([0.9, 2.2, 0.9, 1.2, 1.6], vertical_alignment="center")
    with n1:
        prev_disabled = (not in_watch) or idx == 0
        if st.button("← 上一只", disabled=prev_disabled, use_container_width=True):
            _select_ticker(watch_tickers[idx - 1])
            st.rerun()
    with n2:
        title = current or "未选择"
        name = NAMES.get(current or "", current or "")
        st.markdown(
            f"<div style='text-align:center;font-size:1.05rem;font-weight:700;line-height:1.2'>"
            f"{title} · {name}</div>",
            unsafe_allow_html=True,
        )
    with n3:
        next_disabled = (not in_watch) or idx == len(watch_tickers) - 1
        if st.button("下一只 →", disabled=next_disabled, use_container_width=True):
            _select_ticker(watch_tickers[idx + 1])
            st.rerun()
    with n4:
        if watch_tickers:
            last = st.session_state.get("_last_watch_select")
            if "watch_select" not in st.session_state:
                st.session_state.watch_select = current if in_watch else watch_tickers[0]
            chosen = st.selectbox("自选股", watch_tickers, key="watch_select", label_visibility="collapsed")
            if last is None:
                st.session_state._last_watch_select = chosen
            elif chosen != last:
                st.session_state._last_watch_select = chosen
                _select_ticker(chosen)
                st.rerun()
        else:
            st.caption("自选股为空")
    with n5:
        with st.form("manual_ticker_form", clear_on_submit=False, border=False):
            f1, f2 = st.columns([2.2, 1])
            typed = f1.text_input("分析其他股票", placeholder="AMD", label_visibility="collapsed")
            analyze_btn = f2.form_submit_button("分析", use_container_width=True)
        if analyze_btn:
            parsed = normalize_ticker(typed)
            if not parsed:
                st.error("股票代码格式不正确。")
            else:
                _select_ticker(parsed)
                st.rerun()

    if current and not in_watch:
        if st.button(f"+ 加入自选股（{current}）", key="ss_add_watch"):
            try:
                add_watchlist(db, user_id, current)
                st.success(f"已添加 {current}")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(public_db_error("insert", "watchlist", e, client=db))

    if not current:
        st.info("请选择或输入一只股票。")
        st.stop()

    # —— V5.3 单股连续页：估值 + 财报 + 事件入口 + 诊断（无二级 Tabs）——
    as_of = None  # 估值 Tab：始终最新交易日
    cache_key = (current, as_of)
    if st.session_state.get("analysis_cache_key") != cache_key:
        with st.spinner(f"正在分析 {current}…"):
            try:
                r = analyze_one(current, as_of, db, user_id)
            except Exception as e:
                st.error(public_analysis_error(current, e))
                st.stop()
        st.session_state.last_analysis = r
        st.session_state.analysis_cache_key = cache_key
    r = st.session_state.get("last_analysis")

    if r:
        from last_reliable_valuation import render_cache_notice
        render_cache_notice(st, r)
        from production_reliability_governance import render_structural_notice
        render_structural_notice(st, r)
        if r.get("snapshot_error"):
            st.error(r["snapshot_error"])
        elif r.get("analysis_error") and r.get("price") is None:
            st.error(r["analysis_error"])
        elif r.get("errors"):
            st.warning("部分数据源失败，已保留可用的价格/估值结果。")
        if (r.get("blend") or {}).get("legacy"):
            st.info("该历史快照创建于可靠性层之前，部分可靠性指标不可用。")

        conf = str(r.get("confidence") or "").upper()
        view = (r.get("blend") or {}).get("view") or primary_valuation_view(r.get("blend") or {})
        score = r.get("reliability_score")
        if r.get("fair") is None or conf in {"SPECIALIZED", "UNAVAILABLE"}:
            delta_display = "—"
        else:
            dlt = delta_pct(r["price"], r["fair"])
            delta_display = "—" if dlt is None else f"{float(dlt):.1f}%"
        exit_zone = r.get("exit_zone") or ((r.get("blend") or {}).get("exit_zone"))
        trim_txt = format_trim_zone(exit_zone) if conf not in {"LOW", "SPECIALIZED", "UNAVAILABLE"} else "—"

        # 第一屏：决策核心摘要
        status_badge(r.get("recommendation") or "—")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("价格", money(r.get("price")))
        if view.get("mode") == "specialized":
            a2.metric("内部估值", "不适用")
        elif view.get("mode") == "unavailable":
            a2.metric("内部估值", "数据不足")
        elif view.get("mode") == "indicative_range":
            _ = ("Indicative Valuation Range", "Reference midpoint")
            a2.metric(
                "参考估值区间",
                f"{money_conf(view.get('low'), 'LOW')} – {money_conf(view.get('high'), 'LOW')}",
            )
        elif view.get("mode") == "point":
            a2.metric("内部估值", money_conf(view.get("mid"), "HIGH"))
        else:
            _ = ("Fair Value Estimate", "Reasonable Range")
            a2.metric("Internal Fair Value Estimate", money_conf(view.get("mid"), conf))
        a3.metric("置信度", confidence_zh(r.get("confidence")))
        a4.metric("可靠性", f"{score}" if score is not None else "—")
        b1, b2, b3 = st.columns(3)
        b1.metric("距公允价值%", delta_display)
        b2.metric(
            "核心买入区",
            zone_text(r["zones"]["core"]) if r.get("zones") and not r.get("hide_precise_trading_zones") else "—",
        )
        b3.metric("减仓参考区", trim_txt)

        if view.get("mode") == "indicative_range":
            st.caption(
                f"参考中枢：{money_conf(view.get('mid'), 'LOW')}  ·  估值不确定性较高，区间是主信息。"
            )
        elif view.get("mode") == "specialized":
            st.info("传统估值模型不适用，需要专项场景估值。仅显示技术观察。")

        # 买入 / 持有 / 高估 / 减仓区
        if r.get("zones") and not r.get("hide_precise_trading_zones"):
            labels = (r["zones"] or {}).get("labels") or {}
            z1, z2, z3 = st.columns(3)
            z1.info(f"**{labels.get('first', '第一批区')}**\n\n{zone_text(r['zones']['first'])}")
            z2.success(f"**{labels.get('core', '核心买入区')}**\n\n{zone_text(r['zones']['core'])}")
            z3.success(f"**{labels.get('deep', '深度价值区')}**\n\n{zone_text(r['zones']['deep'])}")
            if conf == "LOW":
                st.warning("估值不确定性较高，此价格区仅为模型参考。")
            mode = (exit_zone or {}).get("display_mode") if isinstance(exit_zone, dict) else None
            if conf in {"HIGH", "MEDIUM"} and isinstance(exit_zone, dict) and mode == "precise":
                e1, e2, e3, e4 = st.columns(4)
                e1.info(f"**合理持有区**\n\n≤ {money(exit_zone.get('hold_upper_price'))}")
                e2.warning(
                    f"**偏高估区**\n\n{money(exit_zone.get('hold_upper_price'))} – {money(exit_zone.get('trim_price'))}"
                )
                e3.warning(f"**减仓参考区**\n\n{format_trim_zone(exit_zone)}")
                e4.error(f"**明显高估区**\n\n{format_extreme_zone(exit_zone)}")
                st.caption("减仓参考区基于当前估值模型与安全边际，不代表个性化投资建议。")
                render_valuation_band(r)
            elif conf in {"HIGH", "MEDIUM"} and mode == "qualitative":
                disp = r.get("dispersion_pct")
                disp_txt = f"{disp*100:.0f}%" if disp is not None else "—"
                st.warning("**退出估值：低确定性**")
                st.write(f"**原因：** 模型分歧 {disp_txt}")
                st.write(f"**当前解读：** {r.get('recommendation')}")
                st.caption("由于估值模型分歧较大，不提供精确减仓价格。")
            elif conf == "LOW":
                st.caption("低置信度不生成精确减仓价；若价格明显高于参考估值区间，状态显示「估值偏高（低置信度）」。")
        elif (r.get("blend") or {}).get("specialized") or conf == "SPECIALIZED":
            st.info("传统估值模型不适用，需要专项场景估值。仅显示技术指标，不生成价值买入区。")
        else:
            st.info("有效估值模型不足，暂不生成买入区。")

        # SMA 第二行
        s1, s2, s3 = st.columns(3)
        s1.metric("SMA30", money(r.get("sma30")), pct(delta_pct(r.get("price"), r.get("sma30"))) if r.get("sma30") else None)
        s2.metric("SMA50", money(r.get("sma50")), pct(delta_pct(r.get("price"), r.get("sma50"))) if r.get("sma50") else None)
        s3.metric("SMA200", money(r.get("sma200")), pct(delta_pct(r.get("price"), r.get("sma200"))) if r.get("sma200") else None)
        if r.get("vp"):
            st.caption(
                f"近一年成交密集区（估算）：{money(r['vp']['low'])} – {money(r['vp']['high'])}"
            )

        # 财报与业务（内嵌，无 Tab）
        try:
            from industry.company_panels import render_earnings_inline, render_latest_event_teaser

            render_earnings_inline(current)
            from external_reference_ui import render_external_reference
            render_external_reference(current, r)
            render_latest_event_teaser(current, open_headlines_cb=open_headlines)
        except Exception as exc:
            st.warning(f"财报/事件模块暂不可用：{type(exc).__name__}")

        with st.expander("估值模型与诊断", expanded=False):
            meta1, meta2, meta3 = st.columns(3)
            meta1.metric("估值类型", class_label_zh(r.get("valuation_class_label"), r.get("valuation_class")))
            meta2.metric("置信度", confidence_zh(r.get("confidence")))
            meta3.metric("可靠性评分", f"{score} / 100" if score is not None else "—")
            rel = (r.get("blend") or {}).get("reliability") or {}
            disp = r.get("dispersion_pct")
            inc = rel.get("model_count_included")
            total = rel.get("model_count_total")
            d1, d2, d3 = st.columns(3)
            d1.metric("模型分歧", f"{disp*100:.0f}%" if disp is not None else "—")
            d2.metric("有效模型", f"{inc} / {total}" if inc is not None and total is not None else "—")
            d3.metric("数据质量", rel.get("data_quality") or "—")
            cap = blend_caption(r.get("blend"))
            if cap:
                st.caption(cap)
            if r.get("note"):
                st.caption(r["note"])
            model_rows = []
            model_list = (r.get("blend") or {}).get("model_list") or []
            if not model_list:
                model_list = [obj for obj in (r.get("pe"), r.get("dcf"), r.get("growth")) if obj]
            for obj in model_list:
                usable = bool(obj) and obj.get("valid") and not obj.get("outlier") and obj.get("applicable") is not False
                model_rows.append({
                    "模型": model_label_zh(obj),
                    "低值": obj.get("low") if usable else None,
                    "中枢": obj.get("mid") if usable else None,
                    "高值": obj.get("high") if usable else None,
                    "状态": model_status_text(obj),
                    "置信度": confidence_zh(obj.get("confidence")),
                })
            if model_rows:
                st.dataframe(
                    pd.DataFrame(model_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "低值": st.column_config.NumberColumn(format="$%.2f"),
                        "中枢": st.column_config.NumberColumn(format="$%.2f"),
                        "高值": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )
            if r.get("history") is not None:
                st.line_chart(r["history"].tail(260)[["Close", "SMA30", "SMA50", "SMA200"]], use_container_width=True)
            render_cycle_panel(r)
            render_model_explanations(r)
            render_valuation_diagnostics(r)
            render_exit_diagnostics(r)

        # Historical snapshots retained via list_snapshots / save_snapshot (UI history tab removed).
        _ = list_snapshots  # keep loader wired for future history charts
        if st.button("保存当前估值快照"):
            try:
                save_snapshot(db, user_id, r)
                st.success("已保存。")
            except Exception as e:
                st.error(public_db_error("upsert", "valuation_snapshots", e, client=db))

elif page in {"产业链地图", "市场格局"}:
    if not _INDUSTRY_MAP_AVAILABLE or render_industry_page is None:
        st.error("产业模块尚未加载完成。请确认部署已包含产业页。")
        if _INDUSTRY_IMPORT_ERROR is not None:
            st.code(
                f"{type(_INDUSTRY_IMPORT_ERROR).__name__}: {_INDUSTRY_IMPORT_ERROR}\n\n"
                + "".join(
                    traceback.format_exception(
                        type(_INDUSTRY_IMPORT_ERROR),
                        _INDUSTRY_IMPORT_ERROR,
                        _INDUSTRY_IMPORT_ERROR.__traceback__,
                    )
                )
            )
        st.stop()
    try:
        watch_ind = get_watchlist(db, user_id)
    except Exception as e:
        st.error(public_db_error("select", "watchlist", e, client=db))
        st.stop()

    render_industry_page(
        watchlist_tickers=watch_ind,
        mode="landscape" if page == "市场格局" else "map",
    )

elif page == "头等大事":
    try:
        watch = get_watchlist(db, user_id)
    except Exception as e:
        st.error(public_db_error("select", "watchlist", e, client=db))
        st.stop()
    tickers = [x["ticker"] for x in watch]
    if not tickers:
        st.info("请先添加自选股。")
        st.stop()

    # V5.4: direct top-nav → all watchlist; sticky ticker only via single-stock deep link
    _arrived_from = st.session_state.get("_prev_nav_for_headlines")
    if _arrived_from != "头等大事":
        filter_ticker = st.session_state.pop("headline_filter_ticker", None)
        if filter_ticker:
            st.session_state["headline_ticker_filter"] = filter_ticker
        else:
            st.session_state.pop("headline_ticker_filter", None)
            st.session_state.pop("headline_selected_event_id", None)
            st.session_state.pop("headline_selected_event", None)

    range_opt = st.radio(
        "时间范围",
        ["过去24小时", "本周", "本季度", "即将发生"],
        horizontal=True,
        key="headline_range",
        label_visibility="collapsed",
    )
    try:
        from industry.events_provider import get_company_events, range_bounds
        from industry.news import news_source_status, translate_ui_term

        bounds = range_bounds(range_opt)
        events = get_company_events(
            tickers,
            start_time=bounds["start_time"],
            end_time=bounds["end_time"],
            include_upcoming=bounds["include_upcoming"],
            range_key=range_opt,
        )
        src_status = news_source_status()
    except Exception as exc:
        st.warning(f"事件数据暂不可用：{type(exc).__name__}")
        events = []
        src_status = {"message_if_empty": "当前未配置实时新闻源。"}

    ticker_filter = st.session_state.get("headline_ticker_filter")
    if ticker_filter:
        events = [e for e in events if ("GOOG" if str(ticker_filter).upper() == "GOOGL" else str(ticker_filter).upper()) in e.get("primary_tickers", [str(e.get("ticker") or "").upper()])]
        c1, c2 = st.columns([4, 1])
        with c1:
            st.caption(f"已筛选：{ticker_filter}")
        with c2:
            if st.button("清除筛选", key="clear_headline_filter"):
                st.session_state.pop("headline_ticker_filter", None)
                st.session_state.pop("headline_filter_ticker", None)
                st.session_state.pop("headline_selected_event_id", None)
                st.session_state.pop("headline_selected_event", None)
                st.rerun()

    if not src_status.get("demo_mode") and src_status.get("live_configured"):
        from finnhub_service import get_finnhub_provider, STATUS_TEXT
        from industry.news.finnhub_live import upcoming_events
        from datetime import datetime
        from zoneinfo import ZoneInfo
        checked_tickers = [ticker_filter] if ticker_filter else tickers
        if range_opt == "即将发生":
            _, module_statuses = upcoming_events(checked_tickers, datetime.now(ZoneInfo("Europe/London")).date())
            for ticker, status in module_statuses.items():
                if status == "NO_DATA":
                    st.caption(f"{ticker}：Finnhub 暂无该公司未来财报日期")
                elif status != "AVAILABLE":
                    st.caption(f"{ticker}：{STATUS_TEXT.get(status, '暂不可用')}")
        else:
            for ticker in checked_tickers:
                reference = get_finnhub_provider().get_company_news(ticker, str(bounds['start_time'])[:10], str(bounds['end_time'])[:10])
                if reference['status'] not in ('AVAILABLE', 'NO_DATA'):
                    st.caption(f"{ticker}：{STATUS_TEXT.get(reference['status'], '暂不可用')}")
    show_rows = events
    selected = st.session_state.get("headline_selected_event")
    selected_id = st.session_state.get("headline_selected_event_id")
    if selected_id and selected and selected.get("event_id") == selected_id and range_opt == "本季度":
        allowed = set(tickers) | ({"GOOG"} if "GOOGL" in tickers else set())
        if allowed.intersection(selected.get("primary_tickers") or [selected.get("ticker")]):
            show_rows = [selected] + [e for e in show_rows if e.get("event_id") != selected_id]
    if not show_rows:
        empty_msg = src_status.get("message_if_empty")
        if empty_msg and not src_status.get("demo_mode") and not src_status.get("live_configured"):
            st.info("实时新闻源未配置。")
        elif range_opt == "即将发生":
            st.info("本周期没有发现明显改变投资逻辑的重大事件。")
        else:
            st.info("本周期没有发现明显改变投资逻辑的重大事件。")
    else:
        for i, e in enumerate(show_rows):
            t = e.get("ticker") or "—"
            involved = " / ".join(e.get("involved_tickers") or [t])
            headline = e.get("headline") or "（无标题）"
            imp = e.get("importance") or "一般"
            areas = e.get("impact_areas") or []
            area = " / ".join(translate_ui_term(a) for a in areas) if areas else translate_ui_term(e.get("impact_area") or "产品")
            ed = e.get("event_date") or e.get("event_time") or "—"
            # Compact collapsed row: Ticker · Headline · Date · Importance · Impact
            label = f"{involved} · {imp} · {headline} · {ed} · {area}"
            with st.expander(label, expanded=e.get("event_id") == st.session_state.get("headline_selected_event_id")):
                st.markdown(f"**{t} · {headline}**")
                st.caption(f"日期：{ed}　重要性：{imp}　影响：{area}")

                if e.get("calendar"):
                    cal = e["calendar"]
                    st.caption(f"财政季度：FY{cal.get('year') or '—'} Q{cal.get('quarter') or '—'} · 每股收益预期：{money(cal.get('epsEstimate'))} · 收入预期：{money(cal.get('revenueEstimate'))}")
                st.caption(f"涉及：{involved}")
                if e.get('original_headline'):
                    st.caption('原英文标题：' + e['original_headline'])
                st.markdown("**【一句话结论】**")
                st.write(e.get('conclusion') or e.get('short_summary') or '—')
                st.markdown("**【发生了什么】**")
                for fact in e.get('facts') or [e.get('what_happened') or '—']:
                    st.write('• ' + fact)
                if e.get('summary_status') == 'PARTIAL_SUMMARY':
                    st.caption('原始摘要仅能提取一项具体事实，更多细节请阅读原文。')

                st.markdown("**【为什么重要】**")
                st.write(e.get("why_it_matters") or "—")

                impact = e.get("impact_summary") or {}
                if isinstance(impact, dict) and impact:
                    st.markdown("**【影响判断】**")
                    for k, v in impact.items():
                        st.markdown(f"- {translate_ui_term(k)}：{translate_ui_term(v)}")

                watch_next = e.get("watch_next") or []
                if watch_next:
                    st.markdown("**【接下来关注】**")
                    for w in watch_next:
                        st.markdown(f"- {w}")

                src = e.get("source_name") or "—"
                url = e.get("source_url") or ""
                pub = e.get("published_at") or ed
                st.markdown("**【来源】**")
                st.caption(f"{src} · 发布：{pub}")
                if url:
                    st.markdown(f"[阅读全文 →]({url})")
                if t and t != "—":
                    if st.button(t, key=f"headline_open_{t}_{i}", help=f"打开 {t} 单股分析"):
                        open_single_stock(t)


else:
    st.info("未知页面。")

st.caption("研究工具，不构成个性化投资建议。")
