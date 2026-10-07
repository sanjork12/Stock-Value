"""Replay identical financial inputs against pre-V4.4, V4.4 and local fix.

Git revisions supply code, not historical market observations. Default inputs
are explicitly synthetic. No network or credentials are required by this audit.
"""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analysis_service
from peer_comparable import PeerComparableResult
from valuation_engine import can_emit_buy_zones, can_emit_exit_zones

BEFORE = 'e44131863ae02184832f2f36ca64ac09dd57372f'
BROKEN = '4621369b196fe3321c396d582a98ff3e1bf7e564'
FIXTURES = ROOT/'tests/fixtures/peer_diagnostic_financials.json'


class UnavailableProvider:
    def get_company_profile(self, ticker):
        return {'status':'NO_DATA','data':None,'source':'Finnhub','fetched_at':datetime.now(timezone.utc).isoformat()}

    def get_basic_financials(self, ticker):
        raise AssertionError('No metrics request expected after unavailable profile')


def history(*_):
    index = pd.date_range('2025-01-02', periods=260, freq='B')
    return pd.DataFrame(dict(Open=100.,High=101.,Low=99.,Close=100.,Volume=1_000_000,
                             SMA30=99.,SMA50=98.,SMA200=95.),index=index)


def load_revision(revision):
    """Read trusted repository code without changing the working tree."""
    loaded = {}
    for filename in ('valuation_engine.py','analysis_service.py'):
        name = '_peer_audit_'+revision[:8]+'_'+filename[:-3]
        spec = importlib.util.spec_from_loader(name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        source = subprocess.check_output(['git','show',revision+':'+filename],cwd=ROOT).decode('utf-8')
        if filename == 'analysis_service.py':
            with patch.dict(sys.modules,{'valuation_engine':loaded['valuation_engine.py']}):
                exec(compile(source,revision+':'+filename,'exec'),module.__dict__)
        else:
            exec(compile(source,revision+':'+filename,'exec'),module.__dict__)
        loaded[filename] = module
    return loaded['analysis_service.py']


def run(module,ticker,financials,peer='unavailable'):
    args = dict(history_loader=history,fundamentals_loader=lambda _:deepcopy(financials))
    if module is analysis_service or 'peer_mode' in module.analyze_ticker.__code__.co_varnames:
        args.update(peer_mode='diagnostic',peer_provider=UnavailableProvider())
    def diagnostic(*args,**kwargs):
        if peer=='mutating':
            args[1].clear()
            raise RuntimeError('Injected peer mutation; not an observed Cloud payload')
        if peer=='exception':raise RuntimeError('Injected peer failure')
        return PeerComparableResult(ticker,'synthetic',valid=peer=='valid',applicable=True,
                                    low=1e6,mid=2e6,high=3e6,confidence='HIGH' if peer=='valid' else 'UNAVAILABLE')
    with patch('peer_comparable.calculate_peer_comparable',side_effect=diagnostic):
        return module.analyze_ticker(ticker,**args)


def internal_snapshot(result):
    blend = result.get('blend') or {}
    return dict(blended_low=result.get('blended_low'),blended_mid=result.get('blended_mid'),
        blended_high=result.get('blended_high'),fair_value=result.get('fair_value'),
        confidence=result.get('confidence'),valuation_mode=result.get('valuation_mode'),
        reliability_score=result.get('reliability_score'),dispersion_pct=result.get('dispersion_pct'),
        buy_zones=result.get('zones'),exit_zones=result.get('exit_zone'),
        status=result.get('recommendation'),state=result.get('state'),
        included_models=blend.get('included_models'),models=blend.get('models'),
        reliability=blend.get('reliability'),blend=blend,
        can_emit_buy_zones=can_emit_buy_zones(blend),can_emit_exit_zones=can_emit_exit_zones(blend))


def report_snapshot(snapshot):
    out={k:v for k,v in snapshot.items() if k not in ('blend','models')}
    out['internal_reason']=snapshot['blend'].get('reason')
    fields=('valid','applicable','reason','outlier','low','mid','high')
    out['model_summaries']={name:{key:obj.get(key) for key in fields}
                            for name,obj in (snapshot.get('models') or {}).items()}
    return out


def build_report(financials_by_ticker):
    before,broken=load_revision(BEFORE),load_revision(BROKEN)
    rows=[]
    for ticker,financials in financials_by_ticker.items():
        original=internal_snapshot(run(before,ticker,financials))
        current=internal_snapshot(run(broken,ticker,financials))
        fixed_result=run(analysis_service,ticker,financials)
        fixed=internal_snapshot(fixed_result)
        fault_old=internal_snapshot(run(broken,ticker,financials,'mutating'))
        fault_fixed=internal_snapshot(run(analysis_service,ticker,financials,'mutating'))
        missing_eps=deepcopy(financials)
        for field in ('forward_eps','trailing_eps','eps_proxy','forward_eps_source','trailing_eps_source','eps_proxy_source'):
            missing_eps[field]=None
        missing_before=internal_snapshot(run(before,ticker,missing_eps))
        missing_current=internal_snapshot(run(broken,ticker,missing_eps))
        missing_fixed=internal_snapshot(run(analysis_service,ticker,missing_eps))
        rows.append(dict(ticker=ticker,before_v44=report_snapshot(original),current_v44=report_snapshot(current),after_fix=report_snapshot(fixed),
            same_input_before_equals_v44=original==current,same_input_before_equals_fix=original==fixed,
            peer_result=fixed_result.get('peer_comparable_result'),
            peer_diagnostics=fixed_result.get('peer_diagnostics'),
            missing_quote_eps_scenario=dict(before_v44=report_snapshot(missing_before),current_v44=report_snapshot(missing_current),
                after_fix=report_snapshot(missing_fixed),all_equal=missing_before==missing_current==missing_fixed),
            synthetic_mutation_fault=dict(current_v44=report_snapshot(fault_old),after_fix=report_snapshot(fault_fixed),
                                          fixed_equals_before=fault_fixed==original)))
    return dict(before_commit=BEFORE,v44_commit=BROKEN,
        input_provenance='See input file. Default is synthetic; not a historical Dashboard export.',
        cloud_regression_root_cause='Unconfirmed without exported financial inputs; normal same-input replay is recorded separately from injected faults.',
        user_reported_cloud_regression={
            'tickers':['AVGO','NVDA','MU','PLTR','COIN','CRCL'],
            'current_broken':'UNAVAILABLE',
            'source':'User description; export and provider input snapshots not supplied',
            'before_v44_actual_values':None,'after_fix_cloud_values':None},
        rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=FIXTURES)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/v44_isolation_regression.json')
    args=parser.parse_args()
    data=json.loads(args.inputs.read_text(encoding='utf-8'))
    report=build_report(data['tickers'])
    report['input_provenance']=data.get('description','User-provided normalized financial inputs')
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(row['same_input_before_equals_fix'] and row['synthetic_mutation_fault']['fixed_equals_before']
               and row['missing_quote_eps_scenario']['all_equal'] for row in report['rows']), 'Internal isolation regression'
    for row in report['rows']:
        a,b,c=(row[key] for key in ('before_v44','current_v44','after_fix'))
        print(row['ticker'],a['fair_value'],a['confidence'],a['valuation_mode'],
              'V4.4 identical:',row['same_input_before_equals_v44'],
              'fixed identical:',row['same_input_before_equals_fix'],
              'mutation isolated:',row['synthetic_mutation_fault']['fixed_equals_before'])
