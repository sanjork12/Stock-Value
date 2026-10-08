"""Repeatable five-stock comparison; credentials never enter reports.

Without configured Finnhub credentials no live financial loader is called.
Reference benchmarks are optional external report inputs, never model inputs.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finnhub_service import get_finnhub_provider
from mag7_monitor import fill_fundamental_fallbacks
from peer_comparable import calculate_peer_comparable, canonical, PEER_CLASSES, MULTIPLE_KEYS
from finnhub_service import number
from valuation_engine import infer_valuation_class, valuate

SAMPLES = ['NVDA','ORCL','MSFT','GOOG','AMZN']


class ReviewProvider:
    """Read-only, whitelist-only evidence recorder; only two allowed endpoints.

    Reuse observations across the five targets, including Alphabet aliases.
    Provider credentials and arbitrary response strings never enter reports.
    """
    def __init__(self, provider):
        self.provider=provider
        self.records={}
        self.responses={}
        self.blocked=False

    def configured(self):
        return self.provider.configured()

    def _read(self,kind,ticker):
        ticker=canonical(ticker)
        record=self.records.setdefault(ticker,{})
        if kind in record:return deepcopy(self.responses[(kind,ticker)])
        if self.blocked:
            response={'status':'RATE_LIMIT','data':{},'fetched_at':None}
        elif not self.configured():
            response={'status':'NOT_CONFIGURED','data':{},'fetched_at':None}
        else:
            try:response=getattr(self.provider,'get_'+kind)(ticker)
            except Exception:response={'status':'NETWORK_ERROR','data':{},'fetched_at':None}
        statuses={'AVAILABLE','NO_DATA','NOT_CONFIGURED','NOT_ENTITLED','RATE_LIMIT',
                  'NETWORK_ERROR','INVALID_RESPONSE','INVALID_SYMBOL'}
        status=response.get('status')
        if status not in statuses:status='INVALID_RESPONSE'
        if status=='RATE_LIMIT':self.blocked=True
        data=response.get('data') or {}
        keys=('marketCapitalization',) if kind=='company_profile' else tuple(MULTIPLE_KEYS.values())+(
            'Revenue Growth TTM YoY','Operating Margin TTM','EPS Growth TTM YoY','ROE TTM','Market Capitalization')
        projected={key:number(data.get(key)) for key in keys}
        # No untrusted free-form strings (URLs, exception text, credentials).
        try:stamp=datetime.fromisoformat(str(response.get('fetched_at')).replace('Z','+00:00')).isoformat()
        except ValueError:stamp=None
        record[kind]={'status':status,'data':projected,'fetched_at':stamp,
                      'source':'Finnhub Company Profile' if kind=='company_profile' else 'Finnhub Basic Financials'}
        # Preserve the model's complete original public input. Evidence
        # projection must not change industry classification or metric gates.
        self.responses[(kind,ticker)]=deepcopy(response)
        return deepcopy(response)

    def get_company_profile(self,ticker):return self._read('company_profile',ticker)
    def get_basic_financials(self,ticker):return self._read('basic_financials',ticker)


def _composition(peer,provider):
    rows=[]
    for ticker in peer.peers_considered:
        record=provider.records.get(ticker,{})
        profile=record.get('company_profile',{})
        metrics=record.get('basic_financials',{})
        m=metrics.get('data') or {}
        rows.append({'ticker':ticker,
            'valuation_class':(peer.provenance.get(ticker) or {}).get('valuation_class') or PEER_CLASSES.get(ticker) or infer_valuation_class(ticker,{}),
            'class_scope':'peer-only classification used by the existing model',
            'multiple_value':m.get(MULTIPLE_KEYS.get(peer.selected_multiple)),
            'multiple_values':{name:m.get(key) for name,key in MULTIPLE_KEYS.items()},
            'growth_pct':m.get('Revenue Growth TTM YoY'),'margin_pct':m.get('Operating Margin TTM'),
            'market_cap_usd_millions':(profile.get('data') or {}).get('marketCapitalization') or m.get('Market Capitalization'),
            'included':ticker in peer.peers_included,
            'exclusion_reason':peer.exclusion_reasons.get(ticker),
            'sources':{'profile':{'source':'Finnhub Company Profile','status':profile.get('status','NOT_REQUESTED'),
                                  'fetched_at':profile.get('fetched_at')},
                       'metrics':{'source':'Finnhub Basic Financials','status':metrics.get('status','NOT_REQUESTED'),
                                  'fetched_at':metrics.get('fetched_at')}},
            'data_age_hours':(peer.provenance.get(ticker) or {}).get('peer_data_age_hours')})
    return rows


def build_report(*, provider=None, financial_loader=None, references=None, tickers=None, internal_results=None):
    provider = ReviewProvider(provider or get_finnhub_provider())
    configured = provider.configured()
    rows, details = [], []
    selected=list(dict.fromkeys(canonical(t) for t in (tickers if tickers is not None else SAMPLES)))
    if any(t not in SAMPLES for t in selected):raise ValueError('Unsupported diagnostic ticker')
    for ticker in selected:
        financials = {}
        status = 'NOT_CONFIGURED'
        internal = None
        blend = {}
        if internal_results is not None:
            result=(internal_results or {}).get(ticker) or {}
            financials=deepcopy(result.get('financials') or {})
            blend=deepcopy(result.get('blend') or {})
            internal=number(result.get('fair_value'))
            status='AVAILABLE' if internal is not None else 'TARGET_FINANCIALS_UNAVAILABLE'
        elif configured and financial_loader is None:
            status = 'TARGET_INPUT_SNAPSHOT_REQUIRED'
        elif configured:
            try:
                financials = fill_fundamental_fallbacks(financial_loader(ticker) or {})
                blend = valuate(ticker,financials,peer_mode='diagnostic')
                internal = blend.get('fair')
                status = 'AVAILABLE' if financials else 'NO_TARGET_FINANCIALS'
            except Exception:
                status = 'TARGET_FINANCIALS_UNAVAILABLE'
        peer = calculate_peer_comparable(ticker,financials,infer_valuation_class(ticker,financials),provider=provider)
        context = (references or {}).get(ticker,{})
        benchmark = context.get('external_benchmark')
        direction = 'UNAVAILABLE'
        if peer.valid and internal is not None and benchmark is not None:
            delta = abs(peer.mid-benchmark)-abs(internal-benchmark)
            direction = 'CLOSER' if delta < 0 else 'FURTHER' if delta > 0 else 'UNCHANGED'
        rows.append(dict(ticker=ticker, target_data_status=status, current_internal_mid=internal,
            peer_low=peer.low,peer_mid=peer.mid,peer_high=peer.high,confidence=peer.confidence,
            selected_multiple=peer.selected_multiple,peers_included=';'.join(peer.peers_included),
            external_benchmark=benchmark,benchmark_direction=direction,
            user_supplied_internal_context=context.get('internal_context'),
            warnings=';'.join(peer.warnings),
            current_internal_fair=internal,current_internal_low=blend.get('blended_low'),
            current_internal_high=blend.get('blended_high'),peer_valid=peer.valid,
            peer_confidence=peer.confidence,peer_group=peer.peer_group,
            peer_q1=peer.peer_q1,peer_median=peer.peer_median,peer_q3=peer.peer_q3,
            target_metric=peer.target_metric,target_metric_value=peer.target_metric_value,
            peer_fair_low=peer.low,peer_fair_mid=peer.mid,peer_fair_high=peer.high,
            peer_dispersion=peer.dispersion,
            peers_considered=';'.join(peer.peers_considered),peers_excluded=';'.join(peer.peers_excluded),
            peer_direction='UNAVAILABLE' if not peer.valid or not internal else
                           'UP' if peer.mid>internal else 'DOWN' if peer.mid<internal else 'UNCHANGED',
            difference_dollars=peer.mid-internal if peer.valid and internal else None,
            difference_pct=(peer.mid/internal-1)*100 if peer.valid and internal else None,
            internal_error_pct=(internal/benchmark-1)*100 if internal and benchmark else None,
            peer_error_pct=(peer.mid/benchmark-1)*100 if peer.valid and benchmark else None,
            review_eligible=bool(peer.valid and len(peer.peers_included)>=3 and peer.dispersion is not None
                                and peer.dispersion<=.6 and peer.peer_group!='commerce_platform')))
        detail=peer.to_dict()
        from peer_post_data_audit import audit_multiples
        detail['post_data_audit']=audit_multiples(ticker,financials,infer_valuation_class(ticker,financials),provider)
        detail['alternate_valid_multiples']=[a['Multiple'] for a in detail['post_data_audit']['attempts']
            if a['Status']=='VALID' and a['Multiple']!=peer.selected_multiple]
        detail['composition']=_composition(peer,provider)
        for member in detail['composition']:member.update(peer.peer_scores.get(member['ticker'],{}))
        detail['multiple_policy']='first valid multiple; alternatives are sequential attempts, never a combined blend'
        detail['review_eligibility_note']='Report-only minimum: >=3 peers, IQR/median <=60%, no aggregate commerce mix. Not a production parameter change.'
        details.append(detail)
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),mode='diagnostic',
                live_finnhub_configured=configured,
                caveat='User-supplied internal context is not a current recalculation. Unavailable values are not inferred.',
                comparison=rows,peer_results=details)


def write_report(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'v44_peer_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output_dir/'v44_peer_comparison.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        rows=report['comparison']; writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default=str(ROOT/'output'/'peer_comparable'))
    parser.add_argument('--reference-file',type=Path)
    parser.add_argument('--target-input-file',type=Path,
                        help='Previously captured normalized target inputs keyed by ticker; no new Yahoo requests.')
    args=parser.parse_args()
    references=json.loads(args.reference_file.read_text(encoding='utf-8')) if args.reference_file else {}
    targets=json.loads(args.target_input_file.read_text(encoding='utf-8')) if args.target_input_file else None
    loader=(lambda ticker:targets[ticker]) if targets is not None else None
    report=build_report(references=references,financial_loader=loader)
    write_report(report,args.output_dir)
    print('Comparison saved; live Finnhub configured:',report['live_finnhub_configured'])
