"""Temporary Cloud production snapshot export; request-local observation only."""
from copy import deepcopy
from datetime import date,datetime,timezone
import csv
import io
import json
import math
from numbers import Real,Integral
import threading
import time
from uuid import uuid4

import analysis_service
import valuation_engine as engine
from valuation_calibration_audit import clone,TICKERS
from finnhub_admin_diagnostics import is_cloud_runtime,verified_admin
from financial_forensics_admin import _secret_strings
from financial_forensics import snapshot_json
from calibration_snapshot_guard import calibration_eligibility,batch_eligibility,reference_snapshot
from model_family_governance import governance_audit
from experimental_family_blend import family_blend_experiment,experiment_summary
from independent_evidence_governance import independent_evidence_audit,EXPORT_FIELDS

_LOCK=threading.Lock()
_LAST_RUN={}


def readonly_display(live,load_snapshot):
    """Exact production resolver, with a no-op writer and defensive read copy."""
    from last_reliable_valuation import resolve_live_result
    return resolve_live_result(deepcopy(live),lambda:deepcopy(load_snapshot()),lambda result:None)


def capture_analysis(ticker,*,history_loader,fundamentals_loader,display_resolver=None):
    observed={}
    def outliers(models):
        observed['models_before_outlier']=deepcopy(models)
        result=engine._flag_outliers(models)
        observed['models_after_outlier']=deepcopy(result)
        return result
    def run_model(name,profile,financials,**kwargs):
        result=engine.run_model(name,profile,financials,**kwargs)
        gate=kwargs.get('_gate_result')
        observed.setdefault('applicability',{})[name]={
            'model_name':name,'applicable':gate[0] if gate else result.get('applicable'),
            'applicability_reason':gate[1] if gate else result.get('applicability_reason'),
            'input_safe':gate[0] if gate else result.get('applicable'),
            'input_safe_basis':'production applicability gate; not a separate diagnostic safety rule',
            'warnings':deepcopy(result.get('warnings',[])),
            'gate_inputs':deepcopy(gate[3]) if gate else None}
        return result
    runner=clone(engine.valuate,_flag_outliers=outliers,run_model=run_model)
    def valuate(t,financials,**kwargs):
        observed['normalized_inputs']=deepcopy(financials)
        observed['profile']=engine.build_profile(t,financials)
        return runner(t,financials,**kwargs)
    # Same function code, loaders and normalization. Private globals do not
    # monkeypatch shared services or invoke a second valuation implementation.
    analyze=clone(analysis_service.analyze_ticker,valuate=valuate,
                  _attach_peer_diagnostics=lambda result,*args,**kwargs:result)
    live=analyze(ticker,history_loader=history_loader,fundamentals_loader=fundamentals_loader,
                 peer_mode='diagnostic')
    displayed=display_resolver(deepcopy(live)) if display_resolver else deepcopy(live)
    return project_snapshot(live,displayed,observed)


def project_snapshot(live,displayed,observed):
    live_blend=deepcopy(live.get('blend') or {})
    display_blend=deepcopy(displayed.get('blend') or {})
    financials=deepcopy(observed.get('normalized_inputs',live.get('financials') or {}))
    normalized_inputs=deepcopy(financials)
    for key in ('forward_eps','forward_eps_source','trailing_eps','trailing_eps_source','eps_proxy','eps_proxy_source',
                'revenue','revenue_growth','ebitda','free_cash_flow','net_income','operating_margin',
                'cash','debt','market_cap','canonical_shares','canonical_shares_source','quote_currency','financial_currency'):
        financials.setdefault(key,None)
    profile=observed.get('profile')
    spec=deepcopy(profile.spec) if profile else {}
    weights=profile.model_weights if profile else {}
    included=display_blend.get('included',[])
    excluded={item['name']:item for item in display_blend.get('excluded',[])}
    models=[]
    for name,model in display_blend.get('models',{}).items():
        item=deepcopy(model)
        mid=engine.fnum(model.get('mid'))
        weight=engine.fnum(display_blend.get('weights_used',{}).get(name)) or 0.
        inputs=deepcopy(model.get('inputs') or {})
        before=(observed.get('models_before_outlier') or {}).get(name,{})
        item.update(model_name=name,model_mid=mid,included=name in included,
            excluded_reason=excluded.get(name,{}).get('reason'),base_weight=weights.get(name,1.),
            normalized_weight=weight,contribution_to_blended_mid=mid*weight if mid is not None and weight else 0.,
            raw_fair_value=before.get('mid') if displayed.get('source_status','live')=='live' else None,inputs_used=inputs,
            assumptions_used=deepcopy(inputs))
        item['growth_provenance']={key:inputs.get(key) for key in (
            'forward_eps_growth','revenue_growth','earnings_growth','growth_used','dcf_growth',
            'terminal_growth','margin_assumption','fair_pe','pe_low','pe_high')}
        capital_keys=('cash','debt','enterprise_value','equity_value','shares')
        item['capital_structure']={key:inputs.get(key,'not_used') for key in capital_keys}
        cash,debt=engine.fnum(inputs.get('cash')),engine.fnum(inputs.get('debt'))
        item['capital_structure']['net_debt']=debt-cash if cash is not None and debt is not None else 'not_used'
        models.append(item)
    applicability=deepcopy(observed.get('applicability',{}))
    for name,model in live_blend.get('models',{}).items():
        if name not in applicability:
            applicability[name]={'model_name':name,'applicable':model.get('applicable'),
                'applicability_reason':model.get('reason') or model.get('applicability_reason'),
                'input_safe':None,'warnings':deepcopy(model.get('warnings',[]))}
    fair=engine.fnum(display_blend.get('fair'))
    total=sum(model['contribution_to_blended_mid'] for model in models)
    match=abs(total-fair)<=max(1e-6,abs(fair)*1e-9) if fair is not None else None
    if match is False:raise ValueError('Captured contribution invariant failed')
    # Extend a COPY of the production blend, preserving its model-map schema.
    display_blend['models']={item['model_name']:item for item in models}
    display_blend.update(low=display_blend.get('fair_low'),mid=fair,high=display_blend.get('fair_high'),
        mode=displayed.get('valuation_mode'),contribution_sum=total,contribution_sum_matches=match)
    source=displayed.get('source_status','live')
    return {'ticker':live['ticker'],'generated_at':datetime.now(timezone.utc).isoformat(),
        'analysis_generated_at':live.get('valuation_run_at'),'source_status':source,
        'current_price':live.get('price'),'fair_value':displayed.get('fair_value'),
        'production_analysis_fair':displayed.get('fair_value'),'financials':financials,
        'normalized_inputs':normalized_inputs,'applicability':applicability,'models':models,
        'blend':display_blend,'live_blend':live_blend,
        'models_before_outlier':observed.get('models_before_outlier',{}),
        'models_after_outlier':observed.get('models_after_outlier',{}),
        'outlier_and_applicability_scope':'current live execution; cached display models may differ',
        'profile_assumptions':spec,'volatility_1y':live.get('volatility_1y'),
        'calculated_at':displayed.get('calculated_at'),
        'input_blend_alignment':'SAME_LIVE_EXECUTION' if source=='live' else
            'CACHED_DISPLAY_WITH_CURRENT_LIVE_INPUTS_DO_NOT_CALIBRATE',
        'capture_status':'COMPLETE' if observed.get('normalized_inputs') is not None and live_blend else 'INCOMPLETE',
        'peer_mode':'diagnostic','peer_in_blend':'peer_comparable' in included}


def _public(value):
    """Defense in depth for unexpected credential-bearing normalized fields."""
    if isinstance(value,dict):
        return {str(k):_public(v) for k,v in value.items() if not any(word in str(k).lower()
            for word in ('token','secret','cookie','password','api_key','authorization','credential'))}
    if isinstance(value,(tuple,list)):return [_public(v) for v in value]
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,(str,bool)) or value is None:return value
    if isinstance(value,Real):return int(value) if isinstance(value,Integral) else float(value) if math.isfinite(value) else None
    return None  # Never stringify unexpected objects/provider clients.


def run_batch(client,user_id,secrets,*,history_loader,fundamentals_loader,display_resolver=None,reference_loader=None):
    if not is_cloud_runtime() or not verified_admin(client,user_id,secrets.get('ADMIN_EMAIL')):
        raise PermissionError('Cloud admin only')
    if not _LOCK.acquire(blocking=False):raise RuntimeError('Busy')
    try:
        if time.monotonic()-_LAST_RUN.get(str(user_id),-1e12)<30:raise RuntimeError('Cooldown')
        _LAST_RUN[str(user_id)]=time.monotonic()
        batch_id=str(uuid4());stamp=datetime.now(timezone.utc).isoformat()
        stocks=[]
        for ticker in TICKERS:
            try:
                stock=capture_analysis(ticker,history_loader=history_loader,
                    fundamentals_loader=fundamentals_loader,display_resolver=display_resolver)
            except Exception:
                stock={'ticker':ticker,'capture_status':'FAILED','analysis_generated_at':datetime.now(timezone.utc).isoformat()}
            reference=None
            reference_status='NOT_REQUESTED'
            if reference_loader:
                try:
                    reference=reference_snapshot(reference_loader(ticker),ticker)
                    reference_status='AVAILABLE' if reference else 'NO_DATA'
                except Exception:reference_status='READ_UNAVAILABLE'
            stock.update(calibration_eligibility(stock,reference))
            stock['correlation_cross_family_governance']=governance_audit(stock)
            stock['experimental_family_blend']=family_blend_experiment(stock)
            stock['independent_evidence_governance']=independent_evidence_audit(stock)
            stock['reference_snapshot_read_status']=reference_status
            stock.update(batch_id=batch_id,batch_generated_at=stamp)
            stocks.append(stock)
        report={'schema_version':'v4.5.0','batch_id':batch_id,'batch_generated_at':stamp,'generated_at':stamp,
            'mode':'read_only_diagnostic','execution':'serial single Cloud batch; underlying cached input ages may differ',
            'stocks':stocks}
        report.update(batch_eligibility(stocks,TICKERS))
        return json.loads(snapshot_json(_public(report),_secret_strings(secrets)))
    finally:_LOCK.release()


def csv_payload(report):
    buffer=io.StringIO(newline='')
    summary_fields=('effective_independent_model_count','dominant_family','dominant_family_weight',
        'family_concentration_status','cross_family_status','cross_family_spread_pct','growth_overlap_risk',
        'governance_classification','governance_review_status')
    fields=('ticker','model_name','model_mid','base_weight','normalized_weight','contribution_to_blended_mid','included','excluded_reason')+summary_fields
    experimental_fields=tuple('experimental_family_blend.'+key for key in ('A_fair','B_fair','C_fair',
        'A_difference_pct','B_difference_pct','C_difference_pct','family_weighting_sensitivity','family_weighting_governance','experiment_status'))
    evidence_fields=tuple('independent_evidence_governance.'+key for key in EXPORT_FIELDS)
    fields+=experimental_fields+evidence_fields
    writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
    for stock in report['stocks']:
        governance=stock.get('correlation_cross_family_governance',{})
        for model in stock.get('models',[]):writer.writerow({'ticker':stock['ticker'],
            **{k:model.get(k) for k in fields if k!='ticker' and k not in summary_fields and k not in experimental_fields and k not in evidence_fields},
            **{k:governance.get(k) for k in summary_fields},
            **{k:experiment_summary(stock).get(k.split('.',1)[1]) for k in experimental_fields},
            **{k:stock.get('independent_evidence_governance',{}).get(k.split('.',1)[1]) for k in evidence_fields}})
    return buffer.getvalue().encode('utf-8-sig')


def render_snapshot_export(st,client,user_id,*,history_loader,fundamentals_loader,display_resolver=None,reference_loader=None):
    if not is_cloud_runtime() or not verified_admin(client,user_id,st.secrets.get('ADMIN_EMAIL')):
        st.session_state.pop('_v45_export_open',None);st.session_state.pop('_v45_export_result',None)
        st.error('无权访问 V4.5 估值结构导出。');return
    st.subheader('V4.5 估值结构导出')
    st.caption('同批串行生产分析 · 只读 · 不写快照或更新 Last Reliable · Peer diagnostic only')
    if st.button('返回',key='v45_export_back'):
        st.session_state.pop('_v45_export_open',None);st.rerun()
    if st.button('运行五股生产分析快照',key='v45_export_run'):
        st.session_state.pop('_v45_export_result',None)
        try:
            with st.spinner('正在捕获五股生产分析…'):
                report=run_batch(client,user_id,st.secrets,history_loader=history_loader,
                    fundamentals_loader=fundamentals_loader,display_resolver=display_resolver,reference_loader=reference_loader)
            st.session_state['_v45_export_result']={'owner':str(user_id),'report':report}
        except PermissionError:st.error('无权运行。')
        except RuntimeError:st.warning('诊断正在运行或过于频繁，请稍后重试。')
        except Exception:st.error('导出未完成；未输出异常原文或凭据。')
    saved=st.session_state.get('_v45_export_result')
    if not saved:return
    if saved.get('owner')!=str(user_id):
        st.session_state.pop('_v45_export_result',None);return
    report=saved['report']
    st.markdown('**Calibration Batch Status**')
    st.write(report.get('batch_calibration_eligibility','INELIGIBLE'))
    if report.get('batch_calibration_eligibility')!='ELIGIBLE':
        st.warning('本批次仅用于输入降级诊断，不应用于估值校准。')
        for reason in report.get('batch_reasons',[]):
            st.write(str(reason['ticker'])+' — '+reason['status']+'：'+', '.join(reason['reasons']))
    st.caption('Batch: '+report['batch_id']+' · '+report['batch_generated_at'])
    st.dataframe([{k:stock.get(k) for k in ('ticker','fair_value','source_status','capture_status','input_blend_alignment',
        'calibration_eligibility','calibration_eligibility_reasons','transient_input_degradation')}
        for stock in report['stocks']],hide_index=True,use_container_width=True)
    st.info('如显示 cached_last_reliable，当前 live inputs 与历史 blend 分开导出，不可将两者用于同一轮校准。')
    st.markdown('**Correlation & Cross-Family Governance**')
    st.caption('结构性 dependency overlap，不是统计相关系数；被 outlier 排除的有效跨家族信号仍参与诊断。生产估值保持不变。')
    summary_fields=('model_count_included','effective_independent_model_count','dominant_family',
        'dominant_family_weight','family_concentration_status','cross_family_status',
        'cross_family_spread_pct','growth_overlap_risk','capital_structure_flags','governance_classification')
    st.dataframe([{'ticker':stock['ticker'],**{k:stock.get('correlation_cross_family_governance',{}).get(k) for k in summary_fields}}
        for stock in report['stocks']],hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        with st.expander(stock['ticker']+' — family / pair diagnostics'):
            st.json(stock.get('correlation_cross_family_governance',{}))
    st.markdown('**Family-Level Blend Experiment**')
    st.caption('EXPERIMENT ONLY · 不修改生产 fair、权重或 outlier · 保留可执行的冲突 family。')
    st.dataframe([experiment_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        with st.expander(stock['ticker']+' — experimental family members / weights'):
            st.json(stock.get('experimental_family_blend',{}))
    st.markdown('**Independent Evidence & Family Suppression**')
    st.caption('DIAGNOSTIC ONLY · Strategy C 仅为 conflict-preserving diagnostic reference；不改变生产 confidence、reliability、fair 或 zones。')
    st.dataframe([{'ticker':stock['ticker'],**{k:stock.get('independent_evidence_governance',{}).get(k) for k in EXPORT_FIELDS}}
        for stock in report['stocks']],hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        evidence=stock.get('independent_evidence_governance',{})
        if 'CASH_FLOW_INTRINSIC' in evidence.get('suppressed_families',[]):
            st.warning(stock['ticker']+' — Independent cash-flow family suppressed')
        with st.expander(stock['ticker']+' — independent evidence governance'):
            st.json(evidence)
    st.download_button('下载 V4.5 JSON',snapshot_json(report),'v45_cloud_production_analysis.json','application/json',key='v45_export_json')
    st.download_button('下载模型贡献 CSV',csv_payload(report),'v45_cloud_model_contributions.csv','text/csv',key='v45_export_csv')
