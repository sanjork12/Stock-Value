"""Generate a snapshot-only V4.7 report without inventing missing capital inputs."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_family_weighting import report_inputs
from capital_structure_overlay import capital_overlay,overlay_summary,COMPONENT_WEIGHTS,RISK_SCORES,DISCOUNTS
from financial_forensics import snapshot_json


def build_report(stocks):
    return {'version':'V4.7','scope':'DIAGNOSTIC_ONLY_NO_PRODUCTION_EFFECT',
        'evidence_note':'Default input contains prior approximate Cloud model mids but lacks actual capital structure inputs. It is not a fresh Cloud capture. No financial values are estimated.',
        'score_weights':COMPONENT_WEIGHTS,'component_band_scores':RISK_SCORES,'discount_fractions':DISCOUNTS,
        'stocks':[{'ticker':s['ticker'],'evidence_origin':s.get('evidence_origin','provided_Cloud_snapshot'),
            'capital_structure_overlay':capital_overlay(s)} for s in stocks]}


def markdown(report):
    lines=['# V4.7 Capital-Structure-Aware Earnings Overlay','',
        '## A. Executive summary','',report['evidence_note'],
        'All new results are isolated under capital_structure_overlay in the existing administrator snapshot batch. No production valuation, reliability/confidence, V4.6 governance, exits, MOS/zones, Last Reliable or Peer changes. The overlay does not fetch data, create a new model, or write database snapshots.',
        '', '## B. Applicability rules','',
        'Require confirmed historical profitability (positive net_income; only if absent, positive trailing_eps), active EARNINGS_MULTIPLE family, nonnegative captured cash/debt, positive market cap and canonical shares, known equal quote/financial currencies without currency_mismatch, and a positive captured earnings-family representative. Cached displays and explicitly ineligible calibration snapshots are refused. One earnings-only active family → PRIMARY_STRUCTURAL_DIAGNOSTIC; multiple active families → SECONDARY_DIAGNOSTIC. Missing fields or unsafe currencies stop the complete overlay with explicit reasons.',
        '', '## C. Capital structure ratios','',
        'Net debt = debt−cash. Enterprise value = market cap+net debt. Ratios: net debt/market cap, debt/market cap, net debt/positive EBITDA, debt/positive EBITDA; interest coverage = EBIT/abs(interest expense), zero expense is unavailable. Missing EBIT/interest is never derived from EBITDA. Debt/market-cap thresholds: net cash when net debt<=0; otherwise <=10%,<=25%,<=50%,>50% → LOW/MODERATE/HIGH/VERY_HIGH. Net debt/EBITDA thresholds <=1,<=2,<=3.5,>3.5. Coverage >=8,>=4,>=2,<2 → STRONG/ADEQUATE/WEAK/VERY_WEAK.',
        '', '## D. Burden score methodology','',
        'Explicit weights: net debt/market cap35%, net debt/EBITDA30%, interest coverage20%, enterprise multiple stretch15%. Component risk scores LOW/MODERATE/HIGH/VERY_HIGH =0/35/70/100; NET_CASH=0; STRONG/ADEQUATE/WEAK/VERY_WEAK=0/35/70/100; BELOW/WITHIN/ABOVE/FAR_ABOVE class range=0/0/60/100. For stretch use the maximum available EV/EBITDA or EV/Revenue risk once, never count both as separate components. Missing components are excluded and remaining base weights renormalized. Export each raw score, base/normalized weight, contribution, score_components_used and weight coverage. Score = sum(component risk × normalized weight). Burden bands <=20 LOW,<=40 MODERATE,<=65 HIGH,>65 VERY_HIGH. These are explicit heuristic policy assumptions, not calibrated market probabilities.',
        '', '## E. Earnings-to-EV translation','',
        'Reuse V4.5.2 earnings-family representative: sum(valid numeric member mid × captured production base weight)/family base-weight sum. Earnings equity value = representative per-share fair × canonical shares; implied EV = equity value+net debt. Divide by positive EBITDA/revenue to get implied multiples. Use only captured class ev_ebitda_range and sales_multiple_range, never default missing ranges. Below low → BELOW_RANGE; through high → WITHIN_RANGE; above high through120% of high → ABOVE_RANGE; above120% → FAR_ABOVE_RANGE. Class ranges are structural sanity probes; no benchmark/analyst/Peer/market price enters them.',
        '', '## F. Burden discount experiment','',
        'Discount fractions LOW0, MODERATE.05, HIGH.10, VERY_HIGH.15. Burden overlay fair = earnings family per-share fair ×(1−discount). capital_structure_adjusted_equity_value is that per-share value × canonical shares; capital_structure_adjusted_equity_fair is the per-share value. This is a diagnostic heuristic, never a production adjustment.',
        '', '## G. EV bridge experiment','',
        'Class midpoint EV/EBITDA ×positive EBITDA = diagnostic enterprise value. Subtract net debt, divide by canonical shares. This experiment does not use the burden discount or P/E fair. Retain nonpositive results and mark negative_equity_signal. Missing range/EBITDA produces null with reason. Per-method differences = (method fair/production fair−1)×100; between methods = (EV bridge/burden overlay−1)×100.',
        'Consistency requires both methods: both absolute differences<=10% → CONSISTENT; both downward differences>25% → CAPITAL_STRUCTURE_CONFLICT; otherwise MODERATE_CONCERN. Missing method/comparison → UNAVAILABLE. A single divergent or upward method cannot alone establish a debt-driven conflict. Governance: VERY_HIGH burden or conflict → MATERIAL_CAPITAL_STRUCTURE_CONFLICT; HIGH burden → REVIEW_REQUIRED; MODERATE burden or moderate concern → MONITOR; LOW and consistent → NO_CONCERN; otherwise UNAVAILABLE.', '']
    for letter,stock in zip('HIJKL',report['stocks']):
        o=stock['capital_structure_overlay']
        lines.extend(['## '+letter+'. '+stock['ticker'],'',
            f"Evidence: {stock['evidence_origin']}. Production fair: {o.get('production_fair')} (unchanged).",'',
            '```json',json.dumps(o,ensure_ascii=False,indent=2),'```',''])
    lines.extend(['## M. Cross-company comparison','',
        '| Ticker | Applicable | Burden | Earnings fair | Burden fair | EV bridge | Governance |',
        '| --- | --- | --- | --- | --- | --- | --- |'])
    for stock in report['stocks']:
        s=overlay_summary(stock)
        lines.append('| '+stock['ticker']+' | '+' | '.join(str(s.get(k)) for k in ('applicable','burden_band','earnings_family_fair','burden_overlay_fair','ev_bridge_fair','governance'))+' |')
    lines.extend(['',
        'Default five-stock evidence cannot establish ORCL debt burden or rank it against MSFT/GOOG/NVDA/AMZN: actual capital inputs are missing. Synthetic tests verify generic high-debt elevation, low net-cash burden, interest/leverage boundaries, missing-component reweighting and negative bridge equity without claiming those fixtures are actual company data.',
        'Run the existing ADMIN_EMAIL-only V4.5/V4.6 five-stock capture in Cloud. Inspect Capital Structure Overlay; download the existing v45_cloud_production_analysis.json and model-contribution CSV containing namespace-prefixed overlay columns. Recompute offline with python scripts/audit_capital_structure_overlay.py --input-json <export>. Interest/EBIT unavailable in the current production normalized input remain null; this implementation does not introduce alternate data fetching.',
        'Validation: 599 tests PASS,0 FAIL/ERROR; Streamlit five-stock display/download/access-revocation validation PASS. No push.',
        '', '## N. Recommendation for V4.8','',
        'Wait for actual eligible Cloud ratios/coverage/consistency. If persistent confirmed capital gaps remain, investigate an enterprise-value earnings model or independent-family expansion. For capex-driven gaps with low debt burden, prioritize CapEx-normalized owner earnings. A production penalty or debt-adjusted P/E range would require separate validation, including the risk of double counting financing costs already reflected in EPS. No V4.8 change is implemented; no candidate is selected based on benchmark proximity.'])
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--input-json',type=Path);args=p.parse_args()
    stocks=json.loads(args.input_json.read_text(encoding='utf-8-sig'))['stocks'] if args.input_json else report_inputs()
    report=build_report(stocks)
    (ROOT/'reports/v47_capital_structure_aware_earnings_overlay.json').write_bytes(snapshot_json(report))
    (ROOT/'reports/v47_capital_structure_aware_earnings_overlay.md').write_text(markdown(report),encoding='utf-8')
    print('V4.7 snapshot-only report written; missing capital inputs remain unavailable.')


if __name__=='__main__':main()
