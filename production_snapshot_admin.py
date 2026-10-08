"""Temporary Cloud production snapshot export; request-local observation only."""
from enterprise_family_suitability import attach_report, audit_export, csv_export, summary as suitability_summary
from copy import deepcopy
from production_input_wiring import build_trace, summary as wiring_summary
from enterprise_evidence import observe_enterprise_statements, evidence_snapshot, complete_report, export_report as evidence_export, export_csv as evidence_csv, summary as evidence_summary
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
from production_reliability_governance import VERSION as GOVERNANCE_VERSION
from capital_structure_overlay import capital_overlay,overlay_summary,valid_range
from enterprise_aware_experiment import enterprise_experiment,enterprise_summary

_LOCK=threading.Lock()
_LAST_RUN={}
ENTERPRISE_WIRING_VERSION='v4.8.wiring.1'


def wired_enterprise_result(stock,*,batch_id=None,existing=None):
    """Use only this captured stock; input trace is metadata, never model input."""
    result=deepcopy(existing) if existing is not None else enterprise_experiment(stock)
    financials=stock.get('normalized_inputs',stock.get('financials')) or {}
    assumptions=stock.get('profile_assumptions') or {}
    result['input_snapshot']={k:engine.fnum(financials.get(k)) for k in
        ('cash','debt','ebitda','revenue','canonical_shares')}
    result['input_snapshot'].update(
        ev_ebitda_range=valid_range(assumptions.get('ev_ebitda_range')),
        sales_multiple_range=valid_range(assumptions.get('sales_multiple_range')))
    result['wiring']={'version':ENTERPRISE_WIRING_VERSION,'batch_id':batch_id,
        'input_source':'captured_admin_production_snapshot',
        'financials_path':'normalized_inputs' if 'normalized_inputs' in stock else 'financials',
        'class_ranges_path':'profile_assumptions',
        'result_path':'stocks[].enterprise_aware_experiment',
        'uses_existing_snapshot_only':True}
    return result


def prepare_enterprise_report(report):
    """Repair missing legacy session sidecars, without fetches or production writes.

    Keep the original batch timestamp/inputs. Current complete results are not
    recalculated; all UI/export consumers receive the same namespace contract.
    """
    out=deepcopy(report)
    repaired=[]
    required=('production_fair','earnings_family_mid','enterprise_family',
        'ev_ebitda_model','ev_revenue_model','applicability')
    for stock in out.get('stocks',[]):
        existing=stock.get('enterprise_aware_experiment')
        complete=(isinstance(existing,dict) and all(k in existing for k in required)
            and isinstance(existing.get('enterprise_family_confidence'),str)
            and isinstance(existing.get('enterprise_evidence_status'),str)
            and isinstance(existing.get('production_readiness'),str))
        if not complete:repaired.append(stock['ticker'])
        stock['enterprise_aware_experiment']=wired_enterprise_result(stock,
            batch_id=out.get('batch_id'),existing=existing if complete else None)
    out['enterprise_experiment_wiring']={'version':ENTERPRISE_WIRING_VERSION,
        'repaired_tickers':repaired,'input_fetch_performed':False,
        'note':'Derived from original batch inputs; original timestamps preserved.'}
    return out


def readonly_display(live,load_snapshot):
    """Exact production resolver, with a no-op writer and defensive read copy."""
    from last_reliable_valuation import resolve_live_result
    return resolve_live_result(deepcopy(live),lambda:deepcopy(load_snapshot()),lambda result:None)


def capture_analysis(ticker,*,history_loader,fundamentals_loader,display_resolver=None):
    from enterprise_evidence_closure import observe_basis
    observed={}
    def observed_fundamentals(t):
        with observe_enterprise_statements(t) as historical, observe_basis(t) as basis_capture:
            result=fundamentals_loader(t)
        observed['metric_basis_evidence']=deepcopy(basis_capture)
        observed['historical_evidence']=deepcopy(historical)
        observed['acquired_inputs']=deepcopy(result)
        return result
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
    live=analyze(ticker,history_loader=history_loader,fundamentals_loader=observed_fundamentals,
                 peer_mode='diagnostic')
    displayed=display_resolver(deepcopy(live)) if display_resolver else deepcopy(live)
    stock=project_snapshot(live,displayed,observed)
    stock['evidence_snapshot']=evidence_snapshot(stock,observed.get('historical_evidence'))
    stock['metric_basis_evidence_snapshot']=deepcopy(observed.get('metric_basis_evidence') or {})
    stock['metric_basis_evidence_snapshot'].update({k:(stock.get('normalized_inputs') or {}).get(k)
        for k in ('input_batch_id','fundamentals_acquisition_id')})
    stock['production_input_trace']=build_trace(ticker,observed.get('acquired_inputs') or {},
        observed.get('normalized_inputs') or {},stock.get('normalized_inputs') or {})
    return stock


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
        'reliability_governance_audit':deepcopy(display_blend.get('reliability_governance_audit')),
        'structural_governance':deepcopy(display_blend.get('structural_governance')),
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
    from fundamental_acquisition import acquisition_batch
    with acquisition_batch(force_refresh=True) as scope:
        # Request-local copies coalesce even an injected loader; no stale session reuse.
        def scoped_fundamentals(ticker):
            key=(scope['batch_id'],ticker,'production_fundamentals')
            if key not in scope['request_scope_cache']:
                scope['request_scope_cache'][key]=deepcopy(fundamentals_loader(ticker))
            return deepcopy(scope['request_scope_cache'][key])
        report=_run_batch_impl(client,user_id,secrets,history_loader=history_loader,
            fundamentals_loader=scoped_fundamentals,display_resolver=display_resolver,
            reference_loader=reference_loader,input_batch_id=scope['batch_id'])
        report['provider_rate_limit_summary']=scope['provider_rate_limit_state'].summary()
        return report


def _run_batch_impl(client,user_id,secrets,*,history_loader,fundamentals_loader,display_resolver=None,reference_loader=None,input_batch_id=None):
    if not is_cloud_runtime() or not verified_admin(client,user_id,secrets.get('ADMIN_EMAIL')):
        raise PermissionError('Cloud admin only')
    if not _LOCK.acquire(blocking=False):raise RuntimeError('Busy')
    try:
        if time.monotonic()-_LAST_RUN.get(str(user_id),-1e12)<30:raise RuntimeError('Cooldown')
        _LAST_RUN[str(user_id)]=time.monotonic()
        batch_id=input_batch_id or str(uuid4());stamp=datetime.now(timezone.utc).isoformat()
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
            trace=stock.get('production_input_trace')
            if trace:
                observed_ids=[v.get('input_batch_id') for v in trace['stage_identities'].values()]
                if any(v is not None and v!=batch_id for v in observed_ids):
                    trace['divergence']='BATCH_ACQUISITION_DIVERGENCE'
                    trace['acceptance_status']='FAIL'
                    if 'input_batch_id' not in trace['identity_divergent_fields']:trace['identity_divergent_fields'].append('input_batch_id')
                trace['input_batch_id']=batch_id
                # Capture the actual guard argument immediately at its boundary.
                calibration_inputs=stock.get('normalized_inputs') or {}
                for field in ('forward_eps','quote_currency','financial_currency'):
                    trace[field]['calibration_input']=deepcopy(calibration_inputs.get(field))
                trace['stage_identities']['calibration']={k:calibration_inputs.get(k) for k in ('input_batch_id','fundamentals_acquisition_id')}
            stock.update(calibration_eligibility(stock,reference))
            stock['correlation_cross_family_governance']=governance_audit(stock)
            stock['experimental_family_blend']=family_blend_experiment(stock)
            stock['independent_evidence_governance']=independent_evidence_audit(stock)
            stock['capital_structure_overlay']=capital_overlay(stock)
            stock['enterprise_aware_experiment']=wired_enterprise_result(stock,batch_id=batch_id)
            stock['reference_snapshot_read_status']=reference_status
            inputs=stock.get('normalized_inputs') or {}
            stock.update(batch_id=batch_id,batch_generated_at=stamp,input_batch_id=batch_id,
                fundamentals_acquisition_id=inputs.get('fundamentals_acquisition_id'),
                batch_input_health=(inputs.get('provider_health') or {}).get('overall_state','UNOBSERVED'))
            stocks.append(stock)
        report={'schema_version':'v4.5.0','batch_id':batch_id,'batch_generated_at':stamp,'generated_at':stamp,
            'mode':'read_only_diagnostic','execution':'serial single Cloud batch; underlying cached input ages may differ',
            'stocks':stocks,'input_batch_id':batch_id,
            'batch_input_health':'DEGRADED' if any(s['batch_input_health'] in ('DEGRADED','UNAVAILABLE') for s in stocks)
                else 'UNOBSERVED' if any(s['batch_input_health']=='UNOBSERVED' for s in stocks)
                else 'PARTIAL' if any(s['batch_input_health']=='PARTIAL' for s in stocks) else 'HEALTHY'}
        report.update(batch_eligibility(stocks,TICKERS))
        report=attach_report(report)
        return json.loads(snapshot_json(_public(report),_secret_strings(secrets)))
    finally:_LOCK.release()


def csv_payload(report):
    report=prepare_enterprise_report(report)
    buffer=io.StringIO(newline='')
    summary_fields=('effective_independent_model_count','dominant_family','dominant_family_weight',
        'family_concentration_status','cross_family_status','cross_family_spread_pct','growth_overlap_risk',
        'governance_classification','governance_review_status')
    fields=('ticker','model_name','model_mid','base_weight','normalized_weight','contribution_to_blended_mid','included','excluded_reason')+summary_fields
    experimental_fields=tuple('experimental_family_blend.'+key for key in ('A_fair','B_fair','C_fair',
        'A_difference_pct','B_difference_pct','C_difference_pct','family_weighting_sensitivity','family_weighting_governance','experiment_status'))
    evidence_fields=tuple('independent_evidence_governance.'+key for key in EXPORT_FIELDS)
    overlay_fields=tuple('capital_structure_overlay.'+key for key in ('applicable','reason','overlay_role',
        'net_debt','net_debt_to_market_cap','net_debt_to_ebitda','interest_coverage','production_fair',
        'earnings_family_fair','burden_score','burden_band','burden_overlay_fair','ev_bridge_fair','consistency_status','governance',
        'burden_overlay_materiality','ev_bridge_materiality','burden_overlay_direction','ev_bridge_direction','consistency_rule_version'))
    enterprise_fields=tuple('enterprise_aware_experiment.'+key for key in ('production_fair','earnings_family_mid',
        'ev_ebitda_mid','ev_revenue_mid','enterprise_family_mid','enterprise_family_confidence','method_spread_pct',
        'difference_vs_earnings_pct','enterprise_evidence_status','evidence_status','production_readiness'))
    fields+=experimental_fields+evidence_fields+overlay_fields+enterprise_fields
    writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
    for stock in report['stocks']:
        governance=stock.get('correlation_cross_family_governance',{})
        for model in stock.get('models',[]):writer.writerow({'ticker':stock['ticker'],
            **{k:model.get(k) for k in fields if k!='ticker' and k not in summary_fields and k not in experimental_fields and k not in evidence_fields and k not in overlay_fields and k not in enterprise_fields},
            **{k:governance.get(k) for k in summary_fields},
            **{k:experiment_summary(stock).get(k.split('.',1)[1]) for k in experimental_fields},
            **{k:stock.get('independent_evidence_governance',{}).get(k.split('.',1)[1]) for k in evidence_fields},
            **{k:overlay_summary(stock).get(k.split('.',1)[1]) for k in overlay_fields},
            **{k:enterprise_summary(stock).get(k.split('.',1)[1]) for k in enterprise_fields}})
    return buffer.getvalue().encode('utf-8-sig')


def governance_audit_rows(report):
    """Project saved metadata; never reinterpret or rewrite historical policy."""
    rows=[]
    for stock in report['stocks']:
        audit=deepcopy(stock.get('reliability_governance_audit') or {'status':'NO_LIVE_GOVERNANCE_AUDIT'})
        governance=stock.get('structural_governance') or audit.get('structural_governance') or {}
        rows.append({'ticker':stock['ticker'],'source_status':stock.get('source_status'),**audit,
            'governance_status':governance.get('status'),
            'governance_scope':governance.get('governance_scope'),
            'fair_value_effect':governance.get('fair_value_effect'),
            'production_effect':governance.get('production_effect'),
            'reliability_governance_version':governance.get('reliability_governance_version')})
    return rows


def render_snapshot_export(st,client,user_id,*,history_loader,fundamentals_loader,display_resolver=None,reference_loader=None):
    if not is_cloud_runtime() or not verified_admin(client,user_id,st.secrets.get('ADMIN_EMAIL')):
        st.session_state.pop('_v45_export_open',None);st.session_state.pop('_v45_export_result',None)
        st.error('无权访问 V4.5 估值结构导出。');return
    st.subheader('V4.5 估值结构导出')
    st.caption('同批串行生产分析 · 只读 · 不写快照或更新 Last Reliable · Peer diagnostic only')
    if st.button('返回',key='v45_export_back'):
        st.session_state.pop('_v45_export_open',None);st.rerun()
    run_v45=st.button('运行五股生产分析快照',key='v45_export_run')
    run_v46=st.button('V4.6 Reliability Governance Audit',key='v46_export_run')
    if run_v45 or run_v46:
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
    report=attach_report(prepare_enterprise_report(saved['report']))
    saved['report']=report
    st.session_state['_v45_export_result']=saved
    if report['enterprise_experiment_wiring']['repaired_tickers']:
        st.info('已从当前保存批次的原始输入补算 V4.8 诊断；未重新抓取财务数据，批次时间保持不变。')
    st.caption('Input batch: '+str(report.get('input_batch_id',report.get('batch_id')))+
        ' · health: '+str(report.get('batch_input_health','LEGACY_UNOBSERVED'))+
        ' · '+str(report.get('generated_at')))
    if report.get('batch_input_health')=='DEGRADED':
        st.warning('该批次包含降级财务输入。点击“运行五股生产分析快照”会创建新 acquisition batch；当前显示保留原批次时间。')
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
    st.markdown('**V4.6 Reliability Governance Audit**')
    st.markdown('**Capital Structure Overlay**')
    st.caption('DIAGNOSTIC ONLY · 资本结构实验不改变生产估值、可靠性或交易区间。')
    st.dataframe([overlay_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        with st.expander(stock['ticker']+' — capital structure overlay'):
            st.json(stock.get('capital_structure_overlay',{}))
    audits=governance_audit_rows(report)
    st.markdown('**Production Input Wiring Trace**')
    rate_summary=report.get('provider_rate_limit_summary') or {}
    st.caption('Yahoo Rate-Limit Summary')
    st.json({key:rate_summary.get(key) for key in ('rate_limit_observed','primary_rate_limit_count',
        'recovery_attempts','recovery_successes','recovery_rate_limit_count','cooldown_events','total_cooldown_seconds')})
    st.dataframe([wiring_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
    st.markdown('**Enterprise-Aware Valuation Experiment**')
    st.caption('DIAGNOSTIC ONLY · 企业价值方法不进入生产 blend、可靠性或 Last Reliable；不是推荐估值。')
    st.dataframe([enterprise_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        with st.expander(stock['ticker']+' — enterprise-aware inputs / models'):
            st.json(stock.get('enterprise_aware_experiment',{}))
    st.markdown('**V4.9 Enterprise Family Suitability Audit**')
    st.caption('DIAGNOSTIC ONLY · 方法适用性不代表估值准确；UNKNOWN 需要证据，不改变 V4.8 聚合。')
    st.dataframe([suitability_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        audit=stock['enterprise_family_suitability']
        with st.expander(stock['ticker']+' — V4.9 suitability evidence'):
            st.json({k:audit[k] for k in ('audit_status','enterprise_method_class_policy','ev_ebitda','ev_revenue',
                'company_level','primary_disagreement_driver','disagreement_driver_evidence','growth_regime_mismatch_flag',
                'business_mix_warning','capital_intensity_assessment','margin_structure_assessment')})
            refs=audit['v48_references']
            st.json({'v48_raw_values':{k:refs.get(k) for k in ('enterprise_family_mid','enterprise_family_confidence','method_spread_pct','difference_vs_earnings_pct')},
                'method_mids':{k:(refs.get(k) or {}).get('mid') for k in ('ev_ebitda_model','ev_revenue_model')}})
    st.download_button('下载 V4.9 Suitability JSON',snapshot_json(audit_export(report)),
        'v49_enterprise_family_suitability_audit.json','application/json',key='v49_export_json')
    st.download_button('下载 V4.9 Suitability CSV',csv_export(report),
        'v49_enterprise_family_suitability_audit.csv','text/csv',key='v49_export_csv')
    st.markdown('**Enterprise Evidence Completion**')
    st.caption('V5.0 · DIAGNOSTIC ONLY · 复用当前批次年度报表；覆盖率不是 suitability 或准确度。')
    if st.button('运行 V5.0 Evidence Completion',key='v50_evidence_run'):
        saved['report']=complete_report(report)
        st.session_state['_v45_export_result']=saved
        report=saved['report']
    if report.get('enterprise_evidence_version')=='v5.0':
        if any((stock.get('enterprise_structural_evidence') or {}).get('audit_status')=='V5_INPUT_STATE_INELIGIBLE' for stock in report['stocks']):
            st.warning('V5 输入状态或批次身份不合格：仅展示证据结构，不生成正式 completion 或生产候选结论。')
        st.dataframe([evidence_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
        for stock in report['stocks']:
            with st.expander(stock['ticker']+' — V5.0 evidence / provenance / delta'):
                st.json({key:stock.get(key) for key in ('enterprise_structural_evidence','evidence_snapshot',
                    'v49_before','v49_after','v49_evidence_delta')})
        st.download_button('下载 V5.0 Evidence JSON',snapshot_json(evidence_export(report)),
            'v50_enterprise_evidence_completion.json','application/json',key='v50_export_json')
        st.download_button('下载 V5.0 Evidence CSV',evidence_csv(report),
            'v50_enterprise_evidence_completion.csv','text/csv',key='v50_export_csv')
    from enterprise_evidence_closure import close_report, summary as closure_summary, export_report as closure_export, export_csv as closure_csv
    st.markdown('**Enterprise Evidence Closure**')
    st.caption('V5.1 · DIAGNOSTIC ONLY · 同批输入，零新增数据请求；未知口径和未审核业务证据保持可见。')
    if report.get('enterprise_evidence_version')=='v5.0':
        if st.button('运行 V5.1 Evidence Closure',key='v51_closure_run'):
            saved['report']=close_report(report)
            st.session_state['_v45_export_result']=saved
            report=saved['report']
        if report.get('enterprise_evidence_closure_version')=='v5.1':
            st.dataframe([closure_summary(stock) for stock in report['stocks']],hide_index=True,use_container_width=True)
            for stock in report['stocks']:
                with st.expander(stock['ticker']+' — V5.1 metric basis / business structure'):
                    st.json(stock['enterprise_evidence_closure'])
            st.download_button('下载 V5.1 Closure JSON',snapshot_json(closure_export(report)),
                'v51_enterprise_evidence_closure.json','application/json',key='v51_export_json')
            st.download_button('下载 V5.1 Closure CSV',closure_csv(report),
                'v51_enterprise_evidence_closure.csv','text/csv',key='v51_export_csv')
    else:
        st.caption('请先运行当前批次 V5.0 Evidence Completion。')
    st.caption('Governance: Applied to production reliability · Scope: Reliability / Confidence / Precise Exit · Fair value effect: None（新生成的 live 治理结果）')
    st.dataframe([{k:a.get(k) for k in ('ticker','source_status','fair_before','fair_after','fair_unchanged',
        'reliability_before','reliability_after','confidence_before','confidence_after','precise_exit_before','precise_exit_after',
        'governance_status','governance_scope','fair_value_effect','production_effect','reliability_governance_version')} for a in audits],
        hide_index=True,use_container_width=True)
    st.download_button('下载 V4.6 Governance JSON',snapshot_json({'batch_id':report['batch_id'],
        'generated_at':report['generated_at'],'mode':'read_only_diagnostic','reliability_governance_version':GOVERNANCE_VERSION,'stocks':audits}),
        'v46_cloud_reliability_governance.json','application/json',key='v46_export_json')
    st.download_button('下载 V4.5 JSON',snapshot_json(report),'v45_cloud_production_analysis.json','application/json',key='v45_export_json')
    st.download_button('下载模型贡献 CSV',csv_payload(report),'v45_cloud_model_contributions.csv','text/csv',key='v45_export_csv')
