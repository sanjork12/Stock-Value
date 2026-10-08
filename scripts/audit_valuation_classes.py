"""Generate V4.5 source audit; optionally replay captured Cloud analyses.

Input: {"analyses": {"GOOG": {"financials": <normalized snapshot>,
"blend": <captured engine result>, "source_status": "live", ...}, ...}}.
No fetch, Auth, snapshot store or Last Reliable code is imported/called.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from valuation_calibration_audit import TICKERS,audit_analysis
from valuation_engine import build_profile
from financial_forensics import snapshot_json

CLOUD_CONTEXT={'GOOG':253.81,'MSFT':657.04,'ORCL':237.71,'NVDA':358.45,'AMZN':290.44}
BENCHMARKS={'GOOG':345,'MSFT':544,'ORCL':180,'NVDA':300,'AMZN':285}
FINDINGS={
 'GOOG':{'known':'Mega-cap override with ticker PE range 20–26 (mid 23); same class as MSFT, different ticker overlay. No segment-level Cloud/YouTube/advertising valuation.',
         'candidates':['MULTIPLE_ASSUMPTION','MODEL_CORRELATION','BUSINESS_MIX'],
         'unresolved':'Need actual EPS/source, Growth PE floor/cap, DCF FCF/share bridge and exclusions to identify the downward driver. Lower than benchmark is not proof of undervaluation bias.'},
 'MSFT':{'known':'Ticker PE 26–32 (mid 29); Forward PE and Growth PE share EPS, with implied forward/trailing growth also entering Growth PE. DCF fixed growth is 11%, not observed earnings_growth.',
         'candidates':['EPS_FORECAST','MODEL_CORRELATION','GROWTH_DOUBLE_COUNT'],
         'unresolved':'Cannot identify largest positive contribution or validate EPS forecast without captured models. Shared signals are a risk, not evidence of a numeric forecast error.'},
 'ORCL':{'known':'Mature-growth override, PE 18–26 (mid 22), fixed DCF growth 10%. Preferred models are Forward PE/DCF/Growth PE; no EV/EBITDA primitive in the internal preferred set. DCF explicitly computes enterprise + cash − debt, then divides by canonical enterprise shares.',
         'candidates':['CAPITAL_STRUCTURE','MODEL_CORRELATION','DCF_ASSUMPTION'],
         'unresolved':'Correct bridge syntax does not validate the actual cash/debt values or FCFF basis. EPS P/E has no extra debt subtraction; whether leverage is reflected economically requires input/source validation.'},
 'NVDA':{'known':'Semiconductor-growth override, PE 20–28 (mid 24), normalized growth base 16%/cap 18%, fixed DCF growth 12%. Forecast EPS and implied EPS growth are shared between PE primitives.',
         'candidates':['EPS_FORECAST','GROWTH_DOUBLE_COUNT','MODEL_CORRELATION'],
         'unresolved':'No automatic forward-PE multiple expansion from live growth. DCF fixed growth is a separate assumption; triple counting of one live signal is not established.'},
 'AMZN':{'known':'Mega-cap override, PE 26–32 (mid 29), normalized growth base 14%/cap 16%, fixed DCF growth 12%. Company-level Peer is ineligible and cannot enter diagnostic internal blend.',
         'candidates':['MODEL_APPLICABILITY','MODEL_CORRELATION','WEIGHTING'],
         'unresolved':'An internal fair near benchmark does not establish healthy model independence. Need captured applicability/outlier/weights/dispersion; do not assume DCF is included or healthy.'}}


def build_audit(analyses=None,benchmarks=None):
    analyses=analyses or {}
    stocks=[]
    for ticker in TICKERS:
        profile=build_profile(ticker,{})
        item={'ticker':ticker,'source_findings':deepcopy(FINDINGS[ticker]),
              'source_profile':profile.to_dict(),'source_assumptions':deepcopy(profile.spec),
              'direction_classification':'NOT_ESTABLISHED',
              'direction_reason':'No validated captured model/input evidence; benchmark gap cannot establish structural bias.'}
        if ticker in analyses:item['captured_audit']=audit_analysis(ticker,deepcopy(analyses[ticker]))
        else:item['captured_audit']={'ticker':ticker,'status':'CLOUD_MODEL_INPUT_SNAPSHOT_REQUIRED',
            'exact_root_cause':None,'waterfall':None,'sensitivity':None}
        stocks.append(item)
    report={'audit_version':'V4.5','generated_at':datetime.now(timezone.utc).isoformat(),
        'scope':'READ_ONLY_AUDIT_NO_CALIBRATION','evidence_status':'PARTIAL_SOURCE_AUDIT' if len(analyses)<5 else 'CAPTURED_INPUT_AUDIT',
        'stocks':stocks,'growth_findings':[
            'Forward PE and Growth PE share the same EPS basis.',
            'Growth PE combines fixed norm_growth with eligible live earnings_growth and implied forward/trailing EPS growth, then caps it.',
            'Forward PE multiple is fixed by ticker/class; no live-growth multiple expansion.',
            'DCF projects FCF using fixed class/ticker growth with a mature-growth fade and fixed terminal growth; no live earnings_growth or explicit revenue/margin model.',
            'Weighted blending shared-signal models can overrepresent one expectation; this is qualitative correlation, not proven arithmetic double/triple counting.'],
        'recommended_experiments':[
            'Capture same-run normalized inputs, source timestamps and full internal blend before any calibration.',
            'Separate EPS-level and EPS-growth sensitivity; compare linked Forward PE/Growth PE contributions without changing weights.',
            'In isolated experiments, assess correlated-model weight concentration; do not activate changes.',
            'Validate capex/FCF normalization, levered versus unlevered cashflow basis, debt bridge and canonical shares.',
            'Run segment/business-mix scenarios separately from company-level baseline, without fitting to benchmark.',
            'Inspect ticker overlays versus class assumptions and floor/cap saturation before proposing class-specific experiments.']}
    # Benchmark context is attached only AFTER every model and sensitivity run.
    refs=BENCHMARKS if benchmarks is None else benchmarks
    report['post_hoc_only']=[{'ticker':t,'user_reported_cloud_fair':CLOUD_CONTEXT[t],
        'benchmark':refs.get(t),'gap_pct':(CLOUD_CONTEXT[t]/refs[t]-1)*100 if refs.get(t) else None,
        'scope':'User supplied approximate final values; never audit/model/sensitivity inputs'} for t in TICKERS]
    return report


def markdown(report):
    lines=['# V4.5 Valuation-Class Calibration Audit','',
        '## A. Executive summary','',
        'Read-only source audit and captured-input replay tool. No production formula, parameter, class, applicability, weight, MOS, zone, fallback or Peer activation changes.',
        '', 'Evidence limitation: supplied Cloud final fair values alone do not identify model contributions or exact root causes. Missing values below are unknown, not zero. No synthetic fixture results stand in for Cloud.',
        '', 'Direction labels UNDERVALUATION_BIAS_RISK / BALANCED / OVERVALUATION_BIAS_RISK are intentionally not assigned without validated internal evidence. Benchmark proximity is insufficient.', '']
    sections={'GOOG':'B. GOOG root cause','MSFT':'C. MSFT root cause','ORCL':'D. ORCL root cause','NVDA':'E. NVDA control','AMZN':'F. AMZN healthy anchor — not yet established'}
    for stock in report['stocks']:
        finding=stock['source_findings'];capture=stock['captured_audit']
        lines.extend(['## '+sections[stock['ticker']],'',finding['known'],'',finding['unresolved'],'',
            'Snapshot status: '+capture['status']+'. Exact Cloud root cause: pending captured evidence.','',
            'Structural candidates (not confirmed causes): '+', '.join(finding['candidates'])+'.',''])
    lines.extend(['## G. Model contribution waterfalls','',
        'For each captured model: raw pre-outlier mid, applicability/validity/inclusion, exclusions, exact inputs, low/mid/high, configured and normalized weights, weighted contribution, outlier reason. Contribution sum must equal blended mid to 1e-6 absolute tolerance.', ''])
    for stock in report['stocks']:
        audit=stock['captured_audit'];lines.extend(['### '+stock['ticker'],''])
        if not audit.get('models'):
            lines.extend(['Unavailable: no matching Cloud model/input snapshot.','']);continue
        lines.extend(['| Model | Raw Mid | Normalized Weight | Contribution |','| --- | ---: | ---: | ---: |'])
        for row in audit['models']:
            lines.append(f"| {row['model_name']} | {row['raw_fair_value']} | {row['weight_after_normalization']} | {row['contribution_to_blended_mid']} |")
        lines.extend(['',f"Sum {audit['waterfall_sum']}; captured mid {audit['fair']}; verified {audit['waterfall_matches']}.",''])
    lines.extend(['## H. Growth double-count findings','']+['- '+x for x in report['growth_findings']]+['',
        '## I. Sensitivity results','',
        'GOOG/MSFT/ORCL: snapshot replay required before sensitivities. Forward EPS ±10%; observed earnings_growth ±20% with class/DCF assumptions fixed; Forward PE realized target multiple ±10% only. Full applicability/outlier/blend rerun. These scopes distinguish shared-signal sensitivity from changing fixed production assumptions.',
        '', 'Numerical sensitivities are in JSON for capture-replay matches. Without snapshots, no elasticities or most-sensitive-input ranking is fabricated. Cached final fair paired with current failed input is rejected.',
        '', '## J. Model correlation','',
        'Forward PE ↔ Growth PE: HIGH_CORRELATION (shared EPS; Growth PE also uses implied forward/trailing growth). PE ↔ DCF: MEDIUM_CORRELATION qualitatively (same firm/cycle, separate fixed DCF growth and FCF basis). No time-series correlation was measured; no weights changed.',
        '', '## K. Root-cause matrix','',
        'Each stock has at most three structural candidates above. No INPUT_QUALITY error, classification mismatch, systematic bias direction or exact Cloud primitive driver is proven from final fair values alone.',
        '', '## L. Recommended next calibration experiments','']+['- '+x for x in report['recommended_experiments']]+['',
        '## POST-HOC ONLY reference context',''])
    for row in report['post_hoc_only']:
        lines.append(f"- {row['ticker']}: user Cloud fair {row['user_reported_cloud_fair']}, benchmark {row['benchmark']}, gap {row['gap_pct']:.2f}% (not used in audit calculations)." if row['gap_pct'] is not None else f"- {row['ticker']}: no benchmark.")
    lines.extend(['','## Reproduce with Cloud captures','',
        'Run `python scripts/audit_valuation_classes.py --input-json <file>` with an `analyses` object keyed by ticker, each containing normalized `financials` and the matching captured `blend`. The tool makes no network calls or snapshot writes. Report JSON contains detailed inputs, contributions and all sensitivity runs.',
        '', 'No production changes. Cloud export capture is pending deployment. No commit or push; full-suite validation is reported in the completion message.',''])
    return '\n'.join(lines)


def write_report(report,output_dir):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'v45_valuation_class_calibration_audit.json').write_bytes(snapshot_json(report))
    (output_dir/'v45_valuation_class_calibration_audit.md').write_text(markdown(report),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input-json',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reports')
    args=parser.parse_args()
    data=json.loads(args.input_json.read_text(encoding='utf-8-sig')) if args.input_json else {}
    analyses=data.get('analyses')
    if analyses is None and 'stocks' in data:
        analyses={stock['ticker']:stock for stock in data['stocks'] if stock.get('capture_status')=='COMPLETE'}
    write_report(build_audit(analyses),args.output_dir)
    print('Read-only V4.5 reports written. No production or snapshot writes.')


if __name__=='__main__':main()
