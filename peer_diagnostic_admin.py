"""Cloud ADMIN_EMAIL-only Peer diagnostics. No writes or production blending."""
from copy import deepcopy
import csv
import io
import json
import threading
import time

from finnhub_admin_diagnostics import is_cloud_runtime, verified_admin
from financial_forensics_admin import _secret_strings
from financial_forensics import snapshot_json
from finnhub_service import FinnhubProvider
from scripts.report_peer_comparable import build_report

TICKERS=('NVDA','ORCL','AMZN','MSFT','GOOG')
BENCHMARKS={'NVDA':300,'ORCL':180,'AMZN':285,'MSFT':544,'GOOG':345}
_LOCK=threading.Lock()
_LAST_RUN={}


class _NoPeerRequests:
    """Suppress redundant sidecar requests while capturing internal baseline."""
    def get_company_profile(self,ticker):return {'status':'NOT_CONFIGURED','data':{}}
    def get_basic_financials(self,ticker):return {'status':'NOT_CONFIGURED','data':{}}


def _live_internal(ticker):
    from analysis_service import analyze_ticker
    from mag7_monitor import get_live_fundamentals
    return analyze_ticker(ticker,peer_mode='diagnostic',peer_provider=_NoPeerRequests(),
        fundamentals_loader=lambda t:get_live_fundamentals(t,allow_estimates=False))


def run_cloud_peer_diagnostic(client,user_id,secrets,tickers,*,provider=None,internal_loader=None):
    if not is_cloud_runtime() or not verified_admin(client,user_id,secrets.get('ADMIN_EMAIL')):
        raise PermissionError('Peer 诊断仅限 Cloud 中 ADMIN_EMAIL 对应管理员。')
    selected=list(dict.fromkeys('GOOG' if str(t).upper()=='GOOGL' else str(t).upper() for t in tickers))
    if not selected or any(t not in TICKERS for t in selected):raise ValueError('请选择允许诊断的股票。')
    if not _LOCK.acquire(blocking=False):raise RuntimeError('诊断正在运行。')
    try:
        identity=str(user_id)
        if time.monotonic()-_LAST_RUN.get(identity,-1e12)<30:raise RuntimeError('请间隔 30 秒重试。')
        _LAST_RUN[identity]=time.monotonic()
        p=provider if provider is not None else FinnhubProvider(
            key_loader=lambda:str(secrets.get('FINNHUB_API_KEY','')).strip() or None)
        loader=internal_loader or _live_internal
        baselines={}
        if p.configured():
            for ticker in selected:
                try:baselines[ticker]=deepcopy(loader(ticker))
                except Exception:baselines[ticker]={}
        # Existing engine inputs/results are captured before peer calculation.
        # Benchmarks enter only the existing report's post-calculation comparison.
        report=build_report(provider=p,tickers=selected,internal_results=baselines,
                            references={t:{'external_benchmark':BENCHMARKS[t]} for t in selected})
        for row,detail in zip(report['comparison'],report['peer_results']):
            status='AVAILABLE' if detail['valid'] and len(detail['peers_included'])>=3 else 'INSUFFICIENT_VALID_PEERS'
            if not report['live_finnhub_configured']:status='NOT_CONFIGURED'
            else:
                observed=[entry.get(key) for entry in detail.get('provenance',{}).values() if isinstance(entry,dict)
                          for key in ('profile_status','metrics_status')]
                if 'RATE_LIMIT' in observed or 'SKIPPED_RATE_LIMIT' in observed:status='RATE_LIMIT'
                elif not detail['valid']:
                    status=next((s for s in ('NOT_ENTITLED','NETWORK_ERROR','NO_DATA','INVALID_RESPONSE') if s in observed),status)
            row['diagnostic_status']=status
            if status!='AVAILABLE':
                # Never display a precise peer price for incomplete/limited runs.
                for key in ('peer_low','peer_mid','peer_high','peer_fair_low','peer_fair_mid','peer_fair_high',
                            'difference_dollars','difference_pct','peer_error_pct'):row[key]=None
                row['peer_valid']=False
                detail.update(valid=False,low=None,mid=None,high=None)
        # Only projected public data reaches session state or downloads.
        return json.loads(snapshot_json(report,_secret_strings(secrets)))
    finally:_LOCK.release()


def summary_rows(report):
    return [{'Ticker':r['ticker'],'Internal Fair':r['current_internal_fair'],
             'Peer Low':r['peer_low'],'Peer Mid':r['peer_mid'],'Peer High':r['peer_high'],
             'Peer Confidence':r['peer_confidence'],'Selected Multiple':r['selected_multiple'],
             'Peers Included':r['peers_included'],'Internal vs Peer %':r['difference_pct'],
             'Internal vs Benchmark %':r['internal_error_pct'],'Peer vs Benchmark %':r['peer_error_pct'],
             'Status':r['diagnostic_status']} for r in report['comparison']]


def download_payloads(report):
    buffer=io.StringIO(newline='')
    rows=summary_rows(report)
    writer=csv.DictWriter(buffer,fieldnames=list(rows[0]) if rows else ['Ticker'])
    writer.writeheader()
    writer.writerows(rows)
    return snapshot_json(report),buffer.getvalue().encode('utf-8-sig')


def render_peer_diagnostics(st,client,user_id):
    if not is_cloud_runtime() or not verified_admin(client,user_id,st.secrets.get('ADMIN_EMAIL')):
        st.session_state.pop('_peer_diagnostic_open',None)
        st.session_state.pop('_peer_diagnostic_result',None)
        st.error('无权访问 Peer 估值诊断。')
        return
    st.subheader('Peer 估值诊断')
    st.caption('Cloud 管理员只读诊断 · diagnostic 模式 · 不进入最终 blend · 不保存估值快照')
    if st.button('返回',key='peer_diagnostic_back'):
        st.session_state.pop('_peer_diagnostic_open',None)
        st.rerun()
    ticker=st.selectbox('Ticker',TICKERS,key='peer_diagnostic_ticker')
    single=st.button('运行单股诊断',key='peer_diagnostic_single')
    batch=st.button('运行五股诊断',key='peer_diagnostic_batch')
    if single or batch:
        st.session_state.pop('_peer_diagnostic_result',None)
        try:
            with st.spinner('正在串行获取公开财务输入及 Finnhub 同行数据…'):
                report=run_cloud_peer_diagnostic(client,user_id,st.secrets,TICKERS if batch else [ticker])
            st.session_state['_peer_diagnostic_result']={'owner':str(user_id),'report':report}
        except PermissionError:st.error('无权运行 Peer 估值诊断。')
        except RuntimeError:st.warning('已有诊断正在执行或请求过于频繁，请稍后重试。')
        except Exception:st.error('诊断未完成；未输出凭据或异常原文。')
    saved=st.session_state.get('_peer_diagnostic_result')
    if not saved:return
    if saved.get('owner')!=str(user_id):
        st.session_state.pop('_peer_diagnostic_result',None)
        return
    report=saved['report']
    st.caption('Internal vs Peer % = (Peer Mid / Internal Fair − 1) × 100；benchmark 仅作事后比较。')
    st.dataframe(summary_rows(report),hide_index=True,use_container_width=True)
    for row,detail in zip(report['comparison'],report['peer_results']):
        with st.expander(row['ticker']+' · '+row['diagnostic_status'],expanded=len(report['comparison'])==1):
            st.write({'Ticker':row['ticker'],'Internal Fair':row['current_internal_fair'],
                      'Peer valid':detail['valid'],'Peer confidence':detail['confidence'],
                      'selected_multiple':detail['selected_multiple'],
                      'peer_low':detail['low'],'peer_mid':detail['mid'],'peer_high':detail['high'],
                      'Peer Group':detail['peer_group'],'Peer Q1':detail['peer_q1'],
                      'Peer Median':detail['peer_median'],'Peer Q3':detail['peer_q3'],
                      'Peer vs Internal %':row['difference_pct'],'External Benchmark':row['external_benchmark'],
                      'Internal vs Benchmark %':row['internal_error_pct'],'Peer vs Benchmark %':row['peer_error_pct']})
            if not detail['valid']:st.info('Peer 不可用：'+row['diagnostic_status'])
            st.markdown('**Peers Included**')
            included=[{k:p[k] for k in ('ticker','multiple_value','growth_pct','margin_pct','market_cap_usd_millions')}
                      for p in detail['composition'] if p['included']]
            if included:st.dataframe(included,hide_index=True,use_container_width=True)
            else:st.caption('无合格同行；不生成 Peer fair value。')
            st.markdown('**Peers Excluded**')
            excluded=[{'ticker':p['ticker'],'reason':p['exclusion_reason']} for p in detail['composition'] if not p['included']]
            if excluded:st.dataframe(excluded,hide_index=True,use_container_width=True)
            st.caption('Growth / margin 为百分点；market cap 单位为 USD millions。fetched_at 是取数时间，不代表报表期。')
            st.json({'source':'Finnhub','fetched_at':detail['provenance'].get('fetched_at'),
                     'peer_sources':{p['ticker']:p['sources'] for p in detail['composition']},
                     'provenance':detail['provenance']})
    json_data,csv_data=download_payloads(report)
    st.download_button('下载 Peer JSON',json_data,'cloud_peer_diagnostic.json','application/json',key='peer_diagnostic_json')
    st.download_button('下载 Peer CSV',csv_data,'cloud_peer_diagnostic.csv','text/csv',key='peer_diagnostic_csv')
