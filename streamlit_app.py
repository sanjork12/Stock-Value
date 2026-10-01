from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import os
import pandas as pd
import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client, Client

from mag7_monitor import (
    add_indicators,
    get_history,
    volume_profile_zone,
    get_live_fundamentals,
    buy_zones,
    classify_price,
    fnum,
)
from valuation_engine import (
    CLASS_LABELS,
    MODEL_VERSION,
    can_emit_buy_zones,
    normalize_ticker,
    valuate,
)

st.set_page_config(
    page_title="Stock Fair Value Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

NAV_PAGES = ["自选股", "单股分析", "历史快照", "账户"]

logger = logging.getLogger("stock_fair_value_monitor")
REMEMBER_COOKIE = "stock_monitor_refresh"
REMEMBER_DAYS = 30


def inject_layout_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="stSidebarCollapsedControl"] {display: none;}
        [data-testid="stHeader"] {background: transparent;}
        .block-container {
            padding-top: 1.1rem;
            padding-left: 2rem;
            padding-right: 2rem;
            max-width: 100%;
        }
        div[data-testid="stPopover"] > button {
            width: 2.35rem;
            height: 2.35rem;
            min-height: 2.35rem;
            padding: 0;
            border-radius: 999px;
            font-weight: 700;
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
    "观察 / 等回调": ("#F3F4F6", "#4B5563", "⚪"),
    "仅技术观察": ("#F3F4F6", "#4B5563", "⚪"),
    "低于深度价值区": ("#BBF7D0", "#14532D", "🟢"),
    "数据不足": ("#FEE2E2", "#991B1B", "🔴"),
}


def money(x):
    if x is None:
        return "—"
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "—"


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


def _apply_access_token(client: Client, access_token: str) -> None:
    """A newly created client is anonymous until the user JWT is attached to PostgREST."""
    try:
        client.postgrest.auth(access_token)
    except Exception:
        logger.warning("failed to apply access token to postgrest client")


def _save_remember_cookie(cookie_manager, refresh_token: str, widget_key: str) -> None:
    if not cookie_manager or not refresh_token:
        return
    try:
        cookie_manager.set(
            REMEMBER_COOKIE,
            refresh_token,
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


MODEL_LABELS = {
    "pe": "P/E",
    "dcf": "DCF",
    "growth": "Growth / PEG",
    "forward_pe": "Forward P/E",
    "normalized_pe": "Normalized P/E",
    "growth_adjusted_pe": "Growth-adjusted P/E",
    "normalized_fcf_dcf": "Normalized FCF DCF",
    "price_to_book_roe": "P/B × ROE",
    "residual_income": "Residual Income",
    "ev_ebitda": "EV/EBITDA",
    "revenue_multiple": "Revenue Multiple",
    "normalized_cycle_earnings": "Cycle-normalized Earnings",
    "unsupported": "Unsupported / specialized",
}


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
        return f"✓ {obj.get('confidence') or 'medium'}"
    return "无数据"


def render_valuation_diagnostics(r: dict):
    f = r.get("financials") or {}
    blend = r.get("blend") or {}
    profile = blend.get("profile") or {}
    st.caption(
        f"数据来源：{r.get('data_source') or 'Yahoo Finance / yfinance'}　"
        f"财务数据期间：{f.get('fcf_period') or '—'}　"
        f"价格日期：{r.get('date') or '—'}　"
        f"估值计算时间：{r.get('valuation_run_at') or '—'}　"
        f"模型版本：{r.get('model_version') or '—'}"
    )
    with st.expander("估值诊断"):
        lines = [
            f"**估值类型**: {profile.get('valuation_class_label') or r.get('valuation_class_label') or '—'}",
            f"**置信度**: {r.get('confidence') or '—'}",
            f"**行业**: {f.get('sector') or '—'} / {f.get('industry') or '—'}",
        ]
        if blend.get("warnings"):
            if "high_valuation_uncertainty" in blend["warnings"]:
                lines.append("**High valuation uncertainty**: 模型分歧超过 60%。")
            lines.append("警告：" + ", ".join(blend["warnings"]))
        model_list = blend.get("model_list") or list((blend.get("models") or {}).values())
        if not model_list:
            model_list = [obj for obj in (r.get("pe"), r.get("dcf"), r.get("growth")) if obj]
        for obj in model_list:
            inputs = obj.get("inputs") or {}
            lines.append(f"**{obj.get('name') or obj.get('model_id')}**")
            lines.append(f"- 状态: {model_status_text(obj)} {money(obj.get('mid'))}")
            if obj.get("reason"):
                lines.append(f"- reason: {obj.get('reason')}")
            for key, value in list(inputs.items())[:8]:
                lines.append(f"- {key}: {value}")
        st.markdown("\n".join(lines))


def blend_caption(blend) -> str:
    if not blend:
        return ""
    included = [MODEL_LABELS.get(name, name) for name in blend.get("included") or []]
    excluded = [MODEL_LABELS.get(item.get("name"), item.get("name")) for item in blend.get("excluded") or []]
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
        parts.append("High valuation uncertainty")
    return "　".join(parts)


def recommendation_label(r):
    conf = str((r.get("blend") or {}).get("confidence") or r.get("confidence") or "").upper()
    if conf in {"SPECIALIZED", "UNAVAILABLE"} or not r.get("zones") or r.get("price") is None:
        return "仅技术观察"
    z = r["zones"]
    p = r["price"]
    deep = z.get("deep") or (None, None)
    core = z.get("core") or (None, None)
    first = z.get("first") or (None, None)
    if deep[0] is not None and p < deep[0]:
        label = "低于深度价值区"
    elif deep[0] is not None and deep[1] is not None and deep[0] <= p <= deep[1]:
        label = "深度价值区"
    elif core[0] is not None and core[1] is not None and core[0] <= p <= core[1]:
        label = "核心买入区"
    elif first[0] is not None and first[1] is not None and first[0] <= p <= first[1]:
        label = "第一批区"
    elif first[1] is not None and p <= first[1] * 1.05:
        label = "接近第一批区"
    else:
        label = "观察 / 等回调"
    if conf == "LOW":
        return f"{label}（低置信度）"
    return label


def status_badge(label: str):
    base = str(label).replace("（低置信度）", "")
    bg, fg, icon = STATUS_META.get(base, ("#F3F4F6", "#4B5563", "⚪"))
    st.markdown(
        f'<span style="background:{bg};color:{fg};padding:0.35rem 0.7rem;border-radius:999px;font-weight:700">{icon} {label}</span>',
        unsafe_allow_html=True,
    )


def style_status(v):
    base = str(v).replace("（低置信度）", "")
    bg, fg, _ = STATUS_META.get(base, ("#FFFFFF", "#111827", ""))
    return f"background-color:{bg}; color:{fg}; font-weight:700"


def get_cloud_snapshot(sb: Client, user_id: str, ticker: str, as_of: str):
    current_user_id = assert_live_session(sb, user_id)
    try:
        res = (
            sb.table("valuation_snapshots")
            .select("*")
            .eq("user_id", current_user_id)
            .eq("ticker", ticker)
            .lte("snapshot_date", as_of)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as exc:
        if is_rls_or_auth_error(exc):
            raise
        logger.exception("snapshot select failed ticker=%s", ticker)
        return None


def analyze_one(ticker: str, as_of: str | None, sb: Client | None = None, user_id: str | None = None):
    ticker = normalize_ticker(ticker) or str(ticker).upper().strip()
    df = history_cached(ticker, as_of)
    row = df.iloc[-1]
    price = float(row["Close"])
    trade_date = pd.Timestamp(df.index[-1]).date().isoformat()
    sma30 = fnum(row.get("SMA30"))
    sma50 = fnum(row.get("SMA50"))
    sma200 = fnum(row.get("SMA200"))
    vp = volume_profile_zone(df)

    historical = bool(as_of and pd.Timestamp(as_of).date() < date.today())
    pe = dcf = growth = None
    fair = None
    note = ""
    blend = None
    financials = None
    snap = None
    snap_zones = None
    valuation_run_at = datetime.now(timezone.utc).isoformat()

    if historical:
        snap = get_cloud_snapshot(sb, user_id, ticker, as_of) if sb and user_id else None
        if snap:
            raw = snap.get("raw") if isinstance(snap.get("raw"), dict) else {}
            pe = snap.get("pe_model")
            dcf = snap.get("dcf_model")
            growth = snap.get("growth_model")
            fair = snap.get("fair_value")
            vclass = snap.get("valuation_class") or raw.get("valuation_class")
            models_json = snap.get("models_json") or raw.get("models_json") or {}
            if isinstance(models_json, dict):
                model_list = list(models_json.values())
                included = list(models_json.keys())
            elif isinstance(models_json, list):
                model_list = models_json
                included = [obj.get("model_id") or obj.get("name") for obj in model_list if obj]
            else:
                model_list = [obj for obj in (pe, dcf, growth) if obj]
                included = []
            conf = (snap.get("confidence") or raw.get("confidence") or "MEDIUM")
            if isinstance(conf, str):
                conf = conf.upper()
            blend = {
                "fair": fair,
                "confidence": conf,
                "profile": {
                    "valuation_class": vclass,
                    "valuation_class_label": CLASS_LABELS.get(vclass, vclass),
                },
                "models": models_json if isinstance(models_json, dict) else {},
                "model_list": model_list,
                "model_version": snap.get("model_version") or raw.get("model_version") or "legacy",
                "insufficient_models": fair is None,
                "specialized": conf == "SPECIALIZED",
                "included": included,
            }
            if snap.get("first_low") is not None:
                snap_zones = {
                    "first": (snap.get("first_low"), snap.get("first_high")),
                    "core": (snap.get("core_low"), snap.get("core_high")),
                    "deep": (snap.get("deep_low"), snap.get("deep_high")),
                }
            note = f"历史估值使用 {snap['snapshot_date']} 保存的云端估值快照。"
        else:
            note = "该日期没有历史估值快照，仅显示技术数据。"
    else:
        financials = fundamentals_cached(ticker)
        blend = valuate(ticker, financials)
        models = blend.get("models") or {}
        pe = models.get("forward_pe") or models.get("normalized_pe") or models.get("price_to_book_roe")
        dcf = models.get("normalized_fcf_dcf") or models.get("residual_income")
        growth = models.get("growth_adjusted_pe") or models.get("revenue_multiple")
        fair = blend.get("fair")
        class_label = (blend.get("profile") or {}).get("valuation_class_label") or "Generic"
        if blend.get("specialized") or blend.get("confidence") in {"SPECIALIZED", "UNAVAILABLE"}:
            note = f"估值类型：{class_label}。需要专项估值模型，暂不给出综合公允价值。"
        else:
            note = f"估值类型：{class_label}。使用 V4 sector-aware 模型组合。"
        if blend.get("excluded"):
            note += " 部分模型已排除。"
        if "high_valuation_uncertainty" in (blend.get("warnings") or []):
            note += " High valuation uncertainty。"

    if historical:
        conf = str((blend or {}).get("confidence") or "").upper()
        if snap_zones and snap_zones["first"][0] is not None and conf not in {"SPECIALIZED", "UNAVAILABLE"}:
            zones = snap_zones
        elif fair and conf not in {"SPECIALIZED", "UNAVAILABLE"}:
            zones = buy_zones(fair, vp["mid"] if vp else None, sma200)
        else:
            zones = None
    else:
        zones = buy_zones(fair, vp["mid"] if vp else None, sma200) if can_emit_buy_zones(blend) else None
    display_name = (financials or {}).get("long_name") or NAMES.get(ticker, ticker)

    r = {
        "ticker": ticker,
        "name": display_name,
        "date": trade_date,
        "price": price,
        "sma30": sma30,
        "sma50": sma50,
        "sma200": sma200,
        "vp": vp,
        "pe": pe,
        "dcf": dcf,
        "growth": growth,
        "fair": fair,
        "zones": zones,
        "note": note,
        "state": classify_price(price, fair) if fair else "技术面模式",
        "history": df,
        "blend": blend,
        "financials": financials,
        "valuation_run_at": valuation_run_at,
        "data_source": (financials or {}).get("data_source") or "Yahoo Finance / yfinance",
        "valuation_class": (blend or {}).get("profile", {}).get("valuation_class") if blend else None,
        "valuation_class_label": (blend or {}).get("profile", {}).get("valuation_class_label") if blend else None,
        "confidence": (blend or {}).get("confidence"),
        "model_version": (blend or {}).get("model_version") or MODEL_VERSION,
    }
    r["recommendation"] = recommendation_label(r)
    return r


def save_snapshot(sb: Client, user_id: str, r: dict):
    current_user_id = assert_live_session(sb, user_id)
    z = r.get("zones") or {}
    vp = r.get("vp") or {}
    payload = {
        "user_id": current_user_id,
        "ticker": r["ticker"],
        "snapshot_date": r["date"],
        "price": r.get("price"),
        "sma30": r.get("sma30"),
        "sma50": r.get("sma50"),
        "sma200": r.get("sma200"),
        "volume_zone_low": vp.get("low"),
        "volume_zone_high": vp.get("high"),
        "fair_value": r.get("fair"),
        "pe_model": r.get("pe"),
        "dcf_model": r.get("dcf"),
        "growth_model": r.get("growth"),
        "first_low": z.get("first", [None, None])[0] if z else None,
        "first_high": z.get("first", [None, None])[1] if z else None,
        "core_low": z.get("core", [None, None])[0] if z else None,
        "core_high": z.get("core", [None, None])[1] if z else None,
        "deep_low": z.get("deep", [None, None])[0] if z else None,
        "deep_high": z.get("deep", [None, None])[1] if z else None,
        "status": r.get("recommendation"),
        "raw": {
            "note": r.get("note"),
            "valuation_class": r.get("valuation_class"),
            "confidence": r.get("confidence"),
            "models_json": (r.get("blend") or {}).get("models"),
            "model_version": r.get("model_version") or MODEL_VERSION,
            "weights_used": (r.get("blend") or {}).get("weights_used"),
        },
    }
    extra = {
        "valuation_class": r.get("valuation_class"),
        "confidence": r.get("confidence"),
        "models_json": (r.get("blend") or {}).get("models"),
        "model_version": r.get("model_version") or MODEL_VERSION,
    }
    try:
        sb.table("valuation_snapshots").upsert(
            {**payload, **extra}, on_conflict="user_id,ticker,snapshot_date"
        ).execute()
    except Exception:
        sb.table("valuation_snapshots").upsert(
            payload, on_conflict="user_id,ticker,snapshot_date"
        ).execute()


def list_snapshots(sb: Client, user_id: str, ticker: str):
    current_user_id = assert_live_session(sb, user_id)
    columns = "snapshot_date,price,fair_value,sma30,sma50,sma200,first_low,first_high,core_low,core_high,deep_low,deep_high,status,valuation_class,confidence,model_version"
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
    except Exception:
        res = (
            sb.table("valuation_snapshots")
            .select(legacy)
            .eq("user_id", current_user_id)
            .eq("ticker", ticker)
            .order("snapshot_date", desc=True)
            .execute()
        )
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
    """Restore tokens from the remember-me cookie into this Streamlit session.

    The cookie stores a refresh token only. Passwords are never stored.
    """
    if st.session_state.get("authenticated") and st.session_state.get("access_token"):
        return

    try:
        saved_refresh = cookie_manager.get(REMEMBER_COOKIE)
    except Exception:
        saved_refresh = None
    if not saved_refresh:
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
    st.title("📈 Stock Fair Value Monitor")
    st.caption("股票估值、均线、买入区与长期跟踪")

    left, center, right = st.columns([1, 1.15, 1])
    with center:
        tab_login, tab_signup = st.tabs(["登录", "注册"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("邮箱", placeholder="you@example.com")
                password = st.text_input("密码", type="password")
                remember = st.checkbox("记住登录状态 30 天", value=True)
                submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
            if submitted:
                try:
                    anon = make_anon_client()
                    resp = anon.auth.sign_in_with_password({"email": email.strip(), "password": password})
                    if not resp or not resp.user or not resp.session:
                        st.error("登录失败：未获得有效会话，请重试。")
                    else:
                        persist_auth_session(resp.user, resp.session)
                        if remember:
                            _save_remember_cookie(
                                cookie_manager,
                                resp.session.refresh_token,
                                "remember_login_cookie",
                            )
                        else:
                            _delete_remember_cookie(cookie_manager, "clear_remember_cookie")
                        st.rerun()
                except Exception:
                    logger.exception("login failed")
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
                    except Exception:
                        logger.exception("signup failed")
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

# ---------------- Main app ----------------

header_left, header_right = st.columns([12, 1], vertical_alignment="center")
with header_left:
    st.title("📈 Stock Fair Value Monitor")
    st.caption("自选股数据库 + Sector-aware 公允价值 + SMA30/50/200 + 成交密集区 + 分层买入区")
with header_right:
    avatar = (user_email[:1] if user_email else "U").upper()
    with st.popover(avatar, help=user_email or "账户"):
        st.caption("已登录")
        st.write(user_email)
        if st.button("退出登录", use_container_width=True):
            try:
                db.auth.sign_out()
            except Exception:
                pass
            _delete_remember_cookie(cookie_manager, "logout_delete_cookie")
            clear_auth_session()
            st.rerun()

if "nav_initialized" not in st.session_state:
    qp_boot = query_ticker_param()
    if qp_boot:
        st.session_state.nav_page = "单股分析"
        st.session_state.selected_ticker = qp_boot
        st.session_state.watch_select = qp_boot
        st.session_state._last_watch_select = qp_boot
    st.session_state.nav_initialized = True

if hasattr(st, "segmented_control"):
    page = st.segmented_control(
        "页面",
        options=NAV_PAGES,
        default="自选股",
        key="nav_page",
        label_visibility="collapsed",
    ) or "自选股"
else:
    page = st.radio("页面", NAV_PAGES, horizontal=True, key="nav_page", label_visibility="collapsed")


if page == "自选股":
    st.subheader("我的自选股")
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

    auto_save = st.checkbox("自动保存今天的估值快照", value=True)
    rows = []
    progress = st.progress(0, text="正在更新自选股…")
    for i, item in enumerate(watch, start=1):
        t = item["ticker"]
        try:
            r = analyze_one(t, None, db, user_id)
            if auto_save:
                save_snapshot(db, user_id, r)
            rows.append({
                "股票": t,
                "备注": item.get("nickname") or "",
                "价格": r["price"],
                "SMA30": r["sma30"],
                "SMA50": r["sma50"],
                "SMA200": r["sma200"],
                "估值类型": r.get("valuation_class_label") or "—",
                "公允价值": r["fair"],
                "置信度": r.get("confidence") or "—",
                "距公允价值%": delta_pct(r["price"], r["fair"]),
                "第一批区": zone_text(r["zones"]["first"]) if r["zones"] else "—",
                "核心买入区": zone_text(r["zones"]["core"]) if r["zones"] else "—",
                "深度价值区": zone_text(r["zones"]["deep"]) if r["zones"] else "—",
                "状态": r["recommendation"],
                "_core_gap": core_zone_gap(r["price"], r.get("zones")),
            })
        except Exception as e:
            err_text = (
                public_db_error("upsert", "valuation_snapshots", e, client=db)
                if is_rls_or_auth_error(e)
                else "数据不足"
            )
            rows.append({"股票": t, "备注": item.get("nickname") or "", "状态": "数据不足", "错误": err_text, "_core_gap": float("inf")})
        progress.progress(i / len(watch), text=f"正在更新 {i}/{len(watch)}")
    progress.empty()

    df = pd.DataFrame(rows)
    sort_opt = st.selectbox("排序", ["ticker", "状态", "距离核心买入区"], key="dash_sort")
    if "_core_gap" in df.columns:
        if sort_opt == "ticker":
            df = df.sort_values("股票", kind="stable")
        elif sort_opt == "状态":
            df = df.sort_values("状态", kind="stable")
        else:
            df = df.sort_values("_core_gap", kind="stable")
        df = df.drop(columns=["_core_gap"])
    styled = df.style.map(style_status, subset=["状态"])
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "价格": st.column_config.NumberColumn(format="$%.2f"),
            "SMA30": st.column_config.NumberColumn(format="$%.2f"),
            "SMA50": st.column_config.NumberColumn(format="$%.2f"),
            "SMA200": st.column_config.NumberColumn(format="$%.2f"),
            "公允价值": st.column_config.NumberColumn(format="$%.2f"),
            "距公允价值%": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    st.markdown("#### 颜色说明")
    cols = st.columns(6)
    for col, label in zip(cols, ["低于深度价值区", "深度价值区", "核心买入区", "第一批区", "观察 / 等回调", "仅技术观察"]):
        with col:
            status_badge(label)

    jump = st.selectbox("在单股分析中打开", [x["ticker"] for x in watch], key="dashboard_jump_ticker")
    if st.button("打开单股分析", type="primary"):
        st.session_state.selected_ticker = jump
        st.session_state.watch_select = jump
        st.session_state._last_watch_select = jump
        st.session_state.nav_page = "单股分析"
        try:
            st.query_params["ticker"] = jump
        except Exception:
            pass
        st.rerun()

    with st.expander("管理自选股"):
        to_remove = st.selectbox("选择要删除的股票", [x["ticker"] for x in watch])
        if st.button("从自选股删除"):
            try:
                remove_watchlist(db, user_id, to_remove)
                st.success(f"已删除 {to_remove}")
                st.rerun()
            except Exception as e:
                st.error(public_db_error("delete", "watchlist", e, client=db))
        st.markdown("修改备注")
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
    st.subheader("单股分析")
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
            st.session_state.watch_select = qp_ticker
            st.session_state._last_watch_select = qp_ticker

    if not st.session_state.get("selected_ticker"):
        st.session_state.selected_ticker = watch_tickers[0] if watch_tickers else None

    current = normalize_ticker(st.session_state.get("selected_ticker"))
    in_watch = bool(current and current in watch_tickers)
    idx = watch_tickers.index(current) if in_watch else None

    def _select_ticker(ticker: str):
        st.session_state.selected_ticker = ticker
        if ticker in watch_tickers:
            st.session_state.watch_select = ticker
            st.session_state._last_watch_select = ticker
        try:
            st.query_params["ticker"] = ticker
        except Exception:
            pass

    nav_l, nav_m, nav_r = st.columns([1, 2.4, 1])
    with nav_l:
        prev_disabled = (not in_watch) or idx == 0
        if st.button("← 上一只", disabled=prev_disabled, use_container_width=True):
            _select_ticker(watch_tickers[idx - 1])
            st.rerun()
    with nav_m:
        title = current or "未选择股票"
        name = NAMES.get(current or "", current or "")
        st.markdown(f"<div style='text-align:center;font-size:1.4rem;font-weight:800'>{title} · {name}</div>", unsafe_allow_html=True)
        if not in_watch and current:
            st.caption("当前股票不在自选股序列，左右切换已停用。")
    with nav_r:
        next_disabled = (not in_watch) or idx == len(watch_tickers) - 1
        if st.button("下一只 →", disabled=next_disabled, use_container_width=True):
            _select_ticker(watch_tickers[idx + 1])
            st.rerun()

    pick_c, other_c, add_c = st.columns([1.1, 1.4, 1])
    with pick_c:
        if watch_tickers:
            last = st.session_state.get("_last_watch_select")
            if "watch_select" not in st.session_state:
                st.session_state.watch_select = current if in_watch else watch_tickers[0]
            chosen = st.selectbox("自选股", watch_tickers, key="watch_select")
            if last is None:
                st.session_state._last_watch_select = chosen
            elif chosen != last:
                st.session_state._last_watch_select = chosen
                _select_ticker(chosen)
                st.rerun()
        else:
            st.info("自选股为空，请在下方输入代码分析。")
    with other_c:
        with st.form("manual_ticker_form", clear_on_submit=False):
            typed = st.text_input("分析其他股票", placeholder="例如 AMD")
            analyze_btn = st.form_submit_button("分析", type="primary")
        if analyze_btn:
            parsed = normalize_ticker(typed)
            if not parsed:
                st.error("股票代码格式不正确。仅允许字母、数字、. 和 -。")
            else:
                _select_ticker(parsed)
                st.rerun()
    with add_c:
        if current and not in_watch:
            st.caption(f"{current} 不在你的自选股中")
            if st.button("+ 加入自选股", use_container_width=True):
                try:
                    add_watchlist(db, user_id, current)
                    st.success(f"已添加 {current}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(public_db_error("insert", "watchlist", e, client=db))

    use_latest = st.checkbox("使用最新交易日", value=True)
    chosen_date = st.date_input("历史日期", value=date.today(), disabled=use_latest)
    as_of = None if use_latest else chosen_date.isoformat()

    if not current:
        st.info("请选择或输入一只股票。")
        st.stop()

    cache_key = (current, as_of)
    if st.session_state.get("analysis_cache_key") != cache_key:
        with st.spinner(f"正在分析 {current}…"):
            r = analyze_one(current, as_of, db, user_id)
        st.session_state.last_analysis = r
        st.session_state.analysis_cache_key = cache_key
    r = st.session_state.get("last_analysis")

    if r:
        st.markdown(f"### {r['ticker']} · {r['name']} — {r['date']}")
        meta1, meta2, meta3 = st.columns(3)
        meta1.metric("估值类型", r.get("valuation_class_label") or "—")
        meta2.metric("置信度", r.get("confidence") or "—")
        meta3.write("")
        status_badge(r["recommendation"])
        st.write("")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("价格", money(r["price"]))
        c2.metric("综合公允价值", money(r["fair"]), pct(delta_pct(r["fair"], r["price"])) if r["fair"] else None)
        c3.metric("SMA50", money(r["sma50"]), pct(delta_pct(r["price"], r["sma50"])) if r["sma50"] else None)
        c4.metric("SMA200", money(r["sma200"]), pct(delta_pct(r["price"], r["sma200"])) if r["sma200"] else None)
        cap = blend_caption(r.get("blend"))
        if cap:
            st.caption(cap)

        if r["zones"]:
            z1, z2, z3 = st.columns(3)
            z1.info(f"**第一批区**\n\n{zone_text(r['zones']['first'])}")
            z2.success(f"**核心买入区**\n\n{zone_text(r['zones']['core'])}")
            z3.success(f"**深度价值区**\n\n{zone_text(r['zones']['deep'])}")
        elif (r.get("blend") or {}).get("specialized") or r.get("confidence") == "SPECIALIZED":
            st.info("需要专项估值模型。仅显示技术指标，不生成价值买入区。")
        else:
            st.info("有效估值模型不足，暂不生成买入区。")

        left, right = st.columns([1.2, 1])
        with left:
            tech_df = pd.DataFrame({
                "指标": ["当前价", "SMA30", "SMA50", "SMA200"],
                "价格": [r["price"], r["sma30"], r["sma50"], r["sma200"]],
                "当前价距离%": [0, delta_pct(r["price"], r["sma30"]), delta_pct(r["price"], r["sma50"]), delta_pct(r["price"], r["sma200"])],
            })
            st.dataframe(tech_df, use_container_width=True, hide_index=True,
                         column_config={"价格": st.column_config.NumberColumn(format="$%.2f"), "当前价距离%": st.column_config.NumberColumn(format="%.1f%%")})
            if r["vp"]:
                st.info(f"近一年成交密集区（估算）：**{money(r['vp']['low'])} – {money(r['vp']['high'])}**")
        with right:
            model_rows = []
            model_list = (r.get("blend") or {}).get("model_list") or []
            if not model_list:
                model_list = [obj for obj in (r.get("pe"), r.get("dcf"), r.get("growth")) if obj]
            for obj in model_list:
                usable = bool(obj) and obj.get("valid") and not obj.get("outlier") and obj.get("applicable") is not False
                model_rows.append({
                    "模型": obj.get("name") or obj.get("model_id"),
                    "低值": obj.get("low") if usable else None,
                    "中枢": obj.get("mid") if usable else None,
                    "高值": obj.get("high") if usable else None,
                    "状态": model_status_text(obj),
                    "置信度": obj.get("confidence") or "—",
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

        st.line_chart(r["history"].tail(260)[["Close", "SMA30", "SMA50", "SMA200"]], use_container_width=True)
        st.caption(r["note"])
        render_valuation_diagnostics(r)
        if use_latest and st.button("保存当前估值快照"):
            try:
                save_snapshot(db, user_id, r)
                st.success("已保存。")
            except Exception as e:
                st.error(public_db_error("upsert", "valuation_snapshots", e, client=db))

elif page == "历史快照":
    st.subheader("历史估值快照")
    try:
        watch = get_watchlist(db, user_id)
    except Exception as e:
        st.error(public_db_error("select", "watchlist", e, client=db))
        st.stop()
    tickers = [x["ticker"] for x in watch]
    if not tickers:
        st.info("请先添加自选股。")
        st.stop()
    ticker = st.selectbox("股票", tickers)
    try:
        data = list_snapshots(db, user_id, ticker)
    except Exception as e:
        st.error(public_db_error("select", "valuation_snapshots", e, client=db))
        st.stop()
    if not data:
        st.info("暂无历史快照。打开自选股页面并启用自动保存即可开始积累。")
    else:
        hdf = pd.DataFrame(data)
        st.dataframe(hdf, use_container_width=True, hide_index=True)
        chart = hdf.sort_values("snapshot_date").set_index("snapshot_date")[["price", "fair_value"]]
        chart.columns = ["股价", "公允价值"]
        st.line_chart(chart, use_container_width=True)

else:
    st.subheader("账户")
    st.write(f"邮箱：**{user_email}**")
    st.caption("密码由 Supabase Auth 管理，不保存在应用数据库中。")
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
            except Exception:
                logger.exception("password update failed")
                st.error("修改失败，请重新登录后再试。")

st.divider()
st.caption("研究工具，不构成个性化投资建议。自定义股票使用通用估值假设；重要持仓应进一步校准增长率、折现率与合理估值倍数。")
