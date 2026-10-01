from __future__ import annotations

from datetime import date, datetime, timezone
import logging

import pandas as pd

from mag7_monitor import (
    add_indicators,
    annualized_volatility,
    classify_price,
    fnum,
    get_history,
    get_live_fundamentals,
    volume_profile_zone,
)
from valuation_engine import (
    MODEL_VERSION,
    can_emit_buy_zones,
    check_valuation_invariants,
    dynamic_buy_zones,
    is_legacy_snapshot,
    normalize_ticker,
    reconstruct_blend_from_snapshot,
    valuate,
)

logger = logging.getLogger("stock_fair_value_monitor")
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
}


def _mid(result: dict | None):
    result = result or {}
    if result.get("blended_mid") is not None:
        return result.get("blended_mid")
    if result.get("fair") is not None:
        return result.get("fair")
    return result.get("fair_value")


def format_fair_value(result: dict) -> str:
    """Dashboard and single-stock both use this formatter."""
    conf = str(result.get("confidence") or result.get("overall_confidence") or "").upper()
    mid = _mid(result)
    low = result.get("blended_low") if result.get("blended_low") is not None else result.get("fair_low")
    high = result.get("blended_high") if result.get("blended_high") is not None else result.get("fair_high")
    if conf == "SPECIALIZED" or (mid is None and conf == "UNAVAILABLE"):
        return "—"
    if conf == "LOW" and low is not None and high is not None:
        return f"${float(low):,.0f} – ${float(high):,.0f}"
    if mid is None:
        return "—"
    if conf == "LOW":
        return f"${float(mid):,.0f}"
    return f"${float(mid):,.2f}"


def analyze_ticker(
    ticker: str,
    as_of: str | None = None,
    *,
    history_loader=None,
    fundamentals_loader=None,
    snapshot_loader=None,
) -> dict:
    ticker = normalize_ticker(ticker) or str(ticker).upper().strip()
    history_loader = history_loader or (lambda t, d: add_indicators(get_history(t, d)))
    fundamentals_loader = fundamentals_loader or get_live_fundamentals
    errors = []
    df = None
    financials = None
    blend = None
    snap = None
    snap_zones = None
    snapshot_date = None
    historical = bool(as_of and pd.Timestamp(as_of).date() < date.today())
    valuation_run_at = None if historical else datetime.now(timezone.utc).isoformat()

    try:
        df = history_loader(ticker, as_of)
    except Exception as exc:
        logger.warning(
            "analysis failed ticker=%s stage=history error_type=%s message=%s",
            ticker,
            type(exc).__name__,
            str(exc)[:200],
        )
        errors.append({"stage": "history", "error_type": type(exc).__name__, "message": str(exc)[:200]})
        return {
            "ticker": ticker,
            "name": NAMES.get(ticker, ticker),
            "price": None,
            "sma30": None,
            "sma50": None,
            "sma200": None,
            "fair": None,
            "fair_value": None,
            "blended_mid": None,
            "blended_low": None,
            "blended_high": None,
            "confidence": None,
            "valuation_class": None,
            "valuation_class_label": None,
            "reliability_score": None,
            "zones": None,
            "blend": None,
            "financials": None,
            "history": None,
            "note": "行情数据暂时获取失败",
            "analysis_error": "行情数据暂时获取失败",
            "errors": errors,
            "recommendation": "数据不足",
        }

    row = df.iloc[-1]
    price = float(row["Close"])
    trade_date = pd.Timestamp(df.index[-1]).date().isoformat()
    sma30 = fnum(row.get("SMA30"))
    sma50 = fnum(row.get("SMA50"))
    sma200 = fnum(row.get("SMA200"))
    vp = volume_profile_zone(df)
    pe = dcf = growth = None
    fair = None
    note = ""

    if historical:
        try:
            snap = snapshot_loader(ticker, as_of) if snapshot_loader else None
        except Exception as exc:
            logger.warning(
                "analysis failed ticker=%s stage=snapshot error_type=%s message=%s",
                ticker,
                type(exc).__name__,
                str(exc)[:200],
            )
            errors.append({"stage": "snapshot", "error_type": type(exc).__name__, "message": str(exc)[:200]})
            snap = None
        if snap:
            blend = reconstruct_blend_from_snapshot(snap)
            pe = snap.get("pe_model")
            dcf = snap.get("dcf_model")
            growth = snap.get("growth_model")
            fair = _mid(blend)
            conf = str((blend or {}).get("confidence") or "").upper()
            snapshot_date = snap.get("snapshot_date")
            valuation_run_at = snap.get("created_at") or snap.get("updated_at")
            if snap.get("first_low") is not None:
                snap_zones = {
                    "first": (snap.get("first_low"), snap.get("first_high")),
                    "core": (snap.get("core_low"), snap.get("core_high")),
                    "deep": (snap.get("deep_low"), snap.get("deep_high")),
                    "low_confidence": conf == "LOW",
                }
            note = f"历史估值使用 {snap['snapshot_date']} 保存的云端估值快照，可靠性数据取当时结果。"
            if is_legacy_snapshot(snap):
                note += " 该历史快照创建于可靠性层之前，部分可靠性指标不可用。"
        else:
            note = "该日期没有历史估值快照，仅显示技术数据。"
    else:
        try:
            financials = fundamentals_loader(ticker)
        except Exception as exc:
            logger.warning(
                "analysis failed ticker=%s stage=fundamentals error_type=%s message=%s",
                ticker,
                type(exc).__name__,
                str(exc)[:200],
            )
            errors.append({"stage": "fundamentals", "error_type": type(exc).__name__, "message": str(exc)[:200]})
            financials = {}
        try:
            vol = annualized_volatility(df)
            blend = valuate(ticker, financials or {}, volatility=vol)
        except Exception as exc:
            logger.warning(
                "analysis failed ticker=%s stage=valuation error_type=%s message=%s",
                ticker,
                type(exc).__name__,
                str(exc)[:200],
            )
            errors.append({"stage": "valuation", "error_type": type(exc).__name__, "message": str(exc)[:200]})
            blend = {
                "fair": None,
                "fair_low": None,
                "fair_high": None,
                "blended_mid": None,
                "confidence": "UNAVAILABLE",
                "reason": "valuation_exception",
                "reliability": {},
                "profile": {},
            }
        models = (blend or {}).get("models") or {}
        pe = models.get("forward_pe") or models.get("normalized_pe") or models.get("price_to_book_roe")
        dcf = models.get("normalized_fcf_dcf") or models.get("residual_income")
        growth = models.get("growth_adjusted_pe") or models.get("revenue_multiple")
        fair = _mid(blend)
        class_label = (blend.get("profile") or {}).get("valuation_class_label") or "Generic"
        if blend.get("specialized") or blend.get("confidence") == "SPECIALIZED":
            note = f"估值类型：{class_label}。传统估值模型不适用，需要专项场景估值。"
        elif blend.get("confidence") == "UNAVAILABLE":
            note = f"估值类型：{class_label}。有效估值模型不足。"
        else:
            note = f"估值类型：{class_label}。使用 V4.1 reliability layer。"
        if blend.get("excluded"):
            note += " 部分模型已排除。"
        if "high_valuation_uncertainty" in (blend.get("warnings") or []):
            note += " High valuation uncertainty。"
        if errors:
            note += " 部分数据源失败，已保留可用的行情/估值结果。"

    if historical:
        conf = str((blend or {}).get("confidence") or "").upper()
        if snap_zones and snap_zones["first"][0] is not None and conf not in {"SPECIALIZED", "UNAVAILABLE"}:
            zones = snap_zones
        else:
            zones = None
    elif can_emit_buy_zones(blend) and blend.get("mos"):
        zones = dynamic_buy_zones(
            _mid(blend),
            blend["mos"],
            vp["mid"] if vp else None,
            sma200,
            low_confidence=str(blend.get("confidence")) == "LOW",
        )
        blend["zones"] = zones
    else:
        zones = None

    display_name = (financials or {}).get("long_name") or NAMES.get(ticker, ticker)
    reliability = (blend or {}).get("reliability") or {}
    if blend:
        check_valuation_invariants(blend, strict=False)

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
        "fair_value": fair,
        "blended_mid": fair,
        "blended_low": (blend or {}).get("blended_low") if blend and blend.get("blended_low") is not None else (blend or {}).get("fair_low"),
        "blended_high": (blend or {}).get("blended_high") if blend and blend.get("blended_high") is not None else (blend or {}).get("fair_high"),
        "fair_low": (blend or {}).get("fair_low"),
        "fair_high": (blend or {}).get("fair_high"),
        "zones": zones,
        "note": note,
        "state": classify_price(price, fair) if fair else "技术面模式",
        "history": df,
        "blend": blend,
        "financials": financials,
        "financials_period": (financials or {}).get("fcf_period"),
        "price_timestamp": trade_date,
        "snapshot_date": snapshot_date,
        "valuation_run_at": valuation_run_at,
        "data_source": (financials or {}).get("data_source") or "Yahoo Finance / yfinance",
        "valuation_class": (blend or {}).get("profile", {}).get("valuation_class") if blend else None,
        "valuation_class_label": (blend or {}).get("profile", {}).get("valuation_class_label") if blend else None,
        "confidence": (blend or {}).get("confidence"),
        "overall_confidence": (blend or {}).get("overall_confidence") or (blend or {}).get("confidence"),
        "model_version": (blend or {}).get("model_version") if historical else ((blend or {}).get("model_version") or MODEL_VERSION),
        "reliability_score": reliability.get("reliability_score"),
        "dispersion_pct": reliability.get("dispersion_pct") if reliability.get("dispersion_pct") is not None else (blend or {}).get("dispersion"),
        "volatility_1y": (blend or {}).get("volatility_1y"),
        "cycle": (blend or {}).get("cycle"),
        "errors": errors,
        "analysis_error": None,
    }
    if errors and not fair:
        r["analysis_error"] = "财务数据暂时获取失败" if any(e.get("stage") == "fundamentals" for e in errors) else None
    r["recommendation"] = _recommendation_label(r)
    return r


def _recommendation_label(r):
    conf = str((r.get("blend") or {}).get("confidence") or r.get("confidence") or "").upper()
    if conf in {"SPECIALIZED", "UNAVAILABLE"} or not r.get("zones") or r.get("price") is None:
        return "仅技术观察" if r.get("price") is not None else "数据不足"
    z = r["zones"]
    p = r["price"]
    labels = z.get("labels") or {}
    low_conf = conf == "LOW" or z.get("low_confidence")
    deep_name = labels.get("deep") or ("深度折价区" if low_conf else "深度价值区")
    core_name = labels.get("core") or ("参考折价区" if low_conf else "核心买入区")
    first_name = labels.get("first") or ("参考关注区" if low_conf else "第一批区")
    deep = z.get("deep") or (None, None)
    core = z.get("core") or (None, None)
    first = z.get("first") or (None, None)
    if deep[0] is not None and p < deep[0]:
        label = f"低于{deep_name}"
    elif deep[0] is not None and deep[1] is not None and deep[0] <= p <= deep[1]:
        label = deep_name
    elif core[0] is not None and core[1] is not None and core[0] <= p <= core[1]:
        label = core_name
    elif first[0] is not None and first[1] is not None and first[0] <= p <= first[1]:
        label = first_name
    elif first[1] is not None and p <= first[1] * 1.05:
        label = "接近第一批区" if not low_conf else f"接近{first_name}"
    else:
        label = "观察 / 等回调"
    if low_conf and "低置信度" not in label:
        return f"{label}（低置信度）"
    return label
