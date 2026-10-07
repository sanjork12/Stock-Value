"""Read-only financial input snapshots and evidence-based failure traces.

All exported values are schema-projected public numbers, currencies, dates and
known source/reason identifiers. Never serialize complete provider/Auth objects.
"""
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
import json
import platform
import re

from financial_forensics_observer import (numeric, currency, period, public_observations,
                                         observe_financial_inputs, INFO_NUMBERS, INFO_CURRENCIES)

class FinancialDiagnosticFailure(RuntimeError):
    def __init__(self,stage,exc=None,public_error=None):
        categories={TypeError:'TYPE_ERROR',ValueError:'VALUE_ERROR',KeyError:'KEY_ERROR',
                    ImportError:'IMPORT_ERROR',RuntimeError:'RUNTIME_ERROR',OSError:'IO_ERROR'}
        category=next((code for kind,code in categories.items() if isinstance(exc,kind)),'UNEXPECTED_ERROR')
        locations=[]
        trace=exc.__traceback__ if exc is not None else None
        allowed={'financial_forensics.py','financial_forensics_admin.py','financial_forensics_observer.py',
                 'analysis_service.py','finnhub_service.py','mag7_monitor.py'}
        while trace is not None:
            # Only repository source basename + line, never message/locals/URL.
            name=trace.tb_frame.f_code.co_filename.replace('\\','/').rsplit('/',1)[-1]
            if name in allowed:locations.append({'module':name,'line':trace.tb_lineno})
            trace=trace.tb_next
        self.public_error=public_error or {'stage':stage,'category':category,'code_locations':locations[-4:]}
        super().__init__('Financial diagnostic failed: '+stage+' / '+category)



TICKERS=('AVGO','NVDA','MU','PLTR','COIN','CRCL','AMZN','MSFT')
SOURCE_NAMES={'forwardEps','ticker.info.forwardEps','epsForward','earnings_estimate','price/forwardPE','forward_eps',
 'trailingEps','ticker.info.trailingEps','yahoo_trailing_eps','trailing_eps','statement_derived',
 'income_statement_diluted_eps','ni_over_diluted_shares','historical_eps','statement_trailing_eps',
 'impliedSharesOutstanding','marketCap/price','diluted_average_shares','sharesOutstanding',
 'ticker.cashflow','ticker.info.freeCashflow','ticker.info.operatingCashflow','ticker.info.totalCash',
 'ticker.info.totalDebt','ticker.balance_sheet.cash','ticker.balance_sheet.debt',
 'fallback_missing_assumed_zero','ticker.info.sharesOutstanding','ticker.balance_sheet.shares',
 'ticker.info.marketCap','ticker.info.earningsGrowth','ticker.info.revenueGrowth',
 'ticker.get_earnings_estimate.avg','history.Close','ticker.info.currency','ticker.info.financialCurrency',
 'ticker.info.financialCurrencyCode','existing_normalization','existing_growth_rule','existing_profile',
 'existing_fcf_observations','unobserved_input','missing'}
MODEL_INPUTS={
 'forward_pe':('forward_eps','trailing_eps','eps_proxy'),
 'growth_adjusted_pe':('forward_eps','trailing_eps','eps_proxy','earnings_growth'),
 'normalized_pe':('forward_eps','trailing_eps','historical_eps'),
 'normalized_cycle_earnings':('forward_eps','trailing_eps','historical_eps'),
 'normalized_fcf_dcf':('fcf','annual_cashflows','fcf_ttm_info','canonical_shares','cash','debt','revenue'),
 'ev_ebitda':('ebitda','canonical_shares','cash','debt'),
 'revenue_multiple':('revenue','canonical_shares','cash','debt'),
 'price_to_book_roe':('book_value_per_share','tangible_book_value_per_share','roe'),
 'residual_income':('book_value_per_share','tangible_book_value_per_share','roe')}


def source_name(value):
    if isinstance(value,str) and value in SOURCE_NAMES:return value
    if isinstance(value,str) and re.fullmatch(r'ticker\.(get_info|info|fast_info)\.[A-Za-z]+',value):
        return value if value.rsplit('.',1)[-1] in INFO_NUMBERS+INFO_CURRENCIES else 'unobserved_input'
    return 'unobserved_input' if value else 'missing'


def reason_code(value):
    # Engine reasons are controlled identifiers, never provider messages.
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,100}',value) else None


def source_category(raw):
    if raw=='missing':return 'missing'
    if raw=='unobserved_input':return 'unobserved input'
    if raw=='earnings_estimate' or 'earnings_estimate' in raw:return 'Yahoo earnings estimate'
    if raw in ('statement_derived','income_statement_diluted_eps','ni_over_diluted_shares','historical_eps','statement_trailing_eps'):
        return 'statement derived'
    if raw.startswith('ticker.cashflow') or raw.startswith('ticker.balance_sheet'):return 'Yahoo statement'
    if raw=='price/forwardPE' or raw.startswith('fallback') or raw=='trailing_eps':return 'fallback'
    if raw.startswith('ticker.') or raw in ('forwardEps','trailingEps','epsForward','yahoo_trailing_eps'):return 'Yahoo info'
    if raw=='history.Close':return 'Yahoo history'
    return 'existing derived input'


def environment_info():
    from finnhub_admin_diagnostics import is_cloud_runtime
    dependencies={}
    for name in ('yfinance','pandas','streamlit'):
        try:dependencies[name]=version(name)
        except PackageNotFoundError:dependencies[name]='NOT_INSTALLED'
    return {'runtime':'STREAMLIT_CLOUD' if is_cloud_runtime() else 'LOCAL',
            'python':platform.python_version(),'dependencies':dependencies}


def _history(rows):
    keys=('operating_cash_flow','capital_expenditure_raw','capital_expenditure','free_cash_flow',
          'free_cash_flow_reported','free_cash_flow_computed','eps','diluted_eps','shares','net_income')
    return [{'period':period(row.get('period')),'column':period(row.get('column')),
             **{key:numeric(row.get(key)) for key in keys if key in row}}
            for row in (rows or [])[:8] if isinstance(row,dict)]


def build_input_snapshot(ticker, financials, *, price=None):
    from valuation_engine import build_profile, APPLICABILITY_GATES, _fcf_observations, _cap_growth
    f=deepcopy(financials)
    observations=public_observations()
    sources=observations.get('selected_info_sources',{})
    selected=observations.get('selected_fields',{})
    profile=build_profile(ticker,f)
    _,fcf_observations=_fcf_observations(f)
    snapshot={'schema_version':1,'ticker':ticker,'run_timestamp':datetime.now(timezone.utc).isoformat(),
              'environment':environment_info(),'capture_phase':'BEFORE_VALUATE','fields':{},
              'raw_yahoo_observations':observations,'model_applicability':[]}
    fields=snapshot['fields']
    def put(group,name,value,source='existing_normalization',raw_source=None,raw_value=None):
        raw=source_name(raw_source or source)
        status='MISSING' if value is None or value==[] else 'AVAILABLE'
        fields[group+'.'+name]={'value':value,'source':'missing' if status=='MISSING' else source_category(raw),
            'raw_source_name':raw,'raw_value':raw_value,'status':status}
        snapshot.setdefault(group,{})[name]=value
    def info_source(raw_key,fallback='unobserved_input'):
        return sources.get(raw_key,fallback)
    put('market','price',numeric(price),raw_source='history.Close')
    put('market','market_cap',numeric(f.get('market_cap')),raw_source=info_source('marketCap'))
    put('market','quote_currency',currency(f.get('quote_currency')),raw_source=info_source('currency'))
    for key in ('forward_eps','trailing_eps','statement_eps','eps_proxy'):
        raw=source_name(f.get(key+'_source'))
        lookup={'forward_eps':'forwardEps','trailing_eps':'trailingEps'}.get(key)
        effective=info_source(lookup,raw) if raw in ('ticker.info.forwardEps','ticker.info.trailingEps') else raw
        put('eps',key,numeric(f.get(key)),raw_source=effective)
        put('eps',key+'_source',raw if f.get(key+'_source') else None,raw_source=effective)
    for key in ('statement_eps_currency',):put('eps',key,currency(f.get(key)))
    put('eps','eps_proxy_currency_safe',bool(f.get('eps_proxy_currency_safe')))
    shares_sources={'shares_outstanding':info_source('sharesOutstanding'),
        'implied_shares_outstanding':info_source('impliedSharesOutstanding'),
        'market_cap_over_price':'marketCap/price','diluted_average_shares':'diluted_average_shares',
        'canonical_shares':source_name(f.get('canonical_shares_source'))}
    for key,raw in shares_sources.items():put('shares',key,numeric(f.get(key)),raw_source=raw)
    put('shares','canonical_shares_source',source_name(f.get('canonical_shares_source')) if f.get('canonical_shares_source') else None)
    put('shares','share_count_warning',bool(f.get('class_specific_shares') or 'share_count_warning' in (f.get('warnings') or [])))
    annual=f.get('annual_cashflows') or []
    first=annual[0] if annual else {}
    descriptors=f.get('normalized') or {}
    for name,value,raw in (
        ('operating_cash_flow',f.get('operating_cash_flow'),(descriptors.get('operating_cash_flow') or {}).get('source')),
        ('capital_expenditure',f.get('capital_expenditure_raw'), 'ticker.cashflow'),
        ('normalized_capex',f.get('capital_expenditure'),'ticker.cashflow'),
        ('free_cash_flow',first.get('free_cash_flow') if annual else f.get('fcf_ttm_info'), 'ticker.cashflow' if annual else info_source('freeCashflow')),
        ('normalized_fcf',f.get('fcf'),f.get('fcf_source'))):
        put('cash_flow',name,numeric(value),raw_source=raw or 'unobserved_input')
    put('cash_flow','fcf_history',_history(annual),raw_source='ticker.cashflow')
    put('cash_flow','fcf_observation_count',len(fcf_observations),raw_source='existing_fcf_observations')
    for key in ('cash','debt'):
        observation=selected.get(key,{})
        put('balance_sheet',key,numeric(f.get(key)),raw_source=observation.get('source','unobserved_input'),raw_value=observation.get('raw_value'))
    put('growth','earnings_growth',numeric(f.get('earnings_growth')),raw_source=info_source('earningsGrowth'))
    put('growth','revenue_growth',numeric(f.get('revenue_growth')) if f.get('revenue_growth') is not None else
        selected.get('revenue_growth',{}).get('value'),raw_source=info_source('revenueGrowth'))
    put('growth','normalized_growth',_cap_growth(f.get('earnings_growth'),profile.spec,f),raw_source='existing_growth_rule')
    for key in ('quote_currency','financial_currency'):put('currency',key,currency(f.get(key)),raw_source=info_source('currency' if key=='quote_currency' else 'financialCurrency',info_source('financialCurrencyCode')))
    put('currency','currency_mismatch',bool(f.get('currency_mismatch')))
    snapshot['currency']['currency_knowledge']='KNOWN' if currency(f.get('quote_currency')) and currency(f.get('financial_currency')) else 'UNKNOWN'
    for key,value in [('valuation_class',profile.valuation_class),('preferred_models',list(profile.preferred_models)),('excluded_models',list(profile.excluded_models))]:
        put('profile',key,value,raw_source='existing_profile')
    for name in list(profile.preferred_models)+list(profile.excluded_models):
        checked=MODEL_INPUTS.get(name,())
        available=[key for key in checked if f.get(key) is not None and f.get(key)!=[]]
        missing=[key for key in checked if key not in available]
        if name in profile.excluded_models:applicable,reason=False,'excluded_by_valuation_class'
        else:
            gate=APPLICABILITY_GATES.get(name)
            applicable,reason,*_=gate(profile,deepcopy(f)) if gate else (False,'unknown_model')
        snapshot['model_applicability'].append({'model_name':name,'applicable':bool(applicable),'executed':False,
            'reason':reason_code(reason),'inputs_available':available,'inputs_missing':missing,
            'note':'Checked input alternatives; missing entries are not all individually mandatory. Execution has not started.'})
    snapshot['statement_history']=_history(f.get('historical_eps'))
    return snapshot


def failure_trace(result):
    blend=result.get('blend') or {}
    included=blend.get('included_models') or []
    reliability=blend.get('reliability') or {}
    models=[]
    for name,obj in (blend.get('models') or {}).items():
        if name=='peer_comparable':continue
        models.append({'model_name':reason_code(name),'applicable':bool(obj.get('applicable')),
            'executed':bool(obj.get('executed')),'valid':bool(obj.get('valid')),
            'included':name in included,'outlier':bool(obj.get('outlier')),
            'reason':reason_code(obj.get('reason') or obj.get('applicability_reason'))})
    fair=numeric(result.get('fair_value'))
    reason=reason_code(blend.get('reason'))
    mode=reason_code(result.get('valuation_mode'))
    return {'available':fair is not None,'fair_value':fair,'valuation_mode':mode,
            'confidence':reason_code(result.get('confidence')),
            'valid_models':reliability.get('model_count_valid',0),
            'included_model_count':len(included),'included_models':list(included),
            'internal_reason':reason,'models':models,
            'UNAVAILABLE because':None if fair is not None else reason or 'no_internal_fair_value',
            'guard_assessment':'CORRECT_UNAVAILABLE_FOR_CAPTURED_INPUTS' if reason=='forward_and_trailing_eps_unavailable' else
                               'AVAILABLE' if fair is not None else 'REVIEW_MODEL_REASONS',
            'peer':'diagnostic only / unavailable' if (result.get('peer_diagnostics') or {}).get('status')!='AVAILABLE' else 'diagnostic only / available'}


def finalize_snapshot(snapshot,result,finnhub=None):
    snapshot=deepcopy(snapshot)
    trace=failure_trace(result)
    snapshot['valuation_failure_trace']=trace
    actual={model['model_name']:model for model in trace['models']}
    for entry in snapshot['model_applicability']:
        entry['pre_valuation_applicable']=entry['applicable']
        entry['pre_valuation_reason']=entry['reason']
        if entry['model_name'] in actual:entry.update(actual[entry['model_name']])
    fh=finnhub or {}
    allowed_statuses={'AVAILABLE','NO_DATA','NOT_CONFIGURED','NOT_ENTITLED','RATE_LIMIT','NETWORK_ERROR','INVALID_RESPONSE','NOT_TESTED'}
    fetched=fh.get('fetched_at')
    try:fetched=datetime.fromisoformat(fetched.replace('Z','+00:00')).isoformat() if isinstance(fetched,str) else None
    except ValueError:fetched=None
    snapshot['finnhub_diagnostic']={'source':'Finnhub basic financials',
        'status':fh.get('status') if fh.get('status') in allowed_statuses else 'INVALID_RESPONSE',
        'fetched_at':fetched,
        'fields':{key:numeric((fh.get('fields') or {}).get(key)) for key in ('epsTTM','forwardPE','peTTM','marketCapitalization')},
        'used_for_valuation':False}
    snapshot['hypotheses']=assess_hypotheses(snapshot)
    return snapshot


def assess_hypotheses(snapshot):
    f=snapshot['fields'];raw=snapshot.get('raw_yahoo_observations') or {}
    info=[p.get('fields',{}) for p in raw.get('info_paths',{}).values()]
    observed=bool(info)
    def yahoo_missing(key):return not any(row.get(key) is not None for row in info)
    fh=snapshot.get('finnhub_diagnostic') or {};ff=fh.get('fields') or {}
    return {
        'A_yahoo_forward_trailing':{'evidence':'OBSERVED_YFINANCE_INFO_PATHS' if observed else 'NOT_CAPTURED',
            'forwardEps_missing':yahoo_missing('forwardEps') if observed else None,
            'trailingEps_missing':yahoo_missing('trailingEps') if observed else None,
            'note':'Observed get_info/info paths; no inference about unobserved Yahoo HTTP endpoints.'},
        'B_yahoo_missing_finnhub_available':{'finnhub_status':fh.get('status'),
            'epsTTM_available':numeric(ff.get('epsTTM')) is not None,
            'forwardPE_available':numeric(ff.get('forwardPE')) is not None,'used_for_valuation':False,
            'yahoo_trailing_missing_and_finnhub_epsTTM_available':yahoo_missing('trailingEps') and numeric(ff.get('epsTTM')) is not None if observed else None,
            'yahoo_forward_missing_and_finnhub_forwardPE_available':yahoo_missing('forwardEps') and numeric(ff.get('forwardPE')) is not None if observed else None,
            'fallback_decision':'NOT_AUTHORIZED_THIS_ROUND'},
        'C_implied_shares':{'value':f['shares.implied_shares_outstanding']['value']},
        'D_fcf_history':{'observation_count':f['cash_flow.fcf_observation_count']['value'],'local_comparison':'REQUIRES_MATCHING_LOCAL_SNAPSHOT'},
        'E_statement_rows_periods':{'observed':raw.get('statements',{}),'local_comparison':'REQUIRES_MATCHING_LOCAL_SNAPSHOT'},
        'F_currency_paths':{'quote_currency':f['currency.quote_currency']['value'],
            'financial_currency':f['currency.financial_currency']['value'],
            'currency_knowledge':snapshot['currency']['currency_knowledge'],
            'currency_mismatch':f['currency.currency_mismatch']['value']},
        'G_proxy_guard':snapshot.get('valuation_failure_trace',{}).get('guard_assessment','PENDING_VALUATION')}


def compare_financial_snapshots(local,cloud):
    if local.get('ticker')!=cloud.get('ticker'):raise ValueError('Compare snapshots for the same ticker.')
    critical={'eps.forward_eps','eps.trailing_eps','shares.canonical_shares','currency.quote_currency','currency.financial_currency'}
    rows=[]
    def compare(field,a,b,sa,sb):
        same=a==b and sa==sb
        delta=b-a if isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool) else None
        severity='SAME' if same else 'CRITICAL' if field in critical else 'MATERIAL' if field.startswith(('eps.','shares.','cash_flow.','balance_sheet.','profile.','statement.','models.')) else 'MINOR'
        rows.append(dict(field=field,local_value=a,cloud_value=b,local_source=sa,cloud_source=sb,
                         difference=0 if same else delta if delta is not None else 'SOURCE_CHANGED' if a==b else 'VALUE_CHANGED',severity=severity))
    for key in sorted(set(local.get('fields',{}))|set(cloud.get('fields',{}))):
        a=local.get('fields',{}).get(key,{})
        b=cloud.get('fields',{}).get(key,{})
        compare(key,a.get('value'),b.get('value'),a.get('raw_source_name'),b.get('raw_source_name'))
    for stage in ('cashflow','income_stmt','balance_sheet'):
        a=(local.get('raw_yahoo_observations') or {}).get('statements',{}).get(stage,[])
        b=(cloud.get('raw_yahoo_observations') or {}).get('statements',{}).get(stage,[])
        compare('statement.'+stage,a,b,'observed Yahoo paths','observed Yahoo paths')
    compare('models.applicability',local.get('model_applicability'),cloud.get('model_applicability'),'existing model gates','existing model gates')
    for key in ('valid_models','included_models','internal_reason','available'):
        compare('models.'+key,(local.get('valuation_failure_trace') or {}).get(key),
                (cloud.get('valuation_failure_trace') or {}).get(key),'internal engine','internal engine')
    return rows


def _controlled_baseline_available(result):
    """Test prerequisite only; production fallback eligibility is untouched."""
    f=result.get('financials') or {}
    shares=numeric(f.get('canonical_shares'))
    fair=numeric(result.get('fair_value'))
    return bool(currency(f.get('quote_currency')) and currency(f.get('financial_currency'))
                and shares is not None and shares>0 and f.get('canonical_shares_source')
                and f.get('split_context_known') is True and not f.get('currency_mismatch')
                and fair is not None and fair>0
                and result.get('valuation_mode') in ('STANDARD','LOW_CONFIDENCE'))


def _baseline_display(result):
    f=result.get('financials') or {}
    return {'source_status':'live','fair_value':result.get('fair_value'),
            'valuation_mode':result.get('valuation_mode'),
            **{key:f.get(key) for key in ('quote_currency','financial_currency','canonical_shares',
                'canonical_shares_source','split_context_known','last_split_date','last_split_factor')}}


def _controlled_eps_simulation(baseline):
    """No loaders/providers: simulate exclusively from the accepted live input.

    Only the three EPS values and the explicit test flag differ. In particular,
    do not re-normalize, re-resolve shares, fetch prices or attach external data.
    """
    from valuation_engine import valuate
    from market_reference import apply_reference_display_policy
    f=deepcopy(baseline['financials'])
    for key in ('forward_eps','trailing_eps','eps_proxy'):
        f[key]=None
    f['simulated_missing_input']=True
    snapshot=build_input_snapshot(baseline['ticker'],deepcopy(f),price=baseline.get('price'))
    blend=valuate(baseline['ticker'],f,volatility=baseline.get('volatility_1y'))
    result={'ticker':baseline['ticker'],'price':baseline.get('price'),'financials':f,'blend':blend,
            'valuation_class':baseline.get('valuation_class'),'model_version':baseline.get('model_version'),
            'confidence':blend.get('confidence'),'source_status':'live','simulated_missing_input':True,
            'fair':blend.get('fair'),'fair_low':blend.get('fair_low'),'fair_high':blend.get('fair_high'),
            **{key:blend.get(key) for key in ('fair_value','blended_low','blended_mid','blended_high')},
            'reliability_score':(blend.get('reliability') or {}).get('reliability_score'),
            'zones':None,'exit_zone':None,'peer_diagnostics':{'mode':'diagnostic','status':'NOT_TESTED'}}
    return snapshot,apply_reference_display_policy(result)


def capture_financial_diagnostic(ticker, *, history_loader=None, fundamentals_loader=None, finnhub_provider=None,
                                 simulate_missing_input=False, result_sink=None):
    if ticker not in TICKERS:raise ValueError('Unsupported diagnostic ticker.')
    from analysis_service import analyze_ticker
    snapshots=[]
    capture_errors=[]
    with observe_financial_inputs():
        result=analyze_ticker(ticker,history_loader=history_loader,fundamentals_loader=fundamentals_loader,
                              peer_mode='diagnostic',financial_diagnostic_sink=lambda snapshot:snapshots.append(deepcopy(snapshot)),
                              financial_diagnostic_error_sink=capture_errors.append)
        baseline_display=_baseline_display(result) if simulate_missing_input else None
        if simulate_missing_input and (not snapshots or not _controlled_baseline_available(result)):
            # Never call result_sink (or read a cached valuation) after an
            # incomplete baseline. It is not a controlled simulation.
            report=finalize_snapshot(snapshots[0],result) if snapshots else {'ticker':ticker}
            report.update(simulation_requested=True,simulation_aborted=True,
                          simulated_missing_input=False,baseline_valuation=baseline_display)
            return report
        if simulate_missing_input:
            snapshot,result=_controlled_eps_simulation(result)
            snapshots=[snapshot]
    if not snapshots:
        if capture_errors:
            raise FinancialDiagnosticFailure('PRE_VALUATION_SNAPSHOT',public_error=capture_errors[0])
        stage='LOAD_HISTORY' if any(e.get('stage')=='history' for e in result.get('errors',[])) else 'PRE_VALUATION_SNAPSHOT'
        raise FinancialDiagnosticFailure(stage,public_error={'stage':stage,'category':'NO_SNAPSHOT','code_locations':[]})
    try:
        from finnhub_service import get_finnhub_provider
        provider=finnhub_provider or get_finnhub_provider()
        finnhub=provider.get_diagnostic_basic_financials(ticker)
    except Exception:
        finnhub={'status':'NETWORK_ERROR','fields':{},'used_for_valuation':False}
    try:
        report = finalize_snapshot(snapshots[0],result,finnhub)
        if simulate_missing_input:
            report['simulated_missing_input'] = True
            report['simulation_requested'] = True
            report['baseline_valuation'] = baseline_display
        if result_sink is not None:
            report['valuation'] = result_sink(deepcopy(result))
        return report
    except Exception as exc:
        raise FinancialDiagnosticFailure('FINALIZE_REPORT',exc) from None


def snapshot_rows(snapshot):
    return [{'Field':field,'Value':entry.get('value'),'Source':entry.get('source'),
             'Status':entry.get('status')} for field,entry in snapshot.get('fields',{}).items()]


def snapshot_json(snapshot,redactions=()):
    from collections.abc import Mapping
    import numpy as np
    secrets=[secret for secret in redactions if isinstance(secret,str) and len(secret)>3]
    def clean(value):
        if isinstance(value,np.generic):return clean(value.item())
        if isinstance(value,str):
            for secret in secrets:value=value.replace(secret,'[REDACTED]')
            return value
        if isinstance(value,Mapping):return {clean(key):clean(item) for key,item in value.items()}
        if isinstance(value,(list,tuple)):return [clean(item) for item in value]
        if isinstance(value,(int,float)) and str(value) in secrets:return None
        return value
    return json.dumps(clean(snapshot),ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
