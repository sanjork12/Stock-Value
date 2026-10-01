
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

APP_DIR = Path(__file__).resolve().parent
SNAPSHOT_FILE = APP_DIR / "valuation_snapshots.json"

MAG7 = {"AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA"}
GENERIC_ASSUMPTION = {"pe_range":[18,24], "norm_growth":0.12, "peg_target":1.5, "growth_pe_cap":30, "dcf_growth":0.10}

# These are intentionally editable assumptions, not "truth".
# They are the valuation framework used by this program.
ASSUMPTIONS = {
    "AAPL": {"pe_range":[28,32], "norm_growth":0.09, "peg_target":1.8, "growth_pe_cap":32, "dcf_growth":0.08},
    "MSFT": {"pe_range":[27,32], "norm_growth":0.18, "peg_target":1.7, "growth_pe_cap":34, "dcf_growth":0.16},
    "GOOGL":{"pe_range":[22,26], "norm_growth":0.18, "peg_target":1.5, "growth_pe_cap":30, "dcf_growth":0.16},
    "AMZN": {"pe_range":[27,32], "norm_growth":0.20, "peg_target":1.5, "growth_pe_cap":34, "dcf_growth":0.18},
    "NVDA": {"pe_range":[25,32], "norm_growth":0.24, "peg_target":1.4, "growth_pe_cap":38, "dcf_growth":0.22},
    "META": {"pe_range":[22,27], "norm_growth":0.16, "peg_target":1.5, "growth_pe_cap":30, "dcf_growth":0.15},
    "TSLA": {"pe_range":[60,100],"norm_growth":0.25, "peg_target":2.0, "growth_pe_cap":120,"dcf_growth":0.18},
}

WEIGHTS = {"pe":0.35, "dcf":0.40, "growth":0.25}
DISCOUNT_RATE = 0.09
TERMINAL_GROWTH = 0.03


def fnum(x):
    try:
        if x is None:
            return None
        x = float(x)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def get_history(ticker: str, as_of: Optional[str]) -> pd.DataFrame:
    # Need enough history for 200d SMA + volume profile.
    if as_of:
        end_dt = pd.Timestamp(as_of) + pd.Timedelta(days=1)
    else:
        end_dt = pd.Timestamp.today(tz=None) + pd.Timedelta(days=1)
    start_dt = end_dt - pd.Timedelta(days=800)
    df = yf.download(
        ticker,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=False,
        progress=False,
        actions=False,
        threads=False,
    )
    if df.empty:
        raise RuntimeError(f"No price data returned for {ticker}.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
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


def get_live_fundamentals(ticker: str):
    t = yf.Ticker(ticker)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    # yfinance fields can be missing; keep fallbacks explicit.
    current = fnum(info.get("currentPrice") or info.get("regularMarketPrice"))
    forward_eps = fnum(info.get("forwardEps"))
    trailing_eps = fnum(info.get("trailingEps"))
    shares = fnum(info.get("sharesOutstanding"))
    total_cash = fnum(info.get("totalCash")) or 0.0
    total_debt = fnum(info.get("totalDebt")) or 0.0
    market_cap = fnum(info.get("marketCap"))
    earnings_growth = fnum(info.get("earningsGrowth"))

    fcf = fnum(info.get("freeCashflow"))
    if fcf is None:
        # Try annual cashflow statement: OCF - CapEx.
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                col = cf.columns[0]
                ocf = None
                capex = None
                for key in ["Operating Cash Flow","Total Cash From Operating Activities"]:
                    if key in cf.index:
                        ocf = fnum(cf.loc[key, col])
                        break
                for key in ["Capital Expenditure","Capital Expenditures"]:
                    if key in cf.index:
                        capex = fnum(cf.loc[key, col])
                        break
                if ocf is not None and capex is not None:
                    # CapEx is usually negative in Yahoo statements.
                    fcf = ocf + capex if capex < 0 else ocf - capex
        except Exception:
            pass

    return {
        "current_price":current,
        "forward_eps":forward_eps,
        "trailing_eps":trailing_eps,
        "shares":shares,
        "cash":total_cash,
        "debt":total_debt,
        "market_cap":market_cap,
        "earnings_growth":earnings_growth,
        "fcf":fcf,
    }


def get_assumption(ticker):
    return ASSUMPTIONS.get(ticker.upper(), GENERIC_ASSUMPTION.copy())


def pe_model(ticker, forward_eps):
    a = get_assumption(ticker)
    if not forward_eps or forward_eps <= 0:
        return None
    lo, hi = a["pe_range"]
    return {
        "low":forward_eps*lo,
        "mid":forward_eps*((lo+hi)/2),
        "high":forward_eps*hi,
    }


def growth_model(ticker, forward_eps, live_growth=None):
    if not forward_eps or forward_eps <= 0:
        return None
    a = get_assumption(ticker)
    # Blend live growth with normalized assumption if sensible.
    g = a["norm_growth"]
    if live_growth is not None and 0 < live_growth < 1:
        g = 0.5*g + 0.5*live_growth
    growth_pct = g*100
    fair_pe = growth_pct*a["peg_target"]
    fair_pe = max(12, min(fair_pe, a["growth_pe_cap"]))
    # Wider band because growth estimates are noisy.
    return {
        "low":forward_eps*fair_pe*0.88,
        "mid":forward_eps*fair_pe,
        "high":forward_eps*fair_pe*1.12,
        "fair_pe":fair_pe,
        "growth_used":g,
    }


def dcf_model(ticker, fcf, shares, cash, debt):
    if not fcf or not shares or fcf <= 0 or shares <= 0:
        return None
    g = get_assumption(ticker)["dcf_growth"]
    # Fade growth linearly over 5 years toward a mature rate.
    mature = max(0.06, min(0.10, g*0.45))
    flows = []
    cur = fcf
    for year in range(1,6):
        gy = g + (mature-g)*(year-1)/4
        cur *= (1+gy)
        flows.append(cur)
    pv = sum(cf/((1+DISCOUNT_RATE)**i) for i,cf in enumerate(flows, start=1))
    terminal = flows[-1]*(1+TERMINAL_GROWTH)/(DISCOUNT_RATE-TERMINAL_GROWTH)
    pv_terminal = terminal/((1+DISCOUNT_RATE)**5)
    equity = pv + pv_terminal + cash - debt
    per_share = equity/shares
    return {
        "low":per_share*0.85,
        "mid":per_share,
        "high":per_share*1.15,
        "fcf_used":fcf,
    }


def load_snapshots():
    if not SNAPSHOT_FILE.exists():
        return []
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


def nearest_snapshot(ticker: str, as_of: str):
    target = pd.Timestamp(as_of).date()
    candidates = []
    for s in load_snapshots():
        if s.get("ticker") != ticker:
            continue
        try:
            d = pd.Timestamp(s["date"]).date()
            if d <= target:
                candidates.append((d,s))
        except Exception:
            pass
    if not candidates:
        return None
    return max(candidates, key=lambda x:x[0])[1]


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


def blended_fair(pe, dcf, growth):
    vals = []
    wts = []
    for name, obj in [("pe",pe),("dcf",dcf),("growth",growth)]:
        if obj and obj.get("mid"):
            vals.append(obj["mid"]*WEIGHTS[name])
            wts.append(WEIGHTS[name])
    if not wts:
        return None
    return sum(vals)/sum(wts)


def buy_zones(fair, technical_mid=None, sma200=None):
    if not fair:
        return None
    # Fundamental anchors.
    first = (fair*0.88, fair*0.94)
    core = (fair*0.78, fair*0.86)
    deep = (fair*0.68, fair*0.76)

    # Pull first/core zones toward nearby technical supports if close.
    anchors = [x for x in [technical_mid, sma200] if x and x > 0]
    if anchors:
        nearest = min(anchors, key=lambda x:abs(x-fair*0.9))
        if abs(nearest-fair*0.9)/fair < 0.15:
            width = fair*0.025
            first = (min(first[0], nearest-width), max(first[1], nearest+width))
    return {"first":first,"core":core,"deep":deep}


def money(x):
    return "N/A" if x is None or not math.isfinite(float(x)) else f"${x:,.2f}"


def pct(a,b):
    if a is None or b in (None,0):
        return None
    return (a/b-1)*100


def run(ticker, as_of=None):
    ticker = ticker.upper().strip()
    df = add_indicators(get_history(ticker, as_of))
    row = df.iloc[-1]
    trade_date = pd.Timestamp(df.index[-1]).date().isoformat()
    price = float(row["Close"])
    sma30 = fnum(row["SMA30"])
    sma50 = fnum(row["SMA50"])
    sma200 = fnum(row["SMA200"])
    vp = volume_profile_zone(df)

    historical = as_of is not None and pd.Timestamp(as_of).date() < date.today()

    pe = dcf = growth = None
    fair = None
    valuation_note = ""

    if historical:
        snap = nearest_snapshot(ticker, as_of)
        if snap:
            pe = snap.get("models",{}).get("pe")
            dcf = snap.get("models",{}).get("dcf")
            growth = snap.get("models",{}).get("growth")
            fair = snap.get("blended_fair_value")
            valuation_note = f"Using nearest saved valuation snapshot on/before {as_of}: {snap['date']}"
        else:
            valuation_note = (
                "No point-in-time valuation snapshot exists on/before this date. "
                "Technical comparison is valid, but historical fair value is intentionally left blank "
                "to avoid look-ahead bias."
            )
    else:
        f = get_live_fundamentals(ticker)
        pe = pe_model(ticker, f["forward_eps"])
        growth = growth_model(ticker, f["forward_eps"], f["earnings_growth"])
        dcf = dcf_model(ticker, f["fcf"], f["shares"], f["cash"], f["debt"])
        fair = blended_fair(pe, dcf, growth)
        valuation_note = "Live valuation uses current Yahoo Finance fundamentals and editable model assumptions."

    zones = buy_zones(fair, vp["mid"] if vp else None, sma200) if fair else None

    print("\n" + "="*72)
    print(f"{ticker}  |  price date: {trade_date}")
    print("="*72)
    print(f"Close:   {money(price)}")
    print(f"SMA30:   {money(sma30)}   distance: {pct(price,sma30):+.2f}%" if sma30 else "SMA30: N/A")
    print(f"SMA50:   {money(sma50)}   distance: {pct(price,sma50):+.2f}%" if sma50 else "SMA50: N/A")
    print(f"SMA200:  {money(sma200)}   distance: {pct(price,sma200):+.2f}%" if sma200 else "SMA200: N/A")
    if vp:
        print(f"1Y volume-density zone (approx.): {money(vp['low'])} - {money(vp['high'])}")

    print("\nValuation")
    print("-"*72)
    if pe: print(f"P/E model:      {money(pe['low'])} / {money(pe['mid'])} / {money(pe['high'])}")
    else: print("P/E model:      N/A")
    if dcf: print(f"DCF model:      {money(dcf['low'])} / {money(dcf['mid'])} / {money(dcf['high'])}")
    else: print("DCF model:      N/A")
    if growth: print(f"Growth model:   {money(growth['low'])} / {money(growth['mid'])} / {money(growth['high'])}")
    else: print("Growth model:   N/A")
    print(f"Blended fair:   {money(fair)}")
    if fair:
        print(f"Price vs fair:  {pct(price,fair):+.2f}%")
        print(f"Valuation state: {classify_price(price,fair)}")

    if zones:
        print("\nSuggested valuation zones (not trading advice)")
        print("-"*72)
        print(f"First-entry:    {money(zones['first'][0])} - {money(zones['first'][1])}")
        print(f"Core-buy:       {money(zones['core'][0])} - {money(zones['core'][1])}")
        print(f"Deep-value:     {money(zones['deep'][0])} - {money(zones['deep'][1])}")

    print("\nNotes")
    print("-"*72)
    print(valuation_note)
    print("Volume-density zone is an estimate from daily price/volume bars, not actual investor cost basis.")
    print("Fair value is a model output, not Investing.com's proprietary Fair Value.")
    print("="*72 + "\n")


def main():
    p = argparse.ArgumentParser(description="Magnificent Seven valuation + technical monitor")
    p.add_argument("ticker", nargs="?", help="AAPL MSFT GOOGL AMZN NVDA META TSLA")
    p.add_argument("--date", help="Historical date, YYYY-MM-DD")
    args = p.parse_args()

    ticker = args.ticker or input("Ticker (AAPL/MSFT/GOOGL/AMZN/NVDA/META/TSLA): ").strip()
    as_of = args.date
    if as_of is None:
        d = input("Date YYYY-MM-DD (press Enter for latest): ").strip()
        as_of = d or None
    run(ticker, as_of)


if __name__ == "__main__":
    main()
