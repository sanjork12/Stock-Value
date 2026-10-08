"""Snapshot-only calibration forensics. No network, database or production edits."""
from copy import deepcopy
from itertools import combinations
from types import FunctionType
import math

import valuation_engine as engine
from financial_normalization import NormalizedFinancialInputs

TICKERS=('GOOG','MSFT','ORCL','NVDA','AMZN')
KEYS=('forward_eps','forward_eps_source','trailing_eps','trailing_eps_source','eps_proxy',
      'eps_proxy_source','quote_currency','financial_currency','currency_mismatch',
      'canonical_shares','canonical_shares_source','shares_severe_mismatch','market_cap',
      'price','cash','debt','fcf','fcf_method','earnings_growth','revenue_growth','ebitda','revenue')


def clone(function, **overrides):
    namespace=dict(function.__globals__);namespace.update(overrides)
    fn=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__)
    fn.__kwdefaults__=function.__kwdefaults__
    return fn


def replay(ticker,financials,volatility=None,*,multiple_factor=1.):
    """Isolated Forward PE multiple shock; full production gates/blend rerun.

    Only this primitive's realized PE low/mid/high change in the local runner.
    Growth PE floors, other model assumptions and module globals do not change.
    """
    runners=dict(engine.MODEL_RUNNERS)
    original=runners['forward_pe']
    def shocked(profile,f):
        result=deepcopy(original(profile,f))
        if result.get('valid'):
            for key in ('low','mid','high'):result[key]*=multiple_factor
            for key in ('pe_low','pe_high'):
                if key in result.get('inputs',{}):result['inputs'][key]*=multiple_factor
        return result
    if multiple_factor!=1:runners['forward_pe']=shocked
    run=clone(engine.run_model,MODEL_RUNNERS=runners)
    valuate=clone(engine.valuate,run_model=run)
    return valuate(ticker,deepcopy(financials),volatility=volatility,peer_mode='diagnostic')


def sensitivity(ticker,financials,volatility=None):
    rows=[]
    for axis,factors in (('forward_eps',(.9,1.,1.1)),('earnings_growth',(.8,1.,1.2)),
                         ('forward_pe_target_multiple',(.9,1.,1.1))):
        for factor in factors:
            f=deepcopy(financials)
            value=engine.fnum(f.get(axis))
            if axis!='forward_pe_target_multiple':
                if value is None:
                    rows.append({'axis':axis,'factor':factor,'status':'MISSING_BASE_INPUT','fair':None})
                    continue
                f[axis]=value*factor
            blend=replay(ticker,f,volatility,multiple_factor=factor if axis=='forward_pe_target_multiple' else 1.)
            rows.append({'axis':axis,'factor':factor,'status':blend.get('valuation_mode'),
                         'fair':blend.get('fair'),'included':blend.get('included'),
                         'confidence':blend.get('confidence'),'excluded':blend.get('excluded')})
    base=replay(ticker,financials,volatility).get('fair')
    for row in rows:
        row['delta']=row['fair']-base if row['fair'] is not None and base is not None else None
        row['delta_pct']=row['delta']/base*100 if row['delta'] is not None and base else None
    return {'scope':{'forward_eps':'normalized forward EPS only; implied forward/trailing growth is recomputed',
        'earnings_growth':'observed earnings_growth input only; class growth caps, DCF fixed growth unchanged',
        'forward_pe_target_multiple':'Forward PE primitive realized multiple only; full gates/outliers rerun'},
        'base_fair':base,'runs':rows}


def growth_audit(blend):
    included=blend.get('included',[])
    eps_pair=all(k in included for k in ('forward_pe','growth_adjusted_pe'))
    entries=[]
    for model_id in included:
        model=blend['models'][model_id];inputs=model.get('inputs') or {}
        if model_id=='forward_pe':signals=['EPS forecast or documented trailing proxy','fixed ticker/class PE; no dynamic growth expansion']
        elif model_id=='growth_adjusted_pe':signals=['same EPS basis as Forward PE','earnings_growth','forward/trailing EPS implied growth','fixed normalized growth base/cap']
        elif model_id=='normalized_fcf_dcf':signals=['fixed class/ticker FCF growth','fixed terminal growth; not live earnings_growth']
        else:signals=['model-specific inputs; inspect primitive']
        entries.append({'model':model_id,'growth_enters_via':signals,
                        'eps_source':inputs.get('eps_source'),'growth_used':inputs.get('growth_used'),
                        'dcf_growth':inputs.get('dcf_growth'),'terminal_growth':inputs.get('terminal_growth'),
                        'margin_expansion':'no explicit forecast margin-expansion input in these primitives'})
    correlations=[]
    for a,b in combinations(included,2):
        pair={a,b}
        level='HIGH_CORRELATION' if pair=={'forward_pe','growth_adjusted_pe'} else 'MEDIUM_CORRELATION'
        correlations.append({'models':[a,b],'qualitative_correlation':level,
            'basis':'shared EPS and implied EPS growth' if level=='HIGH_CORRELATION' else
                    'shared company/cycle exposure; DCF growth is fixed, no measured return correlation'})
    return {'risk':'DOUBLE_COUNT_RISK' if eps_pair else 'LOW',
            'risk_interpretation':'structural shared signal, not proven bias or literal summation of independent forecasts',
            'channels':entries,'correlations':correlations}


def audit_analysis(ticker,result):
    """Caller supplies one captured normalized input + recorded internal blend.

    Snapshot replay must agree before sensitivities are accepted. Cached final
    values and live failed inputs must not be treated as one historical result.
    """
    if result.get('source_status','live')!='live':
        return {'ticker':ticker,'status':'NEEDS_ORIGINAL_RELIABLE_INPUTS','reason':'cached display cannot be paired with current live inputs'}
    from calibration_snapshot_guard import calibration_eligibility
    governance=calibration_eligibility(result,result.get('reference_snapshot'))
    if result.get('calibration_eligibility',governance['calibration_eligibility'])!='ELIGIBLE' or governance['calibration_eligibility']!='ELIGIBLE':
        return {'ticker':ticker,'status':'CALIBRATION_INPUT_INELIGIBLE',
                **governance,'sensitivity':None,'models':None,
                'reason':'Degraded data-state may be diagnosed but must not be used for calibration.'}
    f=NormalizedFinancialInputs(deepcopy(result.get('normalized_inputs',result['financials'])))
    blend=deepcopy(result['blend'])
    profile=engine.build_profile(ticker,f)
    excluded={x['name']:x for x in blend.get('excluded',[])}
    rows=[]
    for name,model in blend.get('models',{}).items():
        weight=engine.fnum(blend.get('weights_used',{}).get(name)) or 0.
        raw=engine.run_model(name,profile,deepcopy(f)) if model.get('executed') else model
        mid=engine.fnum(model.get('mid'))
        rows.append({'model_name':name,'display_name':model.get('name'),
            'applicable':model.get('applicable'),'valid':model.get('valid'),
            'included':name in blend.get('included',[]),'excluded_reason':excluded.get(name,{}).get('reason'),
            'input_metrics':deepcopy(model.get('inputs') or {}),'raw_fair_value':raw.get('mid'),
            'low':model.get('low'),'mid':mid,'high':model.get('high'),
            'weight_before_normalization':profile.model_weights.get(name,1.),
            'weight_after_normalization':weight,'contribution_to_blended_mid':mid*weight if mid is not None and weight else 0.,
            'outlier_excluded':bool(model.get('outlier')),'outlier_reason':model.get('reason') if model.get('outlier') else None})
    fair=engine.fnum(blend.get('blended_mid',blend.get('fair')))
    total=sum(r['contribution_to_blended_mid'] for r in rows)
    matches=math.isclose(total,fair,rel_tol=1e-9,abs_tol=1e-6) if fair is not None else None
    if matches is False:raise ValueError('Contribution sum does not match captured blend: '+ticker)
    computed=replay(ticker,f,result.get('volatility_1y'))
    same=(computed.get('included')==blend.get('included') and computed.get('weights_used')==blend.get('weights_used')
          and all(all(computed.get('models',{}).get(k,{}).get(field)==v.get(field)
                      for field in ('valid','applicable','low','mid','high','inputs','reason','outlier'))
                  for k,v in blend.get('models',{}).items())
          and computed.get('fair')==blend.get('fair'))
    direction=[]
    for row in rows:
        if fair and row['included'] and row['mid'] is not None:
            direction.append({'model':row['model_name'],'position':'BELOW_BLEND' if row['mid']<fair else 'ABOVE_BLEND' if row['mid']>fair else 'AT_BLEND',
                              'weighted_offset_from_blend':(row['mid']-fair)*row['weight_after_normalization']})
    return {'ticker':ticker,'status':'CAPTURE_REPLAY_MATCH' if same else 'CAPTURE_REPLAY_MISMATCH',
        'profile':profile.to_dict(),'assumptions':deepcopy(profile.spec),'inputs':{k:f.get(k) for k in KEYS},
        'fair':fair,'confidence':blend.get('confidence'),'dispersion':blend.get('dispersion'),
        'models':rows,'waterfall_sum':total,'waterfall_matches':matches,'relative_model_direction':direction,
        'growth_audit':growth_audit(blend),'sensitivity':sensitivity(ticker,f,result.get('volatility_1y')) if same else None,
        'bias_direction':'NOT_ESTABLISHED','root_cause_status':'REQUIRES_INPUT_AND_ASSUMPTION_VALIDATION',
        'structural_candidates':['MODEL_CORRELATION','EPS_FORECAST','MULTIPLE_ASSUMPTION'] if
            {'forward_pe','growth_adjusted_pe'}.issubset(blend.get('included',[])) else ['MODEL_APPLICABILITY'],
        'note':'Observed model contributions establish arithmetic drivers, not correctness of forecasts or economic bias.'}
