"""Diagnostic report from Cloud export, or explicitly labeled user observations."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model_family_governance import governance_audit,MODEL_FAMILIES,CORE_DRIVERS
from valuation_engine import build_profile
from financial_forensics import snapshot_json


def observed_baseline():
    # Report evidence only. Never imported by production valuation or UI.
    supplied={
        'GOOG':{'fair':253.81,'forward_pe':348.83,'growth_adjusted_pe':303.33,'normalized_fcf_dcf':139.72},
        'MSFT':{'fair':657.05,'forward_pe':686.64,'growth_adjusted_pe':615.61,'normalized_fcf_dcf':203.34,'outlier':'normalized_fcf_dcf'},
        'ORCL':{'fair':237.75,'forward_pe':241.98,'growth_adjusted_pe':230.98,'dcf_reason':'mostly_negative_fcf'},
        'NVDA':{'fair':358.45,'forward_pe':381.95,'growth_adjusted_pe':331.02,'dcf_reason':'fcf_conversion_too_low'},
        'AMZN':{'fair':290.44,'forward_pe':303.53,'growth_adjusted_pe':272.13,'dcf_reason':'capex_or_fcf_distortion'}}
    stocks=[]
    for ticker,data in supplied.items():
        models={name:{'mid':data[name],'valid':True,'applicable':True,'executed':True,'inputs':{}}
            for name in ('forward_pe','growth_adjusted_pe','normalized_fcf_dcf') if name in data}
        before=deepcopy(models)
        included=list(models)
        if data.get('outlier'):
            included.remove(data['outlier'])
            models[data['outlier']].update(valid=False,outlier=True,reason='outlier_vs_other_models')
        if data.get('dcf_reason'):
            models['normalized_fcf_dcf']={'valid':False,'applicable':False,'executed':False,'mid':None,'reason':data['dcf_reason']}
            before['normalized_fcf_dcf']=deepcopy(models['normalized_fcf_dcf'])
        base=build_profile(ticker,{}).model_weights
        total=sum(base[name] for name in included)
        stocks.append({'ticker':ticker,'source_status':'live','financials':{},
            'evidence_origin':'user_supplied_approximate_Cloud_model_observations',
            'missing_evidence':['forward_eps','trailing_eps','cash','debt','market_cap','exact_inputs_used'],
            'weight_evidence':'current source base weights normalized over user-reported included set; not a captured Cloud weight payload',
            'blend':{'fair':data['fair'],'included':included,'models':models,'weights_used':{name:base[name]/total for name in included}},
            'models_before_outlier':before})
    return stocks


def build_report(stocks):
    return {'version':'V4.5.1','scope':'DIAGNOSTIC_ONLY_NO_PRODUCTION_CHANGES',
        'model_family_map':MODEL_FAMILIES,'weighted_core_drivers':CORE_DRIVERS,
        'stocks':[{'ticker':stock['ticker'],'reported_fair':stock.get('fair_value',(stock.get('blend') or {}).get('fair')),
            'evidence_origin':stock.get('evidence_origin','provided_Cloud_snapshot'),
            'weight_evidence':stock.get('weight_evidence','recorded_production_normalized_weights'),
            'missing_evidence':stock.get('missing_evidence',[]),
            **governance_audit(stock)} for stock in stocks],
        'recommended_v452_experiments':[
            'Offline family-level versus model-level weighting experiment, with the original blend frozen as control.',
            'Test correlation-adjusted evidence weighting separately from production reliability.',
            'Review family-disagreement reliability penalties in a sandbox; preserve the current outlier decision as baseline.',
            'Validate capital-structure-aware earnings diagnostics using actual debt/cash/share inputs.',
            'Evaluate capex-cycle-normalized cashflow scenarios without relaxing existing applicability guards.']}


def markdown(report):
    lines=['# V4.5.1 Correlation & Cross-Family Governance Audit','',
        '## A. Executive summary','',
        'Governance only: no production valuation, weights, outlier, confidence, eligibility or reliability changes. Default report replays user-supplied approximate Cloud model observations, not a new Cloud API run. Exact normalized weights are reconstructed from current source and the supplied included set when a full Cloud export is absent. EPS ratios and debt metrics remain unknown without original inputs.',
        '', '## B. Model family map','']
    lines.extend(f'- {name}: {family}' for name,family in MODEL_FAMILIES.items())
    lines.extend(['','## C. Dependency methodology','',
        'Weighted core-driver Jaccard = sum(min(driver weights)) / sum(max(driver weights)). Drivers and weights are explicit in model_family_governance.py and the JSON. Currency/class context is counted in shared declared inputs, not as a core driver. PE pair shares EPS_BASIS(4) and EARNINGS_MULTIPLE_POLICY(2); Growth PE adds SUSTAINABLE_GROWTH(1): score 6/7 = 0.857143, HIGH_DEPENDENCY. Forward PE versus DCF has no shared core driver (score 0, LOW). DCF versus EV/EBITDA shares capital bridge/shares (6/14 = 0.428571, MODERATE). This is a structural descriptor, not Pearson correlation or measured market-price covariance.',
        '', 'Thresholds: >=0.70 HIGH; >=0.40 and <0.70 MODERATE; <0.40 LOW. Recorded model inputs accompany declared dependency sets so missing observations remain visible.',
        '', '## D. Effective independent evidence methodology','',
        'Each active family first model contributes 1.0. Additional same-family models contribute 0.25/0.50/0.75 for HIGH/MODERATE/LOW dependency against the most-overlapping prior family member, in deterministic model-id order. This is a heuristic evidence count, not sample size. Different first families contribute 1.0 each; any cross-family overlaps remain explicit in pair diagnostics. Production model count and weights stay unchanged.',
        '', 'Family concentration sums actual normalized production weights, never reweights them. >=0.75 HIGH; [0.60,0.75) MODERATE; <0.60 DIVERSIFIED. Cross-family representatives are unweighted medians of successful numeric models per family, including later outlier exclusions. Spread = (max−min)/median ×100. Pairwise uses pair mean denominator. <=20% CONSISTENT; (20%,40%] MODERATE; >40% CROSS_FAMILY_DISAGREEMENT.', ''])
    sections={'GOOG':'E. GOOG result','MSFT':'F. MSFT result','ORCL':'G. ORCL result','NVDA':'H. NVDA result','AMZN':'I. AMZN result'}
    for stock in report['stocks']:
        lines.extend(['## '+sections.get(stock['ticker'],stock['ticker']),'',
            f"Classification: {stock['governance_classification']}; review: {stock['governance_review_status']}.",'',
            f"Included count {stock.get('model_count_included')}; effective independent count {stock.get('effective_independent_model_count')}; active families {stock.get('active_families')}; executed families {stock.get('executed_families')}.",'',
            f"Family weights: {stock.get('family_weight_concentration')}. Cross-family status: {stock.get('cross_family_status')}; spread: {stock.get('cross_family_spread_pct')}%.",'',
            f"Family representatives: {stock.get('family_representatives')}.",'',
            f"Growth overlap: {stock.get('growth_overlap_risk')}; EPS ratio: {stock.get('forward_to_trailing_eps_ratio')}; reasons: {stock.get('growth_overlap_reasons')}.",'',
            f"Capital structure: {stock.get('capital_structure')}; flags: {stock.get('capital_structure_flags')}.",'',
            f"Outlier review: {stock.get('outlier_governance_review')}. Production exclusion remains unchanged.",'',
            f"Summary: {stock.get('governance_summary')}. Input/weight scope: {stock['weight_evidence']}.",''])
    lines.extend(['## J. Cross-family disagreement matrix','',
        '| Ticker | Active families | Effective count | Cross-family status | Spread % |',
        '| --- | --- | ---: | --- | ---: |'])
    for stock in report['stocks']:
        lines.append(f"| {stock['ticker']} | {', '.join(stock.get('active_families',[]))} | {stock.get('effective_independent_model_count')} | {stock.get('cross_family_status')} | {stock.get('cross_family_spread_pct')} |")
    lines.extend(['','## K. Growth overlap matrix','',
        'Shared active PE pair alone => MODERATE. Forward/trailing ratio >1.5 plus active HIGH_DEPENDENCY PE pair with the same actual forward_eps recorded and no proxy use => HIGH. A high EPS ratio alone => MODERATE; otherwise LOW. A growth-adjusted model alone never causes HIGH. Active cashflow evidence is separately recorded and does not cancel a confirmed shared-EPS step-up. In default observation replay all EPS ratios are unknown, so NVDA HIGH cannot be numerically confirmed until Cloud inputs are exported.',
        '', '## L. Capital-structure flags','',
        'Positive net debt and only EARNINGS_MULTIPLE active => CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS. This means no explicit EV/equity bridge in active primitives, not that economic leverage has no effect on EPS. ORCL cash/debt values were not supplied; its actual flag remains pending. Unknown metrics produce no fabricated net-debt flag.',
        '', '## M. Outlier governance findings','',
        'MSFT DCF remains in cross-family representatives despite its unchanged production exclusion. CROSS_FAMILY_SIGNAL_SUPPRESSED requires an executed numeric model, outlier_vs_other_models as the exclusion reason, and a family distinct from the active dominant family. Other invalid/applicability failures do not qualify. AMZN is numerically stable within the supplied PE family but concentrated; it is not a healthy independent multi-model anchor.',
        '', '## N. Recommended V4.5.2 experiments','']+['- '+x for x in report['recommended_v452_experiments']]+['',
        'No experiments were implemented. Benchmarks are absent from all governance calculations. Use `python scripts/audit_cross_family_governance.py --input-json v45_cloud_production_analysis.json` for exact captured inputs/weights. The Cloud V4.5 page also exports this governance automatically.',
        '', 'Full test results and local commit hash are in the completion message. No push.',''])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-json',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reports')
    args=parser.parse_args()
    stocks=json.loads(args.input_json.read_text(encoding='utf-8-sig'))['stocks'] if args.input_json else observed_baseline()
    report=build_report(stocks);args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'v451_correlation_cross_family_governance.json').write_bytes(snapshot_json(report))
    (args.output_dir/'v451_correlation_cross_family_governance.md').write_text(markdown(report),encoding='utf-8')
    print('V4.5.1 diagnostic reports written; no valuation or storage changes.')


if __name__=='__main__':main()
