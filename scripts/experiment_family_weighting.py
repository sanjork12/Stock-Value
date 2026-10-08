"""Offline experimental report. Input models are never revalued or persisted."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.audit_cross_family_governance import observed_baseline
from valuation_engine import build_profile
from model_family_governance import governance_audit
from experimental_family_blend import family_blend_experiment,experiment_summary
from financial_forensics import snapshot_json

BENCHMARKS={'GOOG':345,'MSFT':544,'ORCL':180,'NVDA':300,'AMZN':285}


def report_inputs():
    stocks=observed_baseline()
    for stock in stocks:
        stock['profile_assumptions']={'weights':build_profile(stock['ticker'],{}).model_weights}
    return stocks


def build_report(stocks,benchmarks=None):
    results=[]
    for stock in stocks:
        results.append({'ticker':stock['ticker'],'evidence_origin':stock.get('evidence_origin','provided_Cloud_export'),
            'weight_evidence':stock.get('weight_evidence','captured production base weights'),
            'experimental_family_blend':family_blend_experiment(stock)})
    # All experiments have finished before benchmarks are even looked up.
    refs=BENCHMARKS if benchmarks is None else benchmarks
    comparisons=[]
    for stock in results:
        experiment=stock['experimental_family_blend'];reference=refs.get(stock['ticker'])
        mids={'production':experiment.get('production_fair')}
        mids.update({letter:experiment.get(key,{}).get('fair') for letter,key in (
            ('strategy_A','strategy_a_current_weight_aggregated'),('strategy_B','strategy_b_equal_family'),
            ('strategy_C','strategy_c_evidence_adjusted'))})
        comparisons.append({'ticker':stock['ticker'],'benchmark':reference,
            'signed_error_pct':{key:(mid/reference-1)*100 if mid is not None and reference else None for key,mid in mids.items()}})
    return {'version':'V4.5.2','scope':'EXPERIMENT_ONLY_NO_PRODUCTION_ACTIVATION','stocks':results,
        'recommended_v453_experiments':[
            'Offline family-level versus correlation-adjusted weighting on complete eligible captures; retain production as a frozen control.',
            'Test a separate family-disagreement reliability penalty in a sandbox, never by silently dropping minority cashflow evidence.',
            'Evaluate class-specific independent-family minimums without relaxing existing applicability.',
            'Validate capital-structure-aware earnings overlays for debt-heavy single-family cases.',
            'Study capex-normalized owner earnings as a distinct model with documented cashflow basis.'],
        'post_hoc_only':comparisons}


def markdown(report):
    lines=['# V4.5.2 Family-Level Weighting Experiment','',
        '## A. Executive summary','',
        'Pure experimental namespace; no production valuation, confidence, reliability, weights, outlier, applicability, fallback, Peer or zones changes. Default report reuses user-provided approximate Cloud mids and source-derived base weights from V4.5.1. It is not a new Cloud capture. Low/high intervals, EPS ratios and capital inputs absent from that evidence remain unknown.',
        '', '## B. Family aggregation method','',
        'Reuse V4.5.1 family mapping and successful model records, including valid pre-outlier numeric models. No inapplicable/invalid-input model is restored. Family mid/low/high are sums of each captured model value times its positive captured base weight divided by the family base-weight sum. Missing intervals remain null. Missing captured base weights abort the experiment rather than invent equal weights. Correlation-adjusted family mid equals family mid; dependency changes evidence strength only.',
        '', '## C. Strategy A — CURRENT_WEIGHT_AGGREGATED','',
        'Family raw weight = sum of base weights of experimentally retained members; normalize across executed families. This reproduces production only when the same candidate set participates. MSFT restores DCF, so A is a restored-candidate control, not a promise to reproduce the production outlier exclusion.',
        '', '## D. Strategy B — EQUAL_FAMILY','',
        'Each retained family receives 1 / family_count, regardless of how many correlated members it has.',
        '', '## E. Strategy C — EVIDENCE_ADJUSTED','',
        'Raw family weight = family base-weight sum × evidence strength × governance modifier. Reuse same-family increments from V4.5.1: first member 1; HIGH additional 0.25, MODERATE 0.50, LOW 0.75. Dependency penalty = 1 − effective/raw count. Strength: effective >=1.75 →1.0; [1.25,1.75) →0.85; <1.25 →0.70. Conflict modifier 0.85 applies uniformly to every family (otherwise 1.0); it cancels on normalized weights and never suppresses minority evidence. No benchmark enters any formula.', '']
    labels={'GOOG':'F. GOOG','MSFT':'G. MSFT','ORCL':'H. ORCL','NVDA':'I. NVDA','AMZN':'J. AMZN'}
    for stock in report['stocks']:
        exp=stock['experimental_family_blend'];summary=experiment_summary(stock)
        lines.extend(['## '+labels.get(stock['ticker'],stock['ticker']),'',
            f"Evidence: {stock['evidence_origin']}; weights: {stock['weight_evidence']}.",'',
            f"Production {summary['production_fair']}; A {summary['A_fair']}; B {summary['B_fair']}; C {summary['C_fair']}.",'',
            f"Differences (%): A {summary['A_difference_pct']}, B {summary['B_difference_pct']}, C {summary['C_difference_pct']}.",'',
            f"Sensitivity: {summary['family_weighting_sensitivity']}; governance: {summary['family_weighting_governance']}.",'',
            f"Families: {exp.get('family_count')}; representatives: { {key:value['family_mid'] for key,value in exp.get('family_representatives',{}).items()} }.",'',
            f"Effective counts: {exp.get('family_effective_model_count')}; evidence strengths: {exp.get('family_evidence_strength')}.",'',
            f"Suppressed family: {exp.get('suppressed_family')}; experimentally restored: {exp.get('experimental_restored')}. Production exclusion unchanged.",''])
    lines.extend(['## K. Sensitivity comparison','',
        '| Ticker | Production | A | B | C | Maximum sensitivity |','| --- | ---: | ---: | ---: | ---: | --- |'])
    for stock in report['stocks']:
        s=experiment_summary(stock)
        lines.append(f"| {s['ticker']} | {s['production_fair']} | {s['A_fair']} | {s['B_fair']} | {s['C_fair']} | {s['family_weighting_sensitivity']} |")
    lines.extend(['', 'Bands use absolute strategy difference versus production: <=10% LOW; (10%,25%] MODERATE; >25% HIGH. Aggregate sensitivity is the maximum absolute difference over A/B/C. GOOG need not be HIGH: observed numbers and formulas decide, not the initial hypothesis. Small single-family differences against rounded supplied fair are rounding, not diversification.',
        '', '## L. Suppressed-family findings','',
        'MSFT cashflow DCF is restored in all three experiments because it was an executable cross-family outlier signal. No production exclusion is reversed. Family conflict flag and conflict_preserving_blend remain explicit. No fake family is created for ORCL/NVDA/AMZN.',
        '', '## M. Structural recommendations','',
        'Conflict => CROSS_FAMILY_CONFLICT_REQUIRES_REVIEW. Single family => SINGLE_FAMILY_LIMITATION. Moderate disagreement or high strategy sensitivity => FAMILY_LEVEL_BLEND_NEEDS_REVIEW. Multiple-family moderate sensitivity without conflict => FAMILY_LEVEL_BLEND_PROMISING; otherwise NO_ACTION. These are diagnostic recommendations, never production eligibility changes.',
        '', 'Family weighting cannot repair missing capital-structure representation or cashflow applicability. AMZN is numerically stable but concentrated. A HIGH growth-overlap signal on actual NVDA inputs recommends a family confidence cap only; the experiment mid is unchanged. The supplied observations lack the EPS ratio, so that recommendation cannot be asserted from the default report.',
        '', '## N. V4.5.3 proposal','']+['- '+x for x in report['recommended_v453_experiments']]+['',
        'No V4.5.3 change was implemented. To recompute from exact Cloud inputs: `python scripts/experiment_family_weighting.py --input-json v45_cloud_production_analysis.json`. Degraded/cached calibration inputs are refused. Full test results and local commit hash are supplied in the completion message. No push.',
        '', '## POST-HOC ONLY — signed error versus external reference',''])
    for row in report['post_hoc_only']:
        lines.append(f"- {row['ticker']}: benchmark {row['benchmark']}; errors (%) {row['signed_error_pct']}.")
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-json',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reports');args=parser.parse_args()
    stocks=json.loads(args.input_json.read_text(encoding='utf-8-sig'))['stocks'] if args.input_json else report_inputs()
    report=build_report(stocks);args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'v452_family_level_weighting_experiment.json').write_bytes(snapshot_json(report))
    (args.output_dir/'v452_family_level_weighting_experiment.md').write_text(markdown(report),encoding='utf-8')
    print('Experimental report written; no production or database updates.')


if __name__=='__main__':main()
