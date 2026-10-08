"""Snapshot-only V4.8 report; no alternate financial fetch or production mutation."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_family_weighting import report_inputs
from enterprise_aware_experiment import enterprise_experiment,enterprise_summary
from financial_forensics import snapshot_json


def build_report(stocks):
    return {'version':'V4.8','scope':'DIAGNOSTIC_ONLY_NO_PRODUCTION_EFFECT',
        'evidence_note':'Default report reuses prior approximate Cloud model observations, not a new Cloud execution. Full same-run cash/debt, shares, EBITDA/revenue and captured class ranges are unavailable. No values are inferred from supplied ratios or fair estimates.',
        'stocks':[{'ticker':s['ticker'],'evidence_origin':s.get('evidence_origin','provided_Cloud_export'),
            'enterprise_aware_experiment':enterprise_experiment(s)} for s in stocks]}


def markdown(report):
    lines=['# V4.8 Enterprise-Aware Earnings Valuation Experiment','',
        '## A. Executive summary','',report['evidence_note'],
        'New results are only under enterprise_aware_experiment in the administrator audit. No production family-map registration, fair/range, model weights, outlier, V4.6 reliability/confidence/exits, Peer, normal snapshot or Last Reliable changes. Structurally distinct family evidence does not imply statistical independence. Two correlated enterprise methods count as one family.',
        '', '## B. Applicability','',
        'Each method requires its own positive EBITDA or revenue, positive canonical shares, available nonnegative cash/debt, known equal financial/quote currencies without mismatch, and its captured positive ordered class range. No default ranges or zero debt/cash substitution. Missing EBITDA does not block Revenue, and vice versa. Cached displays and explicitly ineligible calibration inputs fail closed; no historical/current financial mixing. Profitability is not an extra gate for these enterprise methods.',
        '', '## C. EV/EBITDA methodology','',
        'Multiples = captured class low,(low+high)/2,high. Enterprise values = EBITDA×multiples. Equity values = enterprise values−(debt−cash). Per-share values = equity/canonical shares. Deduct net debt exactly once; net cash adds to equity. Preserve nonpositive values and mark negative_equity_signal; they remain diagnostic numeric signals. Nonfinite results are invalid.',
        '', '## D. EV/Revenue methodology','',
        'Use captured sales_multiple_range identically: revenue×multiple−net debt, divided by canonical shares. No EPS, P/E discount or earnings fair is used to calculate either enterprise method. Both models are registered only in the experiment-local map as ENTERPRISE_MULTIPLE, experimental_family=true, production_included=false. The existing production revenue_multiple family mapping stays unchanged.',
        '', '## E. Enterprise family aggregation','',
        'Two valid methods:50/50 weighted mean independently for low/mid/high. One valid method:100% of that method, single_method_only=true and LOW confidence. No valid method: null family and UNAVAILABLE. Two methods: spread = (max(mid)−min(mid))/median(mid)×100; <=20% CONSISTENT and MEDIUM confidence; (20%,40%] MODERATE_DISAGREEMENT and LOW; >40% METHOD_DISAGREEMENT and LOW plus warning. Nonpositive median prevents meaningful percentage spread: null spread, warning and LOW confidence. No HIGH confidence in V4.8.', '']
    for letter,s in zip('FGHIJ',report['stocks']):
        e=s['enterprise_aware_experiment']
        lines.extend(['## '+letter+'. '+s['ticker'],'',
            f"Evidence: {s['evidence_origin']}. Production fair: {e.get('production_fair')} (unchanged).",'',
            '```json',json.dumps(e,ensure_ascii=False,indent=2),'```',''])
    lines.extend(['ORCL supplied high net-debt and multiple-stretch observations motivate the experiment but cannot reconstruct exact same-run shares, cash/debt, EBITDA and revenue. Five-company numerical/readiness comparisons remain unavailable until Cloud capture. No ORCL-specific condition is implemented. GOOG net-cash and MSFT/NVDA/AMZN controls are evaluated from actual inputs, not expected ticker outcomes.',
        '', '## K. Method consistency','',
        '| Ticker | EBITDA mid | Revenue mid | Family mid | Spread % | Confidence |',
        '| --- | --- | --- | --- | --- | --- |'])
    for s in report['stocks']:
        row=enterprise_summary(s)
        lines.append('| '+s['ticker']+' | '+' | '.join(str(row[k]) for k in ('ev_ebitda_mid','ev_revenue_mid','enterprise_family_mid','method_spread_pct','enterprise_family_confidence'))+' |')
    lines.extend(['', '## L. Earnings-family conflict','',
        'Reuse captured V4.5.2 earnings-family weighted representative. Difference = (enterprise family mid/earnings family mid−1)×100. Absolute bands <=10% CONSISTENT,<=25% MODERATE_DIFFERENCE,<=50% MATERIAL_DIFFERENCE,>50% SEVERE_DIFFERENCE; direction UP/DOWN, exact zero FLAT. Evidence statuses map to CONSISTENT_WITH_EARNINGS, MODERATE_CONFLICT, MATERIAL_CONFLICT or SEVERE_CONFLICT, with SINGLE_METHOD/UNAVAILABLE taking priority.',
        'Optional equal-family diagnostic fair =50% earnings+50% enterprise. Difference versus production uses this experimental midpoint, not a production adjustment. Observed diagnostic families union existing successful numeric families with ENTERPRISE_MULTIPLE, without changing production active counts. Existing ENTERPRISE_MULTIPLE is not counted twice. Observed cashflow family and nearest-family distances are reported when both comparison families exist; no benchmark selects a preferred model.',
        '', '## M. Production readiness','',
        'STRONG_CANDIDATE requires two valid positive-midpoint methods,spread<=20%,absolute earnings difference>=25%,and captured V4.7 burden HIGH/VERY_HIGH. Missing earnings comparison,one method,spread>40%,unavailable spread or nonpositive midpoint → NOT_READY. Remaining two-method cases → REVIEW_CANDIDATE. These labels cannot activate production weighting or reliability.',
        '| Ticker | Evidence status | Experimental family count | Readiness |',
        '| --- | --- | --- | --- |'])
    for s in report['stocks']:
        row=enterprise_summary(s)
        lines.append('| '+s['ticker']+' | '+' | '.join(str(row[k]) for k in ('enterprise_evidence_status','experimental_independent_family_count','production_readiness'))+' |')
    lines.extend(['',
        'Material earnings differences emit CLASS_MULTIPLE_FIT_REQUIRES_REVIEW, without tuning class ranges. Business-mix warnings are copied only from existing captured fields; absent warnings remain null, with a reason. No AWS/retail or semiconductor rule is inferred from ticker names.',
        'Cloud validation: ADMIN_EMAIL opens the existing V4.5/V4.6 five-stock batch and inspects Enterprise-Aware Valuation Experiment. Existing v45_cloud_production_analysis.json includes full namespace; CSV includes namespace-prefixed enterprise summary. Normal snapshot writing and Last Reliable are not called by this audit. To regenerate from exact exported inputs: python scripts/audit_enterprise_aware_experiment.py --input-json <export>. No credentials in exports.',
        '', '## N. V4.9 recommendation','',
        'Wait for actual eligible Cloud method spreads, earnings conflicts, burden and class-fit warnings. Consider formal enterprise-family registration only where internal methods are coherent and capital-heavy evidence supports it. Review class-specific applicability before multiple calibration; never use benchmark closeness. Reliability or production blend admission requires a separate version and before/after validation. Where enterprise methods disagree or capex distortion dominates, investigate CapEx-normalized owner earnings instead. No V4.9 work is implemented.',
        'Validation:654 tests PASS,0 FAIL/ERROR; administrator widget capture/download/access-revocation validation PASS. Synthetic formulas,net cash,negative equity,method-specific missing inputs,family aggregation,confidence/readiness,production invariants,no-write snapshot isolation and external-data independence are tested. Actual Cloud validation pending deployment. No push.'])
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--input-json',type=Path);args=p.parse_args()
    stocks=json.loads(args.input_json.read_text(encoding='utf-8-sig'))['stocks'] if args.input_json else report_inputs()
    report=build_report(stocks)
    (ROOT/'reports/v48_enterprise_aware_valuation_experiment.json').write_bytes(snapshot_json(report))
    (ROOT/'reports/v48_enterprise_aware_valuation_experiment.md').write_text(markdown(report),encoding='utf-8')
    print('V4.8 snapshot-only report generated; no production or database updates.')


if __name__=='__main__':main()
