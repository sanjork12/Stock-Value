"""V4.6 offline policy report, no requests, database access or invented Cloud scores."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_family_weighting import report_inputs
from independent_evidence_governance import independent_evidence_audit
from production_reliability_governance import evaluate_structural_governance,VERSION,PENALTIES,CEILINGS
from financial_forensics import snapshot_json


def build_report(stocks):
    rows=[]
    for s in stocks:
        blend=s.get('blend') or {}
        actual=s.get('reliability_governance_audit') or blend.get('reliability_governance_audit')
        if actual:
            rows.append({'ticker':s['ticker'],'evidence':'captured_production_audit',**actual})
        else:
            g=independent_evidence_audit(s)
            policy=evaluate_structural_governance(g)
            fair=s.get('production_analysis_fair',blend.get('fair'))
            rows.append({'ticker':s['ticker'],'evidence':s.get('evidence_origin','snapshot_policy_preview'),
                'fair_before':fair,'fair_after':fair,'fair_unchanged':True,
                'reliability_before':None,'reliability_after':None,'confidence_before':None,'confidence_after':None,
                'precise_exit_before':None,'precise_exit_after':None,'structural_governance':policy,
                'validation_note':'Policy preview only; no original reliability/exit records. Exact before/after requires the Cloud audit.'})
    return {'reliability_governance_version':VERSION,'production_fair_policy':'UNCHANGED',
        'evidence_note':'Default report reuses approximate prior Cloud model observations, not a new Cloud execution. No missing capital/EPS/reliability values are invented.',
        'penalties':PENALTIES,'ceilings':CEILINGS,'stocks':rows}


def markdown(report):
    lines=['# V4.6 Production Reliability Governance','',
        '## A. Executive summary','',report['evidence_note'],
        'Production analysis_service applies the policy after unchanged valuation, MOS and buy-zone construction, before result assembly and snapshot persistence. valuation_engine model execution/blend math stays unchanged. Reuse V4.5.3 independent_evidence_audit; no second family mapping or benchmark-based rule.',
        '', '## B. Governance severity rules','',
        'Highest matching severity wins: suppressed conflict + HIGH materiality → CRITICAL; suppressed conflict + MODERATE → HIGH; other suppressed conflicts, unsuppressed cross-family disagreement, structural gaps or single-active-family HIGH growth overlap → MODERATE; single active family → LOW; otherwise NONE. Ticker names and external references are never policy inputs.',
        '', '## C. Reliability penalty rules','',
        'NONE/LOW/MODERATE/HIGH/CRITICAL primary deltas = 0/−5/−10/−15/−20, defined centrally. At most one secondary −5: single-family HIGH growth overlap first, otherwise structural gap when below CRITICAL. If the primary already charges that same driver, suppress the secondary. Total structural cap −25. Existing penalty list is retained unchanged; structural_reliability_penalties is separate. Apply after existing score; clamp 0–100. Missing original score remains null.',
        '', '## D. Confidence ceiling rules','',
        'NONE/LOW/MODERATE/HIGH/CRITICAL severity ceilings = NONE/HIGH/MEDIUM/MEDIUM/LOW. Recheck unchanged score thresholds 85 and65, and take the minimum of existing confidence, governed-score confidence and structural ceiling. Never upgrade LOW or UNAVAILABLE. Original model version is preserved; reliability_governance_version is independently v4.6.',
        '', '## E. Precise-exit blocking rules','',
        'HIGH/CRITICAL always block. MODERATE blocks for single active family, significant cross-family disagreement or nonempty gaps. LOW/NONE add no block. Re-evaluate existing exit reliability with governed score/confidence and retain original eligibility as an AND gate. The existing exit display guard nulls precise prices when blocked; it never unlocks a previously blocked profile. MOS and buy-zone formulas/ranges remain unchanged.',
        '', '## F. Double-count protection','',
        'One primary + at most one distinct secondary. A structural gap used as primary cannot charge again as secondary. A forecast-only gap cannot be secondary to the same high-growth primary. HIGH/VERY HIGH dispersion plus cross-family disagreement sets overlap_detected and documents suppression of a repeated conflict secondary. A primary structural conflict penalty remains intentional and separate. All rejected secondary codes/reasons are exported in penalty_overlap_guard.', '']
    for letter,s in zip('GHIJK',report['stocks']):
        g=s['structural_governance']
        lines.extend(['## '+letter+'. '+s['ticker']+' expected result','',
            f"Evidence: {s['evidence']}. Fair before/after: {s['fair_before']} / {s['fair_after']}.",'',
            f"Severity {g.get('severity')}; primary {g.get('structural_penalty')}; secondary {g.get('secondary_penalty')}; total {g.get('total_structural_penalty')}; confidence ceiling {g.get('confidence_ceiling')}; structural exit block {g.get('precise_exit_block')}.",'',
            f"Confirmed gaps: {g.get('structural_gaps')}; warnings: {g.get('warnings')}.",''])
    lines.extend(['ORCL MODERATE requires verified capital-structure gap. NVDA MODERATE plus growth secondary requires actual HIGH growth overlap and a confirmed gap. Default observations lack those inputs, so LOW concentration may be all that can be established. Cloud input evidence decides; none is hardcoded.',
        '', '## L. Production invariants','',
        'Automated before/after tests cover all14 fixed financial fixtures: fair, range, production model outputs, weights, included/excluded models, outlier decisions, MOS and buy zones unchanged. Peer diagnostic isolation remains tested. Pre-V4.6 regression hashes run with the post-valuation policy disabled only in that historical test; new governance tests independently prove every immutable valuation field remains identical with the policy enabled. Admin audit exports explicit invariants and before/after reliability/confidence/precise-exit state.',
        '', '## M. Snapshot compatibility','',
        'raw JSON and reliability_json save structural governance/version; existing snapshots get null governance. Last Reliable stores the governed blend and restores it verbatim, including historical exit state and calculated_at. No fallback eligibility,24h freshness, currency/split/share safety rules change. Input fingerprints remain based solely on existing financial inputs/context; governance metadata does not enter the fingerprint. Cached/live structures remain separate. Diagnostic capture uses the existing no-write resolver and does not update Last Reliable.',
        '', '## N. Cloud validation instructions','',
        'As ADMIN_EMAIL in Cloud, open V4.5 估值结构导出 and click V4.6 Reliability Governance Audit. It captures GOOG/MSFT/ORCL/NVDA/AMZN serially in the existing read-only batch. Download v46_cloud_reliability_governance.json. Verify fair_unchanged and all invariants are true; inspect real before/after scores, ceilings and exit blocks. Cached entries are labeled source_status; their saved historical policy is shown rather than recomputed from current missing inputs. No credentials in exports. Local Streamlit widget tests verify access revocation and downloads; actual Cloud validation remains pending deployment.',
        '', '## O. V4.7 recommendation','',
        'After eligible real Cloud audits: prioritize independent-family minimum for HIGH confidence and confirmed capital-structure gaps; investigate capital-structure-aware earnings overlays and CapEx-normalized owner earnings where those gaps are evidenced. Family-level or correlation-aware production weighting requires a separate validation phase because it changes fair. Do not prioritize by benchmark closeness. None of these V4.7 changes is implemented.'])
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--input-json',type=Path);args=p.parse_args()
    stocks=json.loads(args.input_json.read_text(encoding='utf-8-sig'))['stocks'] if args.input_json else report_inputs()
    report=build_report(stocks)
    (ROOT/'reports/v46_production_reliability_governance.json').write_bytes(snapshot_json(report))
    (ROOT/'reports/v46_production_reliability_governance.md').write_text(markdown(report),encoding='utf-8')
    print('V4.6 report written; no Cloud fetch or snapshot write.')


if __name__=='__main__':main()
