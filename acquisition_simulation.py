"""Controlled administrator simulation using one real baseline per ticker.

Only baseline acquisition calls providers. Scenario recovery replays captured
direct values and is labelled replay, not another live Yahoo observation.
Never reads/writes the production acquisition cache or Last Reliable.
"""
from copy import deepcopy
from datetime import datetime,timezone
from uuid import uuid4

from fundamental_acquisition import acquire,RecordingTicker,Flags,flags,get_value,health
from input_resilience_audit import TICKERS


def run_simulation(*,factory,provider=None,options=None):
    options=options or flags();batch_id=str(uuid4());stocks=[]
    class ReadOnlyProvider:
        def peek(self,path,ticker):
            from finnhub_service import FinnhubProvider
            if not isinstance(provider,FinnhubProvider):return {'status':'NO_DATA','data':None}
            key=(path,(('symbol',ticker),))
            with provider._lock:
                item=provider._cache.get(key)
                return deepcopy(item[1]) if item and item[0]>provider.clock() else {'status':'NO_DATA','data':None}
        def get_company_profile(self,ticker):return self.peek('stock/profile2',ticker)
        def get_quote(self,ticker):return self.peek('quote',ticker)
    readonly_provider=ReadOnlyProvider()
    for ticker in TICKERS:
        try:
            info,t,meta=acquire(ticker,factory,provider=readonly_provider,options=options)
            critical=meta['critical_missing_fields']
            if critical:
                stocks.append({'ticker':ticker,'status':'BASELINE_INCOMPLETE',
                    'message':'当前实时数据本身不完整，无法执行受控 acquisition 测试，请稍后重试。',
                    'baseline_metadata':meta,'scenarios':[]})
                continue
            # Record direct alternate evidence at most once before any simulation.
            underlying=t._ticker
            fast={key:get_value(getattr(underlying,'fast_info',None),key)
                for key in ('shares','market_cap','last_price','currency')}
            try:metadata=deepcopy(underlying.get_history_metadata())
            except Exception:metadata={}
            try:splits=deepcopy(underlying.splits)
            except Exception:splits=None
            scenarios=[]
            for name,missing in (('healthy',()),('partial_get_info',('forwardEps','currency','financialCurrency','financialCurrencyCode')),
                ('missing_forward_eps',('forwardEps','epsForward')),('missing_currency',('currency','financialCurrency','financialCurrencyCode')),
                ('missing_split_context',('lastSplitDate','lastSplitFactor'))):
                primary=deepcopy(info)
                for key in missing:primary.pop(key,None)
                calls=[0]
                class Replay:
                    def __init__(self,data):self.data=deepcopy(data);self.ticker=ticker
                    def get_info(self):return deepcopy(self.data)
                    @property
                    def info(self):return deepcopy(self.data)
                    @property
                    def fast_info(self):return deepcopy(fast)
                    def get_history_metadata(self):return deepcopy(metadata)
                    @property
                    def splits(self):return deepcopy(splits)
                def replay_factory(symbol):
                    calls[0]+=1
                    return Replay(primary if calls[0]==1 else info)
                # Replay provider is not allowed to make a network request. Already
                # observed profile evidence is optional; missing evidence stays unknown.
                class NoNewProvider:
                    def get_company_profile(self,_):return {'status':'NO_DATA','data':None}
                    def get_quote(self,_):return {'status':'NO_DATA','data':None}
                _,_,result=acquire(ticker,replay_factory,provider=NoNewProvider(),options=options)
                scenarios.append({'scenario':name,'ticker':ticker,'primary_health':result['primary_health']['overall_state'],
                    'critical_missing_fields':result['primary_health']['critical_missing_fields'],
                    'fresh_recovery_attempted':result['fresh_recovery_attempted'],
                    'recovery_result':result['fresh_recovery_result'],
                    'safe_fallback_fields':result['provider_health']['fallback_fields_used'],
                    'final_input_health':result['health_state'],
                    'would_calibration_reasons_remain':'INPUT_GAPS_REMAIN' if result['critical_missing_fields'] else 'UNKNOWN_REQUIRES_PRODUCTION_GUARD',
                    'simulated_missing_input_reasons_remaining':result['critical_missing_fields'],
                    'calibration_status':'NOT_RECOMPUTED_REQUIRES_LIVE_PRODUCTION_GUARD',
                    'source':'CONTROLLED_REPLAY_OF_THIS_RUN_DIRECT_BASELINE',
                    'new_provider_requests_in_scenario':0,'metadata':result})
            stocks.append({'ticker':ticker,'status':'COMPLETE','baseline_metadata':meta,
                'alternate_capture_calls':{'fast_info_public_fields':1,'history_metadata':1,'splits':1},
                'scenarios':scenarios})
        except Exception as exc:
            stocks.append({'ticker':ticker,'status':'BASELINE_FAILED','exception_category':type(exc).__name__,'scenarios':[]})
    return {'input_batch_id':batch_id,'generated_at':datetime.now(timezone.utc).isoformat(),
        'mode':'READ_ONLY_ACQUISITION_SIMULATION','production_cache_read':False,'production_cache_write':False,
        'production_cache_scope':'FUNDAMENTALS_RAW_CACHE','finnhub_cache_readonly':True,'finnhub_new_requests':0,
        'valuation_recomputed':False,'real_eligibility_modified':False,'stocks':stocks}
