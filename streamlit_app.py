from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import os
import pandas as pd
import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client, Client

from mag7_monitor import (
    MAG7,
    add_indicators,
    get_history,
    volume_profile_zone,
    get_live_fundamentals,
    pe_model,
    dcf_model,
    growth_model,
    blended_fair,
    buy_zones,
    classify_price,
    fnum,
)

st.set_page_config(page_title="Stock Fair Value Monitor", page_icon="📈", layout="wide")

logger = logging.getLogger("stock_fair_value_monitor")
REMEMBER_COOKIE = "stock_monitor_refresh"
REMEMBER_DAYS = 30

NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "NVDA": "Nvidia",
    "META": "Meta",
    "TSLA": "Tesla",
}

STATUS_META = {
    "深度价值区": ("#DCFCE7", "#166534", "🟢"),
    "核心买入区": ("#D1FAE5", "#047857", "🟢"),
    "第一批区": ("#FEF3C7", "#92400E", "🟡"),
    "接近第一批区": ("#E0F2FE", "#075985", "🔵"),
    "观察 / 等回调": ("#F3F4F6", "#4B5563", "⚪"),
    "仅技术观察": ("#F3F4F6", "#4B5563", "⚪"),
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


def recommendation_label(r):
    z = r.get("zones")
    p = r.get("price")
    if not z or p is None:
        return "仅技术观察"
    if p <= z["deep"][1]:
        return "深度价值区"
    if p <= z["core"][1]:
        return "核心买入区"
    if p <= z["first"][1]:
        return "第一批区"
    if p <= z["first"][1] * 1.05:
        return "接近第一批区"
    return "观察 / 等回调"


def status_badge(label: str):
    bg, fg, icon = STATUS_META.get(label, ("#F3F4F6", "#4B5563", "⚪"))
    st.markdown(
        f'<span style="background:{bg};color:{fg};padding:0.35rem 0.7rem;border-radius:999px;font-weight:700">{icon} {label}</span>',
        unsafe_allow_html=True,
    )


def style_status(v):
    bg, fg, _ = STATUS_META.get(str(v), ("#FFFFFF", "#111827", ""))
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
    ticker = ticker.upper().strip()
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

    if historical:
        snap = get_cloud_snapshot(sb, user_id, ticker, as_of) if sb and user_id else None
        if snap:
            pe = snap.get("pe_model")
            dcf = snap.get("dcf_model")
            growth = snap.get("growth_model")
            fair = snap.get("fair_value")
            note = f"历史估值使用 {snap['snapshot_date']} 保存的云端估值快照。"
        else:
            note = "该日期之前没有云端估值快照，因此只显示当时技术面，避免用今天的盈利预期倒推过去。"
    else:
        f = fundamentals_cached(ticker)
        pe = pe_model(ticker, f.get("forward_eps"))
        dcf = dcf_model(ticker, f.get("fcf"), f.get("shares"), f.get("cash"), f.get("debt"))
        growth = growth_model(ticker, f.get("forward_eps"), f.get("earnings_growth"))
        fair = blended_fair(pe, dcf, growth)
        if ticker in MAG7:
            note = "最新估值使用七巨头专用假设 + 当前公开基本面数据。"
        else:
            note = "自定义股票使用通用估值假设；建议后续为重要持仓配置专属估值参数。"

    zones = buy_zones(fair, vp["mid"] if vp else None, sma200) if fair else None

    r = {
        "ticker": ticker,
        "name": NAMES.get(ticker, ticker),
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
        "raw": {"note": r.get("note")},
    }
    sb.table("valuation_snapshots").upsert(
        payload, on_conflict="user_id,ticker,snapshot_date"
    ).execute()


def list_snapshots(sb: Client, user_id: str, ticker: str):
    current_user_id = assert_live_session(sb, user_id)
    res = (
        sb.table("valuation_snapshots")
        .select(
            "snapshot_date,price,fair_value,sma30,sma50,sma200,first_low,first_high,core_low,core_high,deep_low,deep_high,status"
        )
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
    ticker = ticker.upper().strip()
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

st.title("📈 Stock Fair Value Monitor")
st.caption("自选股数据库 + 三模型公允价值 + SMA30/50/200 + 成交密集区 + 分层买入区")

with st.sidebar:
    st.markdown(f"**已登录**  \n{user_email}")
    if st.button("退出登录", use_container_width=True):
        try:
            db.auth.sign_out()
        except Exception:
            pass
        _delete_remember_cookie(cookie_manager, "logout_delete_cookie")
        clear_auth_session()
        st.rerun()

    st.divider()
    page = st.radio("页面", ["自选股", "单股分析", "历史快照", "账户"], index=0)


if page == "自选股":
    st.subheader("我的自选股")
    with st.expander("➕ 添加股票", expanded=False):
        with st.form("add_watchlist_form", clear_on_submit=False):
            c1, c2, c3 = st.columns([1, 1.4, 0.7])
            new_ticker = c1.text_input("股票代码", placeholder="例如 AMZN / AMD / PLTR").upper().strip()
            nickname = c2.text_input("备注（可选）", placeholder="例如：长期观察")
            c3.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
            add_btn = c3.form_submit_button("添加", type="primary", use_container_width=True)
        if add_btn:
            if not new_ticker:
                st.error("请输入股票代码。")
            else:
                try:
                    add_watchlist(db, user_id, new_ticker, nickname)
                    st.success(f"已添加 {new_ticker}")
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
                "公允价值": r["fair"],
                "距公允价值%": delta_pct(r["price"], r["fair"]),
                "第一批区": zone_text(r["zones"]["first"]) if r["zones"] else "—",
                "核心买入区": zone_text(r["zones"]["core"]) if r["zones"] else "—",
                "深度价值区": zone_text(r["zones"]["deep"]) if r["zones"] else "—",
                "状态": r["recommendation"],
            })
        except Exception as e:
            err_text = (
                public_db_error("upsert", "valuation_snapshots", e, client=db)
                if is_rls_or_auth_error(e)
                else "数据不足"
            )
            rows.append({"股票": t, "备注": item.get("nickname") or "", "状态": "数据不足", "错误": err_text})
        progress.progress(i / len(watch), text=f"正在更新 {i}/{len(watch)}")
    progress.empty()

    df = pd.DataFrame(rows)
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
    cols = st.columns(5)
    for col, label in zip(cols, ["深度价值区", "核心买入区", "第一批区", "接近第一批区", "观察 / 等回调"]):
        with col:
            status_badge(label)

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
    default_options = [x["ticker"] for x in watch] or sorted(MAG7)
    c1, c2 = st.columns([1, 1])
    ticker = c1.text_input("股票代码", value=default_options[0] if default_options else "AMZN").upper().strip()
    use_latest = c2.checkbox("使用最新交易日", value=True)
    chosen_date = st.date_input("历史日期", value=date.today(), disabled=use_latest)
    if st.button("开始分析", type="primary"):
        as_of = None if use_latest else chosen_date.isoformat()
        with st.spinner(f"正在分析 {ticker}…"):
            r = analyze_one(ticker, as_of, db, user_id)
        st.session_state.last_analysis = r

    r = st.session_state.get("last_analysis")
    if r:
        st.markdown(f"### {r['ticker']} · {r['name']} — {r['date']}")
        status_badge(r["recommendation"])
        st.write("")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("价格", money(r["price"]))
        c2.metric("综合公允价值", money(r["fair"]), pct(delta_pct(r["fair"], r["price"])) if r["fair"] else None)
        c3.metric("SMA50", money(r["sma50"]), pct(delta_pct(r["price"], r["sma50"])) if r["sma50"] else None)
        c4.metric("SMA200", money(r["sma200"]), pct(delta_pct(r["price"], r["sma200"])) if r["sma200"] else None)

        if r["zones"]:
            z1, z2, z3 = st.columns(3)
            z1.info(f"**第一批区**\n\n{zone_text(r['zones']['first'])}")
            z2.success(f"**核心买入区**\n\n{zone_text(r['zones']['core'])}")
            z3.success(f"**深度价值区**\n\n{zone_text(r['zones']['deep'])}")

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
            for label, obj in [("P/E", r["pe"]), ("DCF", r["dcf"]), ("Growth / PEG", r["growth"])]:
                model_rows.append({"模型": label, "低值": obj.get("low") if obj else None, "中枢": obj.get("mid") if obj else None, "高值": obj.get("high") if obj else None})
            st.dataframe(pd.DataFrame(model_rows), use_container_width=True, hide_index=True,
                         column_config={"低值": st.column_config.NumberColumn(format="$%.2f"), "中枢": st.column_config.NumberColumn(format="$%.2f"), "高值": st.column_config.NumberColumn(format="$%.2f")})

        st.line_chart(r["history"].tail(260)[["Close", "SMA30", "SMA50", "SMA200"]], use_container_width=True)
        st.caption(r["note"])
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
