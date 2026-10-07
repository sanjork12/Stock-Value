
from __future__ import annotations

import argparse
import logging
import math
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("stock_fair_value_monitor")

MAG7 = {"AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA"}
FCF_WEIGHTS_3Y = (0.50, 0.30, 0.20)

OCF_ALIASES = (
    "Operating Cash Flow",
    "Total Cash From Operating Activities",
    "Cash Flow From Continuing Operating Activities",
)
CAPEX_ALIASES = (
    "Capital Expenditure",
    "Capital Expenditures",
    "Purchase Of PPE",
)
FCF_ALIASES = ("Free Cash Flow",)


def fnum(x):
    try:
        if x is None:
            return None
        x = float(x)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _yfinance():
    """Import yfinance on first use so a Cloud wheel mismatch does not crash app boot."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance failed to import. Use Python 3.12 on Streamlit Cloud and install "
            "yfinance, curl_cffi, websockets, and lxml."
        ) from exc
    return yf


OHLCV_NAMES = {"open", "high", "low", "close", "adj close", "adj_close", "volume"}


def flatten_yahoo_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance single-ticker frames so Close/High/Low/Volume always exist."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        chosen = None
        for level in range(out.columns.nlevels):
            labels = {str(v).strip().lower() for v in out.columns.get_level_values(level)}
            if labels & OHLCV_NAMES:
                out.columns = out.columns.get_level_values(level)
                chosen = level
                break
        if chosen is None:
            out.columns = [c[-1] if isinstance(c, tuple) else c for c in out.columns]
    out.columns = [str(c).strip() for c in out.columns]
    rename = {}
    for col in out.columns:
        key = col.lower().replace("_", " ")
        if key == "adj close":
            rename[col] = "Adj Close"
        elif key in {"open", "high", "low", "close", "volume"}:
            rename[col] = key.title()
    if rename:
        out = out.rename(columns=rename)
    if "Close" not in out.columns:
        raise RuntimeError(f"No Close column after flattening Yahoo bars: {list(out.columns)}")
    return out


def get_history(ticker: str, as_of: Optional[str]) -> pd.DataFrame:
    # Need enough history for 200d SMA + volume profile.
    if as_of:
        end_dt = pd.Timestamp(as_of) + pd.Timedelta(days=1)
    else:
        end_dt = pd.Timestamp.today(tz=None) + pd.Timedelta(days=1)
    start_dt = end_dt - pd.Timedelta(days=800)
    start_s = start_dt.strftime("%Y-%m-%d")
    end_s = end_dt.strftime("%Y-%m-%d")
    last_error = None
    df = None
    try:
        df = _yfinance().download(
            ticker,
            start=start_s,
            end=end_s,
            auto_adjust=False,
            progress=False,
            actions=False,
            threads=False,
            group_by="column",
        )
    except TypeError:
        try:
            df = _yfinance().download(
                ticker,
                start=start_s,
                end=end_s,
                auto_adjust=False,
                progress=False,
                actions=False,
                threads=False,
            )
        except Exception as exc:
            last_error = exc
            logger.warning("history stage=download ticker=%s error_type=%s", ticker, type(exc).__name__)
    except Exception as exc:
        last_error = exc
        logger.warning("history stage=download ticker=%s error_type=%s", ticker, type(exc).__name__)
    if df is None or df.empty:
        try:
            df = _yfinance().Ticker(ticker).history(start=start_s, end=end_s, auto_adjust=False)
        except Exception as exc:
            last_error = exc
            logger.warning("history stage=ticker.history ticker=%s error_type=%s", ticker, type(exc).__name__)
    if df is None or df.empty:
        detail = type(last_error).__name__ if last_error else "empty"
        raise RuntimeError(f"No price data returned for {ticker} ({detail}).")
    df = flatten_yahoo_ohlcv(df)
    return df.dropna(subset=["Close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for n in (30,50,200):
        out[f"SMA{n}"] = out["Close"].rolling(n).mean()
    return out


def volume_profile_zone(df: pd.DataFrame, lookback=252, bins=24):
    d = df.tail(lookback).copy()
    if len(d) < 30 or "Volume" not in d or d["Volume"].fillna(0).sum() <= 0:
        return None
    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    lo, hi = float(typical.min()), float(typical.max())
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins+1)
    idx = np.clip(np.digitize(typical.to_numpy(), edges)-1, 0, bins-1)
    vols = np.zeros(bins)
    for i, v in zip(idx, d["Volume"].fillna(0).to_numpy()):
        vols[i] += float(v)
    top = int(np.argmax(vols))
    return {
        "low": float(edges[top]),
        "high": float(edges[top+1]),
        "mid": float((edges[top]+edges[top+1])/2),
    }


def annualized_volatility(df: pd.DataFrame, lookback=252) -> float | None:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    closes = df["Close"].dropna().tail(lookback + 1)
    if len(closes) < 60:
        return None
    rets = closes.pct_change().dropna()
    if len(rets) < 40:
        return None
    std = float(rets.std())
    if not math.isfinite(std) or std < 0:
        return None
    return std * math.sqrt(252)


def metric_field(value, source=None, period=None, unit="USD", raw=None):
    return {
        "value": fnum(value),
        "raw": raw if raw is not None else value,
        "source": source,
        "period": period,
        "unit": unit,
    }


def normalize_capex(raw_capex):
    """Return CapEx as a positive cash outflow."""
    value = fnum(raw_capex)
    if value is None:
        return None
    return abs(value)


def model_result(
    name,
    *,
    valid=True,
    low=None,
    mid=None,
    high=None,
    confidence="medium",
    reason=None,
    inputs=None,
    warnings=None,
    outlier=False,
    extra=None,
):
    result = {
        "name": name,
        "valid": bool(valid) and not outlier,
        "outlier": bool(outlier),
        "low": fnum(low),
        "mid": fnum(mid),
        "high": fnum(high),
        "confidence": "invalid" if not valid or outlier else confidence,
        "reason": reason,
        "inputs": inputs or {},
        "warnings": list(warnings or []),
    }
    if extra:
        result.update(extra)
    if result["valid"] and not range_is_ordered(result["low"], result["mid"], result["high"]):
        result["valid"] = False
        result["confidence"] = "invalid"
        result["reason"] = result["reason"] or "unordered_or_nonpositive_range"
    return result


def range_is_ordered(low, mid, high) -> bool:
    low, mid, high = fnum(low), fnum(mid), fnum(high)
    if low is None or mid is None or high is None:
        return False
    if min(low, mid, high) <= 0:
        return False
    if not all(math.isfinite(v) for v in (low, mid, high)):
        return False
    return low <= mid <= high


def structural_valid(model) -> bool:
    if not model:
        return False
    if model.get("valid") is False or model.get("outlier"):
        return False
    return range_is_ordered(model.get("low"), model.get("mid"), model.get("high"))


def _cashflow_row(df: pd.DataFrame, aliases, col):
    if df is None or df.empty:
        return None
    lowered = {str(idx).strip().lower(): idx for idx in df.index}
    for alias in aliases:
        key = lowered.get(str(alias).strip().lower())
        if key is not None:
            try:
                return fnum(df.loc[key, col])
            except Exception:
                return None
    return None


def _period_label(col) -> str:
    try:
        ts = pd.Timestamp(col)
        return f"FY{ts.year}"
    except Exception:
        return str(col)


def _yearly_cashflows(cf: pd.DataFrame) -> list[dict]:
    rows = []
    if cf is None or cf.empty:
        return rows
    for col in list(cf.columns)[:5]:
        ocf = _cashflow_row(cf, OCF_ALIASES, col)
        capex_raw = _cashflow_row(cf, CAPEX_ALIASES, col)
        capex_outflow = normalize_capex(capex_raw)
        fcf_reported = _cashflow_row(cf, FCF_ALIASES, col)
        fcf_computed = None
        if ocf is not None and capex_outflow is not None:
            fcf_computed = ocf - capex_outflow
        fcf = fcf_reported if fcf_reported is not None else fcf_computed
        if ocf is None and capex_raw is None and fcf is None:
            continue
        rows.append({
            "period": _period_label(col),
            "column": str(col),
            "operating_cash_flow": ocf,
            "capital_expenditure_raw": capex_raw,
            "capital_expenditure": capex_outflow,
            "free_cash_flow_reported": fcf_reported,
            "free_cash_flow_computed": fcf_computed,
            "free_cash_flow": fcf,
            "source": "ticker.cashflow",
        })
        if len(rows) >= 3:
            break
    return rows


def _normalize_fcf(annual_rows: list[dict], ttm_fcf=None) -> dict:
    values = [row["free_cash_flow"] for row in annual_rows if fnum(row.get("free_cash_flow")) is not None]
    warnings = []
    if len(values) >= 3:
        median = float(np.median(values[:3]))
        weighted = sum(w * v for w, v in zip(FCF_WEIGHTS_3Y, values[:3]))
        latest = values[0]
        if latest is not None and median > 0 and latest < 0.5 * median:
            warnings.append("latest_fcf_well_below_history")
        # Median damps a single high-CapEx year without inventing a positive FCF.
        return {
            "value": median,
            "method": "median_3y_annual",
            "weighted_3y": weighted,
            "latest": latest,
            "source": "ticker.cashflow",
            "period": f"{annual_rows[2]['period']}-{annual_rows[0]['period']}",
            "warnings": warnings,
        }
    if len(values) == 2:
        weighted = 0.6 * values[0] + 0.4 * values[1]
        return {
            "value": weighted,
            "method": "weighted_2y_annual",
            "latest": values[0],
            "source": "ticker.cashflow",
            "period": f"{annual_rows[1]['period']}-{annual_rows[0]['period']}",
            "warnings": warnings,
        }
    if len(values) == 1:
        return {
            "value": values[0],
            "method": "latest_annual",
            "latest": values[0],
            "source": "ticker.cashflow",
            "period": annual_rows[0]["period"],
            "warnings": warnings + ["only_one_annual_fcf"],
        }
    if fnum(ttm_fcf) is not None:
        return {
            "value": fnum(ttm_fcf),
            "method": "yahoo_info_freeCashflow",
            "latest": fnum(ttm_fcf),
            "source": "ticker.info.freeCashflow",
            "period": "TTM",
            "warnings": warnings + ["fallback_ttm_info_freeCashflow"],
        }
    return {
        "value": None,
        "method": None,
        "source": None,
        "period": None,
        "warnings": warnings + ["missing_fcf"],
    }


def _fast_info_get(fast, *names):
    for name in names:
        try:
            if isinstance(fast, dict):
                value = fast.get(name)
            else:
                value = getattr(fast, name, None)
        except Exception:
            value = None
        number = fnum(value)
        if number is not None:
            return number
    return None


def _merge_ticker_info(ticker: str, t) -> dict:
    from financial_forensics_observer import observe_info
    info = {}
    try:
        raw = t.get_info() if hasattr(t, "get_info") else None
        observe_info("ticker.get_info", raw)
        if isinstance(raw, dict) and raw:
            info.update(raw)
    except Exception as exc:
        observe_info("ticker.get_info", None, "ERROR")
        logger.warning("fundamentals stage=get_info ticker=%s error_type=%s", ticker, type(exc).__name__)
    if not info:
        try:
            raw = t.info or {}
            observe_info("ticker.info", raw)
            if isinstance(raw, dict) and raw:
                info.update(raw)
        except Exception as exc:
            observe_info("ticker.info", None, "ERROR")
            logger.warning("fundamentals stage=info ticker=%s error_type=%s", ticker, type(exc).__name__)
    try:
        fast = t.fast_info if hasattr(t, "fast_info") else None
        if fast is not None:
            shares = _fast_info_get(fast, "shares", "sharesOutstanding")
            if shares is not None and fnum(info.get("sharesOutstanding")) is None:
                info["sharesOutstanding"] = shares
                observe_info("ticker.fast_info", {"sharesOutstanding":shares})
            market_cap = _fast_info_get(fast, "market_cap", "marketCap")
            if market_cap is not None and fnum(info.get("marketCap")) is None:
                info["marketCap"] = market_cap
                observe_info("ticker.fast_info", {"marketCap":market_cap})
            last = _fast_info_get(fast, "last_price", "lastPrice", "regularMarketPrice")
            if last is not None and fnum(info.get("currentPrice")) is None:
                info["currentPrice"] = last
                observe_info("ticker.fast_info", {"currentPrice":last})
    except Exception as exc:
        logger.warning("fundamentals stage=fast_info ticker=%s error_type=%s", ticker, type(exc).__name__)
    return info


def _forward_eps_from_estimates(ticker: str, t):
    from financial_forensics_observer import observe_estimate
    try:
        getter = getattr(t, "get_earnings_estimate", None)
        df = getter() if callable(getter) else None
        if df is None or getattr(df, "empty", True):
            observe_estimate("NOT_AVAILABLE", None)
            return None
        for idx in ("0y", "+1y", "0q", "+1q"):
            if idx in df.index and "avg" in df.columns:
                value = fnum(df.loc[idx, "avg"])
                observe_estimate(idx, value)
                if value is not None and value > 0:
                    return value
        if "avg" in df.columns:
            series = df["avg"].dropna()
            if len(series):
                value = fnum(series.iloc[0])
                observe_estimate("FIRST_AVAILABLE_AVG", value)
                if value is not None and value > 0:
                    return value
    except Exception as exc:
        observe_estimate("ERROR", None)
        logger.warning("fundamentals stage=earnings_estimate ticker=%s error_type=%s", ticker, type(exc).__name__)
    return None


def _load_statement(ticker: str, t, stage: str, attrs: tuple[str, ...], methods: tuple[str, ...]):
    from financial_forensics_observer import observe_statement
    for attr in attrs:
        try:
            df = getattr(t, attr, None)
            observe_statement(stage, "ticker."+attr, df)
            if df is not None and hasattr(df, "empty") and not df.empty:
                return df
        except Exception as exc:
            observe_statement(stage, "ticker."+attr, None, "ERROR")
            logger.warning("fundamentals stage=%s ticker=%s error_type=%s", stage, ticker, type(exc).__name__)
    for name in methods:
        fn = getattr(t, name, None)
        if not callable(fn):
            continue
        try:
            df = fn()
            observe_statement(stage, "ticker."+name, df)
            if df is not None and hasattr(df, "empty") and not df.empty:
                return df
        except Exception as exc:
            observe_statement(stage, "ticker."+name, None, "ERROR")
            logger.warning("fundamentals stage=%s ticker=%s error_type=%s", stage, ticker, type(exc).__name__)
    return None


def get_live_fundamentals(ticker: str):
    t = _yfinance().Ticker(ticker)
    info = _merge_ticker_info(ticker, t)

    current = fnum(info.get("currentPrice") or info.get("regularMarketPrice"))
    forward_eps = fnum(info.get("forwardEps"))
    trailing_eps = fnum(info.get("trailingEps"))
    shares_outstanding = fnum(info.get("sharesOutstanding"))
    implied_shares = fnum(info.get("impliedSharesOutstanding"))
    shares = shares_outstanding
    total_cash = fnum(info.get("totalCash"))
    total_debt = fnum(info.get("totalDebt"))
    market_cap = fnum(info.get("marketCap"))
    quote_currency = info.get("currency")
    financial_currency = info.get("financialCurrency") or info.get("financialCurrencyCode")
    earnings_growth = fnum(info.get("earningsGrowth"))
    ttm_fcf = fnum(info.get("freeCashflow"))
    ttm_ocf = fnum(info.get("operatingCashflow"))
    book_value = fnum(info.get("bookValue"))
    roe = fnum(info.get("returnOnEquity"))
    ebitda = fnum(info.get("ebitda"))
    revenue = fnum(info.get("totalRevenue"))
    enterprise_value = fnum(info.get("enterpriseValue"))
    nta = fnum(info.get("netTangibleAssets"))
    tangible_bvps = nta / shares if nta and shares and shares > 0 else None
    dividend_rate = fnum(info.get("dividendRate"))
    beta = fnum(info.get("beta"))
    operating_margin = fnum(info.get("operatingMargins") or info.get("operatingMargin"))
    profit_margin = fnum(info.get("profitMargins"))
    sector = info.get("sector")
    industry = info.get("industry")
    quote_type = info.get("quoteType")
    long_name = info.get("shortName") or info.get("longName")

    annual_rows = []
    cashflow_df = _load_statement(
        ticker, t, "cashflow",
        ("cashflow", "cash_flow"),
        ("get_cashflow", "get_cash_flow"),
    )
    try:
        if cashflow_df is not None:
            annual_rows = _yearly_cashflows(cashflow_df)
    except Exception as exc:
        logger.warning("fundamentals stage=cashflow_parse ticker=%s error_type=%s", ticker, type(exc).__name__)
        annual_rows = []

    historical_eps = []
    historical_margins = []
    inc = _load_statement(
        ticker, t, "income_stmt",
        ("income_stmt", "financials"),
        ("get_income_stmt", "get_financials"),
    )
    try:
        if inc is not None and not inc.empty:
            for col in list(inc.columns)[:5]:
                net_income = _cashflow_row(inc, ("Net Income", "Net Income Common Stockholders"), col)
                share_count = _cashflow_row(inc, ("Diluted Average Shares", "Basic Average Shares"), col)
                revenue_row = _cashflow_row(inc, ("Total Revenue", "Operating Revenue"), col)
                operating_income = _cashflow_row(inc, ("Operating Income", "EBIT"), col)
                diluted_eps = _cashflow_row(inc, ("Diluted EPS", "Basic EPS"), col)
                eps = fnum(diluted_eps)
                if eps is None and net_income is not None and share_count:
                    eps = net_income / share_count
                if eps is not None or net_income is not None:
                    historical_eps.append({
                        "period": _period_label(col),
                        "net_income": net_income,
                        "shares": share_count,
                        "eps": fnum(eps),
                        "diluted_eps": fnum(diluted_eps),
                    })
                if revenue_row and revenue_row > 0 and operating_income is not None:
                    historical_margins.append({
                        "period": _period_label(col),
                        "revenue": revenue_row,
                        "operating_income": operating_income,
                        "operating_margin": operating_income / revenue_row,
                    })
    except Exception as exc:
        logger.warning("fundamentals stage=income_parse ticker=%s error_type=%s", ticker, type(exc).__name__)
        historical_eps = []
        historical_margins = []

    diluted_average_shares = fnum(historical_eps[0].get("shares")) if historical_eps else None
    statement_eps = None
    statement_eps_source = None
    if historical_eps:
        statement_eps = fnum(historical_eps[0].get("diluted_eps")) or fnum(historical_eps[0].get("eps"))
        if historical_eps[0].get("diluted_eps") is not None:
            statement_eps_source = "income_statement_diluted_eps"
        elif statement_eps is not None:
            statement_eps_source = "ni_over_diluted_shares"
    forward_eps_source = "ticker.info.forwardEps" if forward_eps and forward_eps > 0 else None
    trailing_eps_source = "ticker.info.trailingEps" if trailing_eps and trailing_eps > 0 else None
    if forward_eps is None or forward_eps <= 0:
        estimated = _forward_eps_from_estimates(ticker, t)
        if estimated:
            forward_eps = estimated
            forward_eps_source = "earnings_estimate"
    if (forward_eps is None or forward_eps <= 0) and fnum(info.get("epsForward")):
        forward_eps = fnum(info.get("epsForward"))
        forward_eps_source = "epsForward"
    if (forward_eps is None or forward_eps <= 0) and current and fnum(info.get("forwardPE")):
        pe = fnum(info.get("forwardPE"))
        if pe and pe > 0:
            forward_eps = current / pe
            forward_eps_source = "price/forwardPE"
    extra_warnings = []
    if forward_eps is not None and forward_eps <= 0:
        forward_eps = None
        forward_eps_source = None

    bs = _load_statement(
        ticker, t, "balance_sheet",
        ("balance_sheet", "balancesheet", "quarterly_balance_sheet", "quarterly_balancesheet"),
        ("get_balance_sheet", "get_balancesheet"),
    )
    equity = None
    try:
        if bs is not None and not bs.empty:
            col0 = list(bs.columns)[0]
            equity = _cashflow_row(
                bs,
                (
                    "Stockholders Equity",
                    "Stockholder Equity",
                    "Total Stockholder Equity",
                    "Total Stockholders Equity",
                    "Common Stock Equity",
                    "Total Equity Gross Minority Interest",
                    "Equity Attributable to Owners of Parent",
                    "Tangible Book Value",
                    "Net Tangible Assets",
                ),
                col0,
            )
            if shares is None:
                shares = _cashflow_row(
                    bs,
                    ("Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding", "Common Shares"),
                    col0,
                )
            if book_value is None and equity and shares and shares > 0:
                book_value = equity / shares
            if tangible_bvps is None:
                tba = _cashflow_row(bs, ("Tangible Book Value", "Net Tangible Assets"), col0)
                if tba and shares and shares > 0:
                    tangible_bvps = tba / shares
            if total_cash is None:
                total_cash = _cashflow_row(
                    bs,
                    ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash Financial"),
                    col0,
                )
            if total_debt is None:
                total_debt = _cashflow_row(
                    bs,
                    ("Total Debt", "Long Term Debt And Capital Lease Obligation", "Net Debt"),
                    col0,
                )
    except Exception as exc:
        logger.warning("fundamentals stage=balance_parse ticker=%s error_type=%s", ticker, type(exc).__name__)
        equity = None
    latest_ni = historical_eps[0].get("net_income") if historical_eps else None
    if roe is None and equity and latest_ni is not None and equity != 0:
        roe = latest_ni / equity
    if roe is None and book_value and book_value > 0 and trailing_eps:
        roe = trailing_eps / book_value

    if tangible_bvps is None and nta and shares and shares > 0:
        tangible_bvps = nta / shares
    if not long_name:
        long_name = ticker

    latest_annual = annual_rows[0] if annual_rows else {}
    normalized = _normalize_fcf(annual_rows, ttm_fcf=ttm_fcf)
    cash = total_cash if total_cash is not None else 0.0
    debt = total_debt if total_debt is not None else 0.0
    from financial_forensics_observer import observe_selected
    observe_selected("cash", cash, "fallback_missing_assumed_zero" if total_cash is None else
                     "ticker.info.totalCash" if fnum(info.get("totalCash")) is not None else "ticker.balance_sheet.cash", total_cash)
    observe_selected("debt", debt, "fallback_missing_assumed_zero" if total_debt is None else
                     "ticker.info.totalDebt" if fnum(info.get("totalDebt")) is not None else "ticker.balance_sheet.debt", total_debt)
    observe_selected("shares", shares, "ticker.info.sharesOutstanding" if shares_outstanding is not None else "ticker.balance_sheet.shares", shares_outstanding)
    observe_selected("revenue_growth", fnum(info.get("revenueGrowth")), "ticker.info.revenueGrowth", fnum(info.get("revenueGrowth")))
    if cash < 0:
        cash = 0.0
    if debt < 0:
        debt = 0.0
    if fnum(normalized.get("value")) is None and fnum(forward_eps) is None and fnum(trailing_eps) is None:
        logger.warning(
            "fundamentals stage=empty ticker=%s error_type=EmptyFundamentals message=no eps/fcf after fallbacks",
            ticker,
        )

    payload = {
        "analyst_consensus_target": fnum(info.get("targetMeanPrice")),
        "analyst_target_low": fnum(info.get("targetLowPrice")),
        "analyst_target_high": fnum(info.get("targetHighPrice")),
        "analyst_count": fnum(info.get("numberOfAnalystOpinions")),
        "consensus_source": "Yahoo Finance / yfinance ticker.info",
        "consensus_updated_at": None,
        "forward_estimate_updated_at": None,
        "current_forward_pe": fnum(info.get("forwardPE")),
        "current_price": current,
        "forward_eps": forward_eps,
        "forward_eps_source": forward_eps_source,
        "trailing_eps": trailing_eps,
        "trailing_eps_source": trailing_eps_source,
        "statement_eps": statement_eps,
        "statement_eps_source": statement_eps_source,
        "eps_proxy": None,
        "eps_proxy_source": None,
        "quote_currency": quote_currency,
        "financial_currency": financial_currency,
        "eps_currency": financial_currency,
        "shares": shares,
        "shares_outstanding": shares_outstanding,
        "implied_shares_outstanding": implied_shares,
        "diluted_average_shares": diluted_average_shares,
        "cash": cash,
        "debt": debt,
        "market_cap": market_cap,
        "earnings_growth": earnings_growth,
        "fcf": normalized.get("value"),
        "fcf_method": normalized.get("method"),
        "fcf_period": normalized.get("period"),
        "fcf_source": normalized.get("source"),
        "fcf_ttm_info": ttm_fcf,
        "operating_cash_flow": latest_annual.get("operating_cash_flow") or ttm_ocf,
        "capital_expenditure_raw": latest_annual.get("capital_expenditure_raw"),
        "capital_expenditure": latest_annual.get("capital_expenditure"),
        "annual_cashflows": annual_rows,
        "book_value_per_share": book_value,
        "tangible_book_value_per_share": tangible_bvps,
        "roe": roe,
        "ebitda": ebitda,
        "revenue": revenue,
        "enterprise_value": enterprise_value,
        "dividend_rate": dividend_rate,
        "beta": beta,
        "sector": sector,
        "industry": industry,
        "quote_type": quote_type,
        "long_name": long_name,
        "historical_eps": historical_eps,
        "historical_margins": historical_margins,
        "operating_margin": operating_margin,
        "profit_margin": profit_margin,
        "normalized": {
            "forward_eps": metric_field(forward_eps, forward_eps_source or "ticker.info.forwardEps", unit="USD/share"),
            "trailing_eps": metric_field(trailing_eps, trailing_eps_source or "ticker.info.trailingEps", unit="USD/share"),
            "operating_cash_flow": metric_field(
                latest_annual.get("operating_cash_flow") or ttm_ocf,
                "ticker.cashflow" if latest_annual else "ticker.info.operatingCashflow",
                latest_annual.get("period"),
            ),
            "capital_expenditure": metric_field(
                latest_annual.get("capital_expenditure"),
                "ticker.cashflow",
                latest_annual.get("period"),
                raw=latest_annual.get("capital_expenditure_raw"),
            ),
            "free_cash_flow": metric_field(
                normalized.get("value"),
                normalized.get("source"),
                normalized.get("period"),
            ),
            "total_cash": metric_field(cash, "ticker.info.totalCash"),
            "total_debt": metric_field(debt, "ticker.info.totalDebt"),
            "shares_outstanding": metric_field(shares, "ticker.info.sharesOutstanding", unit="shares"),
            "market_cap": metric_field(market_cap, "ticker.info.marketCap"),
            "earnings_growth": metric_field(earnings_growth, "ticker.info.earningsGrowth", unit="ratio"),
        },
        "warnings": list(normalized.get("warnings") or []) + extra_warnings,
        "data_source": "Yahoo Finance / yfinance",
    }
    return fill_fundamental_fallbacks(payload)


def fill_fundamental_fallbacks(financials: dict | None) -> dict:
    """Normalize EPS provenance, currency safety, and canonical shares.

    Never fills forward_eps from statement EPS. Statement-derived trailing is
    only allowed when financial_currency matches quote_currency.
    """
    from financial_normalization import normalize_financials

    return normalize_financials(financials)


def classify_price(price, fair):
    if fair is None or fair <= 0:
        return "N/A"
    ratio = price/fair
    if ratio <= 0.80:
        return "Deep-value zone"
    if ratio <= 0.90:
        return "Attractive zone"
    if ratio <= 1.00:
        return "Fair-to-attractive"
    if ratio <= 1.10:
        return "Near fair value"
    return "Above fair value / observe"


def money(x):
    return "N/A" if x is None or not math.isfinite(float(x)) else f"${x:,.2f}"


def pct(a,b):
    if a is None or b in (None,0):
        return None
    return (a/b-1)*100


def run(ticker, as_of=None):
    from valuation_engine import can_emit_buy_zones, valuate
    from valuation_primitives import range_is_ordered

    ticker = ticker.upper().strip()
    df = add_indicators(get_history(ticker, as_of))
    row = df.iloc[-1]
    trade_date = pd.Timestamp(df.index[-1]).date().isoformat()
    price = float(row["Close"])
    sma30 = fnum(row["SMA30"])
    sma50 = fnum(row["SMA50"])
    sma200 = fnum(row["SMA200"])
    vp = volume_profile_zone(df)
    vol = annualized_volatility(df)

    historical = as_of is not None and pd.Timestamp(as_of).date() < date.today()
    blend = None
    fair = None
    zones = None

    if historical:
        valuation_note = (
            "CLI no longer reads local JSON snapshots. "
            "Historical fair value comes from Supabase; technical comparison is still valid."
        )
    else:
        financials = fill_fundamental_fallbacks(get_live_fundamentals(ticker))
        blend = valuate(ticker, financials, volatility=vol)
        fair = blend.get("fair")
        valuation_note = (
            f"V4.1 {blend.get('profile', {}).get('valuation_class_label') or ''} | "
            f"confidence={blend.get('confidence')}"
        )
        if blend.get("excluded"):
            reasons = ", ".join(f"{item['name']}={item['reason']}" for item in blend["excluded"])
            valuation_note += f" Excluded models: {reasons}."
        if blend.get("warnings"):
            valuation_note += " " + ", ".join(blend["warnings"])
        if can_emit_buy_zones(blend):
            zones = blend.get("zones")

    print("\n" + "=" * 72)
    print(f"{ticker}  |  price date: {trade_date}")
    print("=" * 72)
    print(f"Close:   {money(price)}")
    print(f"SMA30:   {money(sma30)}   distance: {pct(price,sma30):+.2f}%" if sma30 else "SMA30: N/A")
    print(f"SMA50:   {money(sma50)}   distance: {pct(price,sma50):+.2f}%" if sma50 else "SMA50: N/A")
    print(f"SMA200:  {money(sma200)}   distance: {pct(price,sma200):+.2f}%" if sma200 else "SMA200: N/A")
    if vp:
        print(f"1Y volume-density zone (approx.): {money(vp['low'])} - {money(vp['high'])}")

    print("\nValuation")
    print("-" * 72)

    def _print_model(label, obj):
        if obj and obj.get("valid") and range_is_ordered(obj.get("low"), obj.get("mid"), obj.get("high")):
            print(f"{label:<16}{money(obj['low'])} / {money(obj['mid'])} / {money(obj['high'])}")
        elif obj:
            print(f"{label:<16}N/A  ({obj.get('reason') or 'invalid'})")
        else:
            print(f"{label:<16}N/A")

    if blend and blend.get("model_list"):
        for obj in blend["model_list"]:
            _print_model(f"{obj.get('name')}:", obj)
    print(f"Blended fair:   {money(fair)}")
    if blend:
        print(f"Class/confidence: {blend.get('profile', {}).get('valuation_class')} / {blend.get('confidence')}")
    if fair:
        print(f"Price vs fair:  {pct(price,fair):+.2f}%")
        print(f"Valuation state: {classify_price(price,fair)}")

    if zones:
        print("\nSuggested valuation zones (not trading advice)")
        print("-" * 72)
        print(f"First-entry:    {money(zones['first'][0])} - {money(zones['first'][1])}")
        print(f"Core-buy:       {money(zones['core'][0])} - {money(zones['core'][1])}")
        print(f"Deep-value:     {money(zones['deep'][0])} - {money(zones['deep'][1])}")

    print("\nNotes")
    print("-" * 72)
    print(valuation_note)
    print("Volume-density zone is an estimate from daily price/volume bars, not actual investor cost basis.")
    print("Fair value is a model output, not Investing.com's proprietary Fair Value.")
    print("=" * 72 + "\n")


def main():
    from valuation_engine import valuate

    p = argparse.ArgumentParser(description="Magnificent Seven valuation + technical monitor")
    p.add_argument("ticker", nargs="?", help="AAPL MSFT GOOGL AMZN NVDA META TSLA")
    p.add_argument("--date", help="Historical date, YYYY-MM-DD")
    p.add_argument("--sanity", action="store_true", help="Run MAG7 valuation sanity check")
    args = p.parse_args()

    if args.sanity:
        print(f"{'ticker':<7} {'price':>10} {'class':<24} {'conf':<12} {'fair':>10} included")
        for ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"):
            df = add_indicators(get_history(ticker, None))
            price = float(df.iloc[-1]["Close"])
            financials = fill_fundamental_fallbacks(get_live_fundamentals(ticker))
            blend = valuate(ticker, financials, volatility=annualized_volatility(df))
            print(
                f"{ticker:<7} {money(price):>10} {str((blend.get('profile') or {}).get('valuation_class') or '-'):<24} "
                f"{str(blend.get('confidence') or '-'):<12} {money(blend.get('fair')):>10} "
                f"{','.join(blend.get('included') or [])}"
            )
        return

    ticker = args.ticker or input("Ticker (AAPL/MSFT/GOOGL/AMZN/NVDA/META/TSLA): ").strip()
    as_of = args.date
    if as_of is None:
        d = input("Date YYYY-MM-DD (press Enter for latest): ").strip()
        as_of = d or None
    run(ticker, as_of)


if __name__ == "__main__":
    main()
