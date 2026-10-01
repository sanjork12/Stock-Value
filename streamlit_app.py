from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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


def make_supabase() -> Client:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error("Supabase 尚未配置。请先按 README 设置 SUPABASE_URL 和 SUPABASE_ANON_KEY。")
        st.stop()
    return create_client(url, key)


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
    try:
        res = (
            sb.table("valuation_snapshots")
            .select("*")
            .eq("user_id", user_id)
            .eq("ticker", ticker)
            .lte("snapshot_date", as_of)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
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
    z = r.get("zones") or {}
    vp = r.get("vp") or {}
    payload = {
        "user_id": user_id,
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


def get_watchlist(sb: Client, user_id: str):
    res = (
        sb.table("watchlist")
        .select("id,ticker,nickname,created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


def add_watchlist(sb: Client, user_id: str, ticker: str, nickname: str = ""):
    ticker = ticker.upper().strip()
    # Validate symbol by fetching recent history.
    history_cached(ticker, None)
    sb.table("watchlist").upsert(
        {"user_id": user_id, "ticker": ticker, "nickname": nickname.strip() or None},
        on_conflict="user_id,ticker",
    ).execute()


def remove_watchlist(sb: Client, user_id: str, ticker: str):
    (
        sb.table("watchlist")
        .delete()
        .eq("user_id", user_id)
        .eq("ticker", ticker)
        .execute()
    )


# ---------------- Authentication ----------------

sb = make_supabase()
cookie_manager = stx.CookieManager(key="auth_cookie_manager")

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None

# Restore persistent login using the Supabase refresh token. Password is never stored.
if st.session_state.auth_user is None:
    saved_refresh = cookie_manager.get("stock_monitor_refresh")
    if saved_refresh:
        try:
            resp = sb.auth.refresh_session(saved_refresh)
            if resp and resp.session and resp.user:
                st.session_state.auth_user = resp.user
                st.session_state.access_token = resp.session.access_token
                st.session_state.refresh_token = resp.session.refresh_token
                cookie_manager.set(
                    "stock_monitor_refresh",
                    resp.session.refresh_token,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                    key="refresh_cookie_after_restore",
                )
        except Exception:
            try:
                cookie_manager.delete("stock_monitor_refresh", key="delete_bad_refresh_cookie")
            except Exception:
                pass


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
                    resp = sb.auth.sign_in_with_password({"email": email.strip(), "password": password})
                    st.session_state.auth_user = resp.user
                    st.session_state.access_token = resp.session.access_token
                    st.session_state.refresh_token = resp.session.refresh_token
                    if remember:
                        cookie_manager.set(
                            "stock_monitor_refresh",
                            resp.session.refresh_token,
                            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                            key="remember_login_cookie",
                        )
                    else:
                        try:
                            cookie_manager.delete("stock_monitor_refresh", key="clear_remember_cookie")
                        except Exception:
                            pass
                    st.rerun()
                except Exception as e:
                    st.error(f"登录失败：{e}")

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
                        resp = sb.auth.sign_up({"email": new_email.strip(), "password": new_password})
                        if resp.session:
                            st.success("注册成功并已登录。")
                            st.session_state.auth_user = resp.user
                            st.session_state.access_token = resp.session.access_token
                            st.session_state.refresh_token = resp.session.refresh_token
                            st.rerun()
                        else:
                            st.success("注册成功。请先到邮箱完成验证，然后回来登录。")
                    except Exception as e:
                        st.error(f"注册失败：{e}")

        st.caption("密码由 Supabase Auth 安全处理；本程序不会把明文密码写入数据库或 GitHub。")


if st.session_state.auth_user is None:
    login_page()
    st.stop()

user = st.session_state.auth_user
user_id = user.id
user_email = getattr(user, "email", "") or ""

# ---------------- Main app ----------------

st.title("📈 Stock Fair Value Monitor")
st.caption("自选股数据库 + 三模型公允价值 + SMA30/50/200 + 成交密集区 + 分层买入区")

with st.sidebar:
    st.markdown(f"**已登录**  \n{user_email}")
    if st.button("退出登录", use_container_width=True):
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        try:
            cookie_manager.delete("stock_monitor_refresh", key="logout_delete_cookie")
        except Exception:
            pass
        st.session_state.auth_user = None
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.rerun()

    st.divider()
    page = st.radio("页面", ["自选股", "单股分析", "历史快照", "账户"], index=0)


if page == "自选股":
    st.subheader("我的自选股")
    with st.expander("➕ 添加股票", expanded=False):
        c1, c2, c3 = st.columns([1, 1.4, 0.7])
        new_ticker = c1.text_input("股票代码", placeholder="例如 AMZN / AMD / PLTR").upper().strip()
        nickname = c2.text_input("备注（可选）", placeholder="例如：长期观察")
        add_btn = c3.button("添加", type="primary", use_container_width=True)
        if add_btn and new_ticker:
            try:
                add_watchlist(sb, user_id, new_ticker, nickname)
                st.success(f"已添加 {new_ticker}")
                st.rerun()
            except Exception as e:
                st.error(f"无法添加 {new_ticker}：{e}")

    watch = get_watchlist(sb, user_id)
    if not watch:
        st.info("你的自选股还是空的。可以先添加 AMZN、NVDA、MSFT 等代码。")
        st.stop()

    auto_save = st.checkbox("自动保存今天的估值快照", value=True)
    rows = []
    progress = st.progress(0, text="正在更新自选股…")
    for i, item in enumerate(watch, start=1):
        t = item["ticker"]
        try:
            r = analyze_one(t, None, sb, user_id)
            if auto_save:
                save_snapshot(sb, user_id, r)
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
            rows.append({"股票": t, "备注": item.get("nickname") or "", "状态": "数据不足", "错误": str(e)})
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
            remove_watchlist(sb, user_id, to_remove)
            st.success(f"已删除 {to_remove}")
            st.rerun()

elif page == "单股分析":
    st.subheader("单股分析")
    watch = get_watchlist(sb, user_id)
    default_options = [x["ticker"] for x in watch] or sorted(MAG7)
    c1, c2 = st.columns([1, 1])
    ticker = c1.text_input("股票代码", value=default_options[0] if default_options else "AMZN").upper().strip()
    use_latest = c2.checkbox("使用最新交易日", value=True)
    chosen_date = st.date_input("历史日期", value=date.today(), disabled=use_latest)
    if st.button("开始分析", type="primary"):
        as_of = None if use_latest else chosen_date.isoformat()
        with st.spinner(f"正在分析 {ticker}…"):
            r = analyze_one(ticker, as_of, sb, user_id)
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
            save_snapshot(sb, user_id, r)
            st.success("已保存。")

elif page == "历史快照":
    st.subheader("历史估值快照")
    watch = get_watchlist(sb, user_id)
    tickers = [x["ticker"] for x in watch]
    if not tickers:
        st.info("请先添加自选股。")
        st.stop()
    ticker = st.selectbox("股票", tickers)
    res = (
        sb.table("valuation_snapshots")
        .select("snapshot_date,price,fair_value,sma30,sma50,sma200,first_low,first_high,core_low,core_high,deep_low,deep_high,status")
        .eq("user_id", user_id)
        .eq("ticker", ticker)
        .order("snapshot_date", desc=True)
        .execute()
    )
    data = res.data or []
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
                sb.auth.update_user({"password": p1})
                st.success("密码已更新。")
            except Exception as e:
                st.error(f"修改失败：{e}")

st.divider()
st.caption("研究工具，不构成个性化投资建议。自定义股票使用通用估值假设；重要持仓应进一步校准增长率、折现率与合理估值倍数。")
