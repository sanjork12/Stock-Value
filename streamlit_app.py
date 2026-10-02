from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import os
import traceback

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Stock Fair Value Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
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
    st.error(f"App boot import failed: {type(_boot_exc).__name__}: {_boot_exc}")
    st.code(traceback.format_exc())
    st.stop()

logger = logging.getLogger("stock_fair_value_monitor")

NAV_PAGES = ["自选股", "单股分析", "历史快照", "账户"]
REMEMBER_COOKIE = "stock_monitor_refresh"
REMEMBER_DAYS = 30


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


def render_model_explanations(r: dict):
    blend = r.get("blend") or {}
    model_list = blend.get("model_list") or list((blend.get("models") or {}).values())
    if not model_list:
        return
    st.markdown("#### 为什么得到这个估值？")
    for obj in model_list:
        name = obj.get("name") or MODEL_DISPLAY_NAMES.get(obj.get("model_id"), obj.get("model_id"))
        applicable = obj.get("applicable") is not False
        usable = applicable and obj.get("valid") and not obj.get("outlier")
        with st.expander(f"{name} — {'纳入' if usable else '排除'}", expanded=False):
            executed = obj.get("executed")
            st.write(f"**executed:** {executed}")
            if obj.get("outlier"):
                st.write("**status:** executed but excluded as outlier")
            elif not applicable:
                st.write("**status:** not applicable / not executed")
            elif obj.get("valid") is False:
                st.write("**status:** executed but invalid")
            else:
                st.write("**status:** included")
            st.write(f"**reason:** {obj.get('applicability_reason') or obj.get('reason') or '—'}")
            st.write(f"**applicability:** {obj.get('why_applicable') or '—'}")
            if usable:
                inputs = obj.get("inputs") or {}
                if inputs:
                    st.write("**Key inputs:**")
                    for key, value in list(inputs.items())[:8]:
                        st.write(f"- {key}: {value}")
                st.write(
                    f"**Result:** {money(obj.get('low'))} / {money(obj.get('mid'))} / {money(obj.get('high'))}"
                )
                st.write(f"**Confidence:** {str(obj.get('confidence') or '—').upper()}")
            elif obj.get("outlier"):
                st.write("该模型已执行，但相对其他模型偏离过大，未纳入综合估值。")
            elif executed is False:
                st.caption("未执行计算：适用性检查未通过。")


def render_cycle_panel(r: dict):
    cycle = (r.get("blend") or {}).get("cycle") or r.get("cycle")
    if not cycle:
        return
    st.markdown("#### Cycle normalization")
    st.caption(cycle.get("note") or "周期估值使用中周期盈利，而非当前周期峰值/谷值。")
    rows = [
        ("Current EPS", cycle.get("current_eps")),
        ("Forward EPS", cycle.get("forward_eps")),
        ("Normalized EPS", cycle.get("cycle_normalized_eps")),
        ("Historical EPS median", cycle.get("historical_eps_median")),
        ("Current operating margin", cycle.get("current_operating_margin")),
        ("Normalized operating margin", cycle.get("normalized_operating_margin")),
        ("Normalized FCF", cycle.get("normalized_fcf")),
    ]
    st.dataframe(
        pd.DataFrame({"指标": [a for a, _ in rows], "值": [b for _, b in rows]}),
        hide_index=True,
        use_container_width=True,
    )
    pe_range = cycle.get("cycle_pe_range")
    if pe_range:
        st.caption(f"Cycle PE range: {pe_range[0]} – {pe_range[1]}")


def render_valuation_diagnostics(r: dict):
    f = r.get("financials") or {}
    blend = r.get("blend") or {}
    profile = blend.get("profile") or {}
    st.caption(
        f"Price: {r.get('price_timestamp') or r.get('date') or '—'} (daily bar)　"
        f"Financials: {f.get('fcf_period') or r.get('financials_period') or '—'}　"
        f"Valuation run: {r.get('valuation_run_at') or '—'}　"
        f"Snapshot: {r.get('snapshot_date') or '— (live, not a stored snapshot)'}　"
        f"Model: {r.get('model_version') or '—'}"
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
        if f.get("eps_proxy") and fnum(f.get("forward_eps")) is None:
            lines.append("**Forward EPS unavailable**")
            source = f.get("eps_proxy_source") or ""
            if source in {"statement_trailing_eps", "statement_derived", "ni_over_diluted_shares", "income_statement_diluted_eps"}:
                lines.append("**Using statement-derived trailing EPS proxy**")
            else:
                lines.append("**Using trailing EPS proxy**")
        prov = f.get("provenance") or {}
        shares_p = prov.get("shares") or {}
        lines.append("**Quote currency**: " + str(prov.get("quote_currency") or f.get("quote_currency") or "—"))
        lines.append("**Financial currency**: " + str(prov.get("financial_currency") or f.get("financial_currency") or "—"))
        fwd = prov.get("forward_eps") or {}
        lines.append(f"**Forward EPS**: {fwd.get('value')}  source={fwd.get('source') or f.get('forward_eps_source') or '—'}")
        tr = prov.get("trailing_eps") or {}
        lines.append(f"**Trailing EPS**: {tr.get('value')}  source={tr.get('source') or f.get('trailing_eps_source') or '—'}")
        st_eps = prov.get("statement_eps") or {}
        lines.append(f"**Statement EPS**: {st_eps.get('value')}  currency={st_eps.get('currency') or f.get('statement_eps_currency') or '—'}")
        px = prov.get("eps_proxy") or {}
        safe = px.get("currency_safe")
        if safe is None:
            safe = f.get("eps_proxy_currency_safe")
        lines.append(
            f"**EPS proxy**: {px.get('value') if px else f.get('eps_proxy')}  "
            f"source={px.get('source') or f.get('eps_proxy_source') or '—'}  "
            f"currency-safe: {'yes' if safe else 'no'}"
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
    zones = r.get("zones") or {}
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
    with st.expander("Exit / Overvaluation diagnostics"):
        st.caption(
            "退出区仅在估值模型一致性与可靠性达到要求时提供精确价格。"
            "模型分歧较大时，仅显示定性高估提示。"
        )
        if conf in {"SPECIALIZED", "UNAVAILABLE"} or mode == "unavailable":
            st.write("SPECIALIZED / UNAVAILABLE：不生成精确退出区。")
            return
        disp = r.get("dispersion_pct")
        disp_txt = f"{disp*100:.0f}%" if disp is not None else "—"
        lines = [
            f"**Valuation confidence**: {conf or '—'}",
            f"**Valuation reliability score**: {r.get('reliability_score') if r.get('reliability_score') is not None else '—'}",
            f"**Model dispersion**: {disp_txt}",
            f"**Exit confidence**: {(exit_zone or {}).get('exit_confidence') or r.get('exit_confidence') or '—'}",
            f"**Display mode**: {mode or '—'}",
            f"**Eligible for precise exit**: {'Yes' if (exit_zone or {}).get('eligible_for_precise_exit') else 'No'}",
            f"**Reason codes**: {', '.join((exit_zone or {}).get('reason_codes') or r.get('exit_reason_codes') or []) or '—'}",
        ]
        if isinstance(rel, dict):
            lines.append(f"**Exit reliability score**: {rel.get('exit_reliability_score')}")
            lines.append(f"**Exit dispersion**: {rel.get('exit_dispersion_pct')}")
        if conf == "LOW" or mode == "qualitative" or not isinstance(exit_zone, dict):
            lines.append("")
            lines.append("精确减仓价格已关闭（qualitative / low reliability）。")
            st.markdown("\n".join(lines))
            return
        lines.extend([
            "",
            f"**Volatility**: {exit_zone.get('volatility_1y')} ({exit_zone.get('volatility_band') or '—'})",
            f"**Cyclicality adjustment**: {exit_zone.get('cyclical_adj', 0):+.0%}" if exit_zone.get("cyclical_adj") is not None else "**Cyclicality adjustment**: —",
            f"**Dispersion adjustment**: {exit_zone.get('dispersion_adj', 0):+.0%}" if exit_zone.get("dispersion_adj") is not None else "**Dispersion adjustment**: —",
            f"**Class adjustment**: {exit_zone.get('class_adj', 0):+.0%}" if exit_zone.get("class_adj") is not None else "**Class adjustment**: —",
            f"**Adjustments**: {', '.join(exit_zone.get('adjustments') or []) or '—'}",
            "",
            f"**Hold upper**: {exit_zone.get('hold_upper_pct', 0):.0%}",
            f"**Overvalued threshold**: {exit_zone.get('overvalued_pct', 0):.0%}",
            f"**Trim threshold**: {exit_zone.get('trim_pct', 0):.0%}",
            f"**Extreme threshold**: {exit_zone.get('extreme_pct', 0):.0%}",
            "",
            f"**Hold upper price**: {money(exit_zone.get('hold_upper_price'))}",
            f"**Overvalued price**: {money(exit_zone.get('overvalued_price'))}",
            f"**Trim reference price**: {money(exit_zone.get('trim_price'))}",
            f"**Extreme overvaluation price**: {money(exit_zone.get('extreme_price'))}",
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

    return analyze_ticker(
        ticker,
        as_of,
        history_loader=history_cached,
        fundamentals_loader=fundamentals_cached,
        snapshot_loader=snapshot_loader,
    )


def save_snapshot(sb: Client, user_id: str, r: dict):
    current_user_id = assert_live_session(sb, user_id)
    payload = build_snapshot_record(current_user_id, r)
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
    st.title("📈 Stock Fair Value Monitor")
    st.caption("股票估值、均线、买入区与长期跟踪")

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

# Apply page jumps before the nav widget is instantiated (cannot mutate widget keys after).
_pending_nav = st.session_state.pop("_pending_nav_page", None)
if _pending_nav in NAV_PAGES:
    st.session_state.nav_page = _pending_nav

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
    show_advanced_cols = st.checkbox("显示高级列", value=False, key="dash_advanced_cols")
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
                    "公允价值": "—",
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
                "公允价值": dashboard_fair_text(r),
                "置信度": r.get("confidence") or "—",
                "距公允价值%": delta_display,
                "第一批区": zone_text(r["zones"]["first"]) if r["zones"] else "—",
                "核心买入区": zone_text(r["zones"]["core"]) if r["zones"] else "—",
                "深度价值区": zone_text(r["zones"]["deep"]) if r["zones"] else "—",
                "减仓参考区": trim_txt,
                "明显高估区": extreme_txt,
                "可靠性": r.get("reliability_score") if r.get("reliability_score") is not None else "—",
                "模型分歧": f"{r['dispersion_pct']*100:.0f}%" if r.get("dispersion_pct") is not None else "—",
                "SMA30": r["sma30"],
                "SMA50": r["sma50"],
                "SMA200": r["sma200"],
                "备注": item.get("nickname") or "",
                "估值类型": r.get("valuation_class_label") or "—",
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
                "公允价值": "—",
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
    dashboard_columns = [
        "股票",
        "价格",
        "状态",
        "错误",
        "公允价值",
        "置信度",
        "距公允价值%",
        "第一批区",
        "核心买入区",
        "深度价值区",
        "减仓参考区",
        "明显高估区",
        "可靠性",
        "模型分歧",
        "SMA30",
        "SMA50",
        "SMA200",
    ]
    if show_advanced_cols:
        dashboard_columns.extend(["备注", "估值类型"])
    visible = [col for col in dashboard_columns if col in df.columns]
    if "错误" in visible and "错误" in df.columns:
        err_series = df["错误"]
        if err_series.isna().all() or err_series.fillna("").astype(str).str.strip().eq("").all():
            visible = [col for col in visible if col != "错误"]
    df = df.loc[:, visible]
    styled = df.style.map(style_status, subset=["状态"] if "状态" in df.columns else [])
    st.dataframe(
        styled,
        use_container_width=False,
        hide_index=True,
        column_config={
            "股票": st.column_config.TextColumn(width=75),
            "价格": st.column_config.NumberColumn(format="$%.2f", width=90),
            "状态": st.column_config.TextColumn(width=180),
            "公允价值": st.column_config.TextColumn(width=120),
            "置信度": st.column_config.TextColumn(width=90),
            "距公允价值%": st.column_config.TextColumn(width=105),
            "第一批区": st.column_config.TextColumn(width=150),
            "核心买入区": st.column_config.TextColumn(width=150),
            "深度价值区": st.column_config.TextColumn(width=150),
            "减仓参考区": st.column_config.TextColumn(width=140),
            "明显高估区": st.column_config.TextColumn(width=110),
            "可靠性": st.column_config.TextColumn(width=80),
            "模型分歧": st.column_config.TextColumn(width=90),
            "SMA30": st.column_config.NumberColumn(format="$%.2f", width=90),
            "SMA50": st.column_config.NumberColumn(format="$%.2f", width=90),
            "SMA200": st.column_config.NumberColumn(format="$%.2f", width=90),
            "备注": st.column_config.TextColumn(width=120),
            "估值类型": st.column_config.TextColumn(width=120),
            "错误": st.column_config.TextColumn(width=180),
        },
    )
    st.caption(
        "可靠性评分衡量数据完整性、模型一致性及适用性，不是股票评级，也不代表未来收益概率。"
        "退出区仅在估值模型一致性与可靠性达到要求时提供精确价格；模型分歧较大时，仅显示定性高估提示。"
    )

    st.markdown("#### 颜色说明")
    cols = st.columns(8)
    for col, label in zip(
        cols,
        ["低于深度价值区", "深度价值区", "核心买入区", "第一批区", "合理持有区", "偏高估区", "减仓参考区", "明显高估区"],
    ):
        with col:
            status_badge(label)

    jump = st.selectbox("在单股分析中打开", [x["ticker"] for x in watch], key="dashboard_jump_ticker")
    if st.button("打开单股分析", type="primary"):
        st.session_state.selected_ticker = jump
        st.session_state._last_watch_select = jump
        st.session_state._pending_watch_select = jump
        st.session_state._pending_nav_page = "单股分析"
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
            try:
                r = analyze_one(current, as_of, db, user_id)
            except Exception as e:
                st.error(public_analysis_error(current, e))
                st.stop()
        st.session_state.last_analysis = r
        st.session_state.analysis_cache_key = cache_key
    r = st.session_state.get("last_analysis")

    if r:
        if r.get("snapshot_error"):
            st.error(r["snapshot_error"])
        elif r.get("analysis_error") and r.get("price") is None:
            st.error(r["analysis_error"])
        elif r.get("errors"):
            st.warning("部分数据源失败，已保留可用的价格/估值结果。")
        st.markdown(f"### {r['ticker']} · {r['name']} — {r.get('date') or '—'}")
        if (r.get("blend") or {}).get("legacy"):
            st.info("该历史快照创建于可靠性层之前，部分可靠性指标不可用。")
        meta1, meta2, meta3 = st.columns(3)
        meta1.metric("估值类型", r.get("valuation_class_label") or "—")
        meta2.metric("置信度", r.get("confidence") or "—")
        score = r.get("reliability_score")
        meta3.metric("可靠性评分", f"{score} / 100" if score is not None else "—")
        status_badge(r["recommendation"])
        st.write("")
        rel = (r.get("blend") or {}).get("reliability") or {}
        disp = r.get("dispersion_pct")
        inc = rel.get("model_count_included")
        total = rel.get("model_count_total")
        conf = str(r.get("confidence") or "").upper()
        view = (r.get("blend") or {}).get("view") or primary_valuation_view(r.get("blend") or {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("价格", money(r["price"]))
        if view.get("mode") == "specialized":
            c2.metric("公允价值", "不适用")
            st.info("传统估值模型不适用，需要专项场景估值。仅显示技术观察。")
        elif view.get("mode") == "unavailable":
            c2.metric("公允价值", "数据不足")
        elif view.get("mode") == "indicative_range":
            c2.metric(
                "Indicative Valuation Range",
                f"{money_conf(view.get('low'), 'LOW')} – {money_conf(view.get('high'), 'LOW')}",
            )
            st.caption(
                f"Reference midpoint: {money_conf(view.get('mid'), 'LOW')}  ·  Confidence: LOW"
            )
            st.caption("估值不确定性较高，区间是主信息，中枢仅供参考。不得把中枢当作精确公允价值。")
        elif view.get("mode") == "point":
            c2.metric("Fair Value", money_conf(view.get("mid"), "HIGH"))
            st.caption(f"Range: {money(view.get('low'))} – {money(view.get('high'))}")
        else:
            c2.metric("Fair Value Estimate", money_conf(view.get("mid"), conf))
            st.caption(f"Reasonable Range: {money(view.get('low'))} – {money(view.get('high'))}")
        c3.metric("SMA50", money(r["sma50"]), pct(delta_pct(r["price"], r["sma50"])) if r["sma50"] else None)
        c4.metric("SMA200", money(r["sma200"]), pct(delta_pct(r["price"], r["sma200"])) if r["sma200"] else None)
        r1, r2, r3 = st.columns(3)
        r1.metric("模型分歧", f"{disp*100:.0f}%" if disp is not None else "—")
        r2.metric("有效模型", f"{inc} / {total}" if inc is not None and total is not None else "—")
        r3.metric("数据质量", rel.get("data_quality") or "—")
        cap = blend_caption(r.get("blend"))
        if cap:
            st.caption(cap)

        if r["zones"]:
            labels = (r["zones"] or {}).get("labels") or {}
            z1, z2, z3 = st.columns(3)
            z1.info(f"**{labels.get('first', '第一批区')}**\n\n{zone_text(r['zones']['first'])}")
            z2.success(f"**{labels.get('core', '核心买入区')}**\n\n{zone_text(r['zones']['core'])}")
            z3.success(f"**{labels.get('deep', '深度价值区')}**\n\n{zone_text(r['zones']['deep'])}")
            if conf == "LOW":
                st.warning("估值不确定性较高，此价格区仅为模型参考。")
            exit_zone = r.get("exit_zone") or ((r.get("blend") or {}).get("exit_zone"))
            mode = (exit_zone or {}).get("display_mode") if isinstance(exit_zone, dict) else None
            if conf in {"HIGH", "MEDIUM"} and isinstance(exit_zone, dict) and mode == "precise":
                e1, e2, e3, e4 = st.columns(4)
                e1.info(
                    f"**合理持有区**\n\n≤ {money(exit_zone.get('hold_upper_price'))}"
                )
                e2.warning(
                    f"**偏高估区**\n\n{money(exit_zone.get('hold_upper_price'))} – {money(exit_zone.get('trim_price'))}"
                )
                e3.warning(
                    f"**减仓参考区**\n\n{format_trim_zone(exit_zone)}"
                )
                e4.error(
                    f"**明显高估区**\n\n{format_extreme_zone(exit_zone)}"
                )
                st.caption("减仓参考区基于当前估值模型与安全边际，不代表个性化投资建议。")
                render_valuation_band(r)
            elif conf in {"HIGH", "MEDIUM"} and mode == "qualitative":
                disp = r.get("dispersion_pct")
                disp_txt = f"{disp*100:.0f}%" if disp is not None else "—"
                st.warning("**Exit valuation: 低确定性**")
                st.write(f"**Reason:** 模型分歧 {disp_txt}")
                st.write(f"**Current interpretation:** {r.get('recommendation')}")
                st.caption("由于估值模型分歧较大，不提供精确减仓价格。")
            elif conf == "LOW":
                st.caption("低置信度不生成精确减仓价；若价格明显高于 indicative range，状态显示「估值偏高（低置信度）」。")
        elif (r.get("blend") or {}).get("specialized") or r.get("confidence") == "SPECIALIZED":
            st.info("传统估值模型不适用，需要专项场景估值。仅显示技术指标，不生成价值买入区。")
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
        render_cycle_panel(r)
        render_model_explanations(r)
        render_valuation_diagnostics(r)
        render_exit_diagnostics(r)
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
        st.caption("以下数值来自当时保存的 snapshot，不会用今天的估值重新计算。")
        if any(is_legacy_snapshot(row) or not row.get("model_version") or row.get("model_version") == "legacy" for row in data):
            st.info("该历史快照创建于可靠性层之前，部分可靠性指标不可用。")
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
            except Exception as exc:
                logger.warning("password update failed error_type=%s", type(exc).__name__)
                st.error("修改失败，请重新登录后再试。")

st.divider()
st.caption("研究工具，不构成个性化投资建议。自定义股票使用通用估值假设；重要持仓应进一步校准增长率、折现率与合理估值倍数。")
