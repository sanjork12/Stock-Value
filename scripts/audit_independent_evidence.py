"""Offline V4.5.3 report; no data fetch, valuation execution or storage writes."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_family_weighting import report_inputs
from experimental_family_blend import family_blend_experiment
from independent_evidence_governance import independent_evidence_audit
from financial_forensics import snapshot_json


def build_report(stocks):
    return {'version':'V4.5.3','scope':'DIAGNOSTIC_GOVERNANCE_ONLY',
        'evidence_note':'Default input replays approximate supplied Cloud observations, not a new Cloud execution. Missing EPS/capital inputs remain unknown.',
        'stocks':[{'ticker':s['ticker'],'evidence_origin':s.get('evidence_origin','provided_Cloud_export'),
            'experimental_family_blend':s.get('experimental_family_blend') or family_blend_experiment(s),
            'independent_evidence_governance':independent_evidence_audit(s)} for s in stocks],
        'v46_recommendations':[
            'Consider reliability-only cross-family conflict governance after eligible Cloud validation; do not change fair.',
            'Evaluate an independent-family minimum for precise confidence and correlation-aware evidence counts in a sandbox.',
            'Investigate a capital-structure-aware earnings overlay using verified debt/cash inputs.',
            'Research a separate CapEx-normalized owner earnings model with documented normalization.'],
        'production_activation':'NONE'}


def markdown(report):
    lines=['# V4.5.3 Cross-Family Conflict Preservation','',
        '## A. Executive summary','',report['evidence_note'],
        'Production fair, reliability, confidence, zones, weights, outliers, Peer and Last Reliable are unchanged. All signals are diagnostic namespace outputs.',
        '', '## B. Active vs observed family framework','',
        'Reuse V4.5.1 mapping/dependencies and successful numeric family records. Active = observed model members included in production blend. Observed = applicable, successfully executed numeric valuation signals, including outlier-only exclusions. Invalid input, non-applicable, failed execution and null/nonfinite mids are not evidence. Independent family count equals observed family count; this is a structural family count, not proof of statistical independence.',
        '', '## C. Suppression governance','',
        'Only exact outlier_vs_other_models exclusions of successful numeric models count. A fully absent active family is independent-family suppression; >=2 absent families is MULTIPLE_FAMILIES_SUPPRESSED. A removed member of a still-active family is SAME_FAMILY_MODEL_SUPPRESSED. No production exclusion is reversed.',
        '', '## D. Independent evidence framework','',
        'Reuse active effective independent count from V4.5.1. Also report observed effective count separately using its dependency increments; suppressed signals cannot upgrade active confidence. Priority: zero observed → INSUFFICIENT; >=2 observed and exactly one active → DIVERSIFIED_BUT_SUPPRESSED; >=2 observed and active effective >=2 → DIVERSIFIED_EVIDENCE; one observed and effective >=1.5 → CONCENTRATED_MULTI_MODEL; one observed below1.5 → WEAKLY_INDEPENDENT_EVIDENCE; remaining incomplete configurations → INSUFFICIENT. Dominance requires one active family, >=2 included numeric members and a HIGH_DEPENDENCY pair.', '']
    for letter,s in zip('EFGHI',report['stocks']):
        g=s['independent_evidence_governance'];e=s['experimental_family_blend']
        lines.extend(['## '+letter+'. '+s['ticker'],'',
            f"Evidence origin: {s['evidence_origin']}. Production fair: {e.get('production_fair')}.",'',
            '```json',json.dumps(g,ensure_ascii=False,indent=2),'```',''])
    lines.extend(['## J. Structural gaps','',
        'Capital structure gap requires the existing CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS flag (verified positive net debt and earnings-only active evidence). Forecast-growth gap requires actual HIGH growth_overlap_risk and no observed cashflow family. CapEx gap requires exact capex_or_fcf_distortion reason and no observed cashflow family. No ticker mapping. Default ORCL capital inputs and NVDA EPS ratio are missing: their expected additional gaps cannot be asserted. AMZN CapEx gap is directly supported by its observed applicability reason.',
        '', '## K. Suppression materiality','',
        'Only independent-family suppression enables this metric: signed difference = (production fair / Strategy C − 1) ×100, using the diagnostic reference as denominator. This differs explicitly from V4.5.2 strategy sensitivity, which uses production as denominator. Absolute difference <=10% LOW, (10%,25%] MODERATE, >25% HIGH. Missing Strategy C → UNAVAILABLE; no suppression → NOT_APPLICABLE. Strategy C is a conflict-preserving diagnostic reference, not recommended production valuation. A/B/C remain intact. No benchmark is an input.',
        '', '## L. Production readiness matrix','',
        '| Ticker | Active / observed | Suppression | Materiality | Dependency | Readiness | Hypothetical action |',
        '| --- | --- | --- | --- | --- | --- | --- |'])
    for s in report['stocks']:
        g=s['independent_evidence_governance']
        lines.append('| '+s['ticker']+' | '+str(g.get('active_family_count'))+' / '+str(g.get('observed_family_count'))+' | '+' | '.join(str(g.get(k)) for k in ('family_suppression_status','suppression_materiality','production_fair_dependency','structural_valuation_readiness','hypothetical_guard_action'))+' |')
    lines.extend(['',
        'Readiness priority: suppressed observed cross-family disagreement → CROSS_FAMILY_CONFLICT_SUPPRESSED; >=2 active conflicting families → ACCEPTABLE_WITH_CONFLICT; diversified sufficient active evidence → ROBUST; otherwise gaps → CONCENTRATED_WITH_STRUCTURAL_GAP, else CONCENTRATED. Zero observed evidence has null readiness/dependency rather than a fabricated positive classification. Preservation required is independent suppression + >=2 observed + existing CROSS_FAMILY_DISAGREEMENT. Dependency SUPPRESSED_CROSS_FAMILY_CONFLICT additionally requires HIGH materiality.',
        '', '## M. Recommendation for V4.6','']+['- '+r for r in report['v46_recommendations']]+['',
        'Worth investigating production governance only after exact eligible Cloud captures confirm these signals. None activated. Admin export includes these fields under independent_evidence_governance and retains V4.5.2 A/B/C. Existing access and read-only storage boundaries are reused.'])
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-json',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reports');args=parser.parse_args()
    stocks=json.loads(args.input_json.read_text(encoding='utf-8-sig'))['stocks'] if args.input_json else report_inputs()
    report=build_report(stocks);args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'v453_cross_family_conflict_preservation.json').write_bytes(snapshot_json(report))
    (args.output_dir/'v453_cross_family_conflict_preservation.md').write_text(markdown(report),encoding='utf-8')
    print('V4.5.3 diagnostic report written; no production activation.')


if __name__=='__main__':main()
