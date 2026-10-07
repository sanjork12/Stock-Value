"""Temporary Cloud-only, ADMIN_EMAIL-only public financial input diagnostic."""
from copy import deepcopy
from collections.abc import Mapping
import json
import threading
import time
from datetime import date

from finnhub_admin_diagnostics import is_cloud_runtime, verified_admin
from financial_forensics import (TICKERS, capture_financial_diagnostic, snapshot_rows,
                                  snapshot_json, compare_financial_snapshots, source_name, FinancialDiagnosticFailure)

_LOCK=threading.Lock()
_LAST_RUN={}


def _secret_strings(secrets):
    # Redact configured strings at the final boundary; never inspect Auth tokens.
    strings=[]
    def walk(value,hint=''):
        if isinstance(value,str):
            if len(value)>3 and any(word in hint.lower() for word in ('key','token','secret','password','cookie')):strings.append(value)
        elif isinstance(value,Mapping):
            for key,item in value.items():walk(item,str(key))
    walk(secrets)
    return strings


def run_cloud_financial_diagnostic(client,user_id,secrets,ticker, *, simulate_missing_input=False):
    if not is_cloud_runtime() or not verified_admin(client,user_id,secrets.get('ADMIN_EMAIL')):
        raise PermissionError('财务输入诊断仅限 Cloud 中 ADMIN_EMAIL 对应的已登录管理员。')
    if ticker not in TICKERS:raise ValueError('请选择允许诊断的股票。')
    simulate_missing_input = simulate_missing_input is True
    if not _LOCK.acquire(blocking=False):raise RuntimeError('已有财务诊断正在执行，请稍后重试。')
    try:
        identity=(str(user_id),ticker)
        if time.monotonic()-_LAST_RUN.get(identity,-1e12)<30:
            raise RuntimeError('同一股票诊断需间隔至少 30 秒。')
        _LAST_RUN[identity]=time.monotonic()
        try:
            def valuation_display(result):
                from analysis_service import fetch_historical_snapshot
                from last_reliable_valuation import apply_last_reliable
                if simulate_missing_input:
                    row=fetch_historical_snapshot(client,user_id,ticker,date.today().isoformat())
                    result=apply_last_reliable(result,row,_admin_simulated_missing=True)
                # Whitelisted public display fields only; no writes in this path.
                return {key:deepcopy(result.get(key)) for key in (
                    'ticker','source_status','stale_reason','fair_value','blended_low',
                    'blended_mid','blended_high','zones','exit_zone','calculated_at',
                    'confidence','valuation_mode','simulated_missing_input')
                } | {'source_status':result.get('source_status','live')}
            report=capture_financial_diagnostic(ticker,
                simulate_missing_input=simulate_missing_input,result_sink=valuation_display)
        except FinancialDiagnosticFailure:
            raise
        except Exception as exc:
            raise FinancialDiagnosticFailure('CAPTURE_INPUTS',exc) from None
        # Only the redacted schema-projected report is retained in session state.
        try:
            redactions=_secret_strings(secrets)
        except Exception as exc:
            raise FinancialDiagnosticFailure('PREPARE_REDACTION',exc) from None
        try:
            return json.loads(snapshot_json(report,redactions))
        except Exception as exc:
            raise FinancialDiagnosticFailure('SERIALIZE_REPORT',exc) from None
    finally:_LOCK.release()


def _local_for_comparison(upload,cloud):
    """Project uploads onto the trusted Cloud schema; never echo arbitrary JSON."""
    if upload.size>1_000_000:raise ValueError('本地快照文件过大。')
    raw=json.loads(upload.getvalue().decode('utf-8-sig'))
    if raw.get('schema_version')!=1 or raw.get('ticker')!=cloud['ticker']:
        raise ValueError('请选择同一 ticker 的财务诊断 JSON。')
    from financial_forensics_observer import numeric,currency
    from financial_forensics import _history
    local={'ticker':raw['ticker'],'fields':{}}
    for name,reference in cloud['fields'].items():
        entry=(raw.get('fields') or {}).get(name,{})
        value=entry.get('value')
        if name.endswith(('_currency','.quote_currency','.financial_currency')):value=currency(value)
        elif name.endswith('_source'):value=source_name(value) if value else None
        elif name=='cash_flow.fcf_history':value=_history(value if isinstance(value,list) else [])
        elif name in ('profile.preferred_models','profile.excluded_models'):
            from financial_forensics import MODEL_INPUTS
            value=[v for v in value if v in MODEL_INPUTS] if isinstance(value,list) else []
        elif name=='profile.valuation_class':
            from valuation_engine import CLASS_SPECS
            value=value if isinstance(value,str) and value in CLASS_SPECS else None
        elif isinstance(reference['value'],bool):value=value if isinstance(value,bool) else None
        else:value=numeric(value)
        local['fields'][name]={'value':value,'raw_source_name':source_name(entry.get('raw_source_name'))}
    # Uploaded arbitrary statement/model text is not rendered. Field-by-field
    # comparison includes history/counts/currencies; full trusted-file comparison
    # remains available through the local helper/CLI.
    return local


def render_financial_diagnostics(st,client,user_id):
    if not is_cloud_runtime() or not verified_admin(client,user_id,st.secrets.get('ADMIN_EMAIL')):
        st.session_state.pop('_financial_diagnostic_result',None)
        st.session_state.pop('_financial_diagnostic_open',None)
        st.error('无权访问财务输入诊断。')
        return
    st.subheader('财务输入诊断')
    st.caption('临时 Cloud 管理员入口 · 只读公开财务输入 · Finnhub 仅旁路观察 · 不改变估值')
    if st.button('返回',key='financial_diagnostic_back'):
        st.session_state.pop('_financial_diagnostic_open',None)
        st.rerun()
    ticker=st.selectbox('Ticker',TICKERS,key='financial_diagnostic_ticker')
    simulate=st.checkbox('模拟关键财务输入缺失',key='financial_diagnostic_simulate_missing',value=False) is True
    if simulate:
        st.warning('测试模式：正在模拟实时财务输入缺失')
    if st.button('Run diagnostic',key='financial_diagnostic_run'):
        try:
            with st.spinner('正在捕获 Yahoo 实际响应路径、估值前输入和模型失败原因…'):
                report=run_cloud_financial_diagnostic(client,user_id,st.secrets,ticker,simulate_missing_input=simulate)
            saved=st.session_state.get('_financial_diagnostic_result')
            reports=deepcopy(saved.get('reports',{})) if saved and saved.get('owner')==str(user_id) else {}
            reports[ticker]=report
            st.session_state['_financial_diagnostic_result']={'owner':str(user_id),'reports':reports}
        except FinancialDiagnosticFailure as exc:
            st.session_state['_financial_diagnostic_result']={'owner':str(user_id),'reports':{
                ticker:{'ticker':ticker,'capture_error':exc.public_error}}}
        except (PermissionError,ValueError,RuntimeError):
            st.warning('诊断未完成、正在执行或请求过于频繁，请稍后重试。')
        except Exception:
            st.error('诊断未完成；未输出请求、凭据或异常详情。')
    saved=st.session_state.get('_financial_diagnostic_result')
    if not saved:return
    if saved.get('owner')!=str(user_id):
        st.session_state.pop('_financial_diagnostic_result',None)
        return
    report=saved.get('reports',{}).get(ticker)
    if not report:return
    if not report.get('capture_error') and bool(report.get('simulated_missing_input')) != simulate:
        st.info('测试开关已切换，请点击 Run diagnostic 重新运行。')
        return
    if report.get('capture_error'):
        error=report['capture_error']
        st.error(f"诊断失败阶段：{error['stage']} · 错误类别：{error['category']}。未输出凭据或异常原文。")
        st.json(error)
        st.download_button('下载脱敏失败报告 JSON',snapshot_json(report),
                           f'cloud_financial_diagnostic_{ticker}.json','application/json',key='financial_diagnostic_error_json')
        return
    st.caption(f"捕获时间：{report['run_timestamp']} · {report['environment']['runtime']} · BEFORE_VALUATE")
    rows=snapshot_rows(report)
    for row in rows:row['Value']=json.dumps(row['Value'],ensure_ascii=False)
    st.dataframe(rows,hide_index=True,use_container_width=True)
    trace=report['valuation_failure_trace']
    if not trace['available']:
        st.warning(f"UNAVAILABLE because: {trace['UNAVAILABLE because']} · valid_models = {trace['valid_models']} · included = {trace['included_model_count']}")
    else:st.success(f"内部估值可用：{trace['fair_value']} · {trace['valuation_mode']}")
    st.dataframe(report['model_applicability'],hide_index=True,use_container_width=True)
    st.caption('Peer: '+trace['peer'])
    valuation=report.get('valuation')
    if valuation:
        from last_reliable_valuation import render_cache_notice
        render_cache_notice(st,valuation)
        st.caption('以下为展示结果；上方保留本次实时模型的真实计算与失败原因。')
        st.json(valuation)
    with st.expander('A–G 假设、原始公开字段和响应路径'):
        st.json(report['hypotheses'])
        st.json(report['raw_yahoo_observations'])
    st.download_button('下载 Cloud Snapshot JSON',snapshot_json(report,_secret_strings(st.secrets)),
                       f'cloud_financial_diagnostic_{ticker}.json','application/json',key='financial_diagnostic_json')
    local=st.file_uploader('可选：上传同一 ticker 的本地财务诊断 JSON 做逐字段对比',type=['json'],key='financial_diagnostic_local')
    if local is not None:
        try:
            comparison=compare_financial_snapshots(_local_for_comparison(local,report),report)
            comparison=[row for row in comparison if row['field'] in report['fields']]
            for row in comparison:
                for key in ('local_value','cloud_value'):row[key]=json.dumps(row[key],ensure_ascii=False)
            # Defensive credential redaction also applies to uploaded values.
            comparison=json.loads(snapshot_json(comparison,_secret_strings(st.secrets)))
            st.dataframe(comparison,hide_index=True,use_container_width=True)
        except Exception:st.warning('无法比较：请使用同一 ticker 的本地诊断工具导出文件。')
