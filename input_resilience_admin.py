"""Temporary Cloud / ADMIN_EMAIL-only V4.8.1 diagnostics."""
import json
import threading
import time

from finnhub_admin_diagnostics import is_cloud_runtime, verified_admin
from financial_forensics_admin import _secret_strings
from financial_forensics import snapshot_json
from finnhub_service import get_finnhub_provider
from input_resilience_audit import run_audit

_LOCK=threading.Lock()
_LAST_RUN={}


def run_cloud_audit(client,user_id,secrets,*,production_report=None,yahoo_factory=None,provider=None):
    if not is_cloud_runtime() or not verified_admin(client,user_id,secrets.get('ADMIN_EMAIL')):
        raise PermissionError('Cloud 管理员专用。')
    if not _LOCK.acquire(blocking=False):raise RuntimeError('已有 Provider Audit 正在运行。')
    try:
        if time.monotonic()-_LAST_RUN.get(str(user_id),-1e12)<300:
            raise RuntimeError('两次审计需间隔至少 5 分钟。')
        _LAST_RUN[str(user_id)]=time.monotonic()
        if yahoo_factory is None:
            from mag7_monitor import _yfinance
            yahoo_factory=_yfinance().Ticker
        report=run_audit(yahoo_factory=yahoo_factory,provider=provider or get_finnhub_provider(),
            production_report=production_report)
        return json.loads(snapshot_json(report,_secret_strings(secrets)))
    finally:_LOCK.release()


def summary_rows(report):
    rows=[]
    for s in report['stocks']:
        paths=s['paths'];c={p['field']:p for p in s['fallback_candidates']}
        statement_states=[paths['yahoo.'+p]['state'] for p in ('income_stmt','cashflow','balance_sheet')]
        rows.append({'Ticker':s['ticker'],'Yahoo info state':paths['yahoo.info']['state'],
            'Yahoo statements state':' / '.join(statement_states),
            'Finnhub profile state':paths['finnhub.profile']['state'],
            'Finnhub metric state':paths['finnhub.metric']['state'],
            'Forward EPS source availability':'YAHOO_DIRECT' if paths['yahoo.get_info']['values'].get('forward_eps') is not None
                or paths['yahoo.info']['values'].get('forward_eps') is not None else c['forward_eps']['source_type'],
            'Quote currency fallback':c['quote_currency']['fallback_safety'],
            'Financial currency status':'KNOWN' if any(paths[p]['values'].get('financial_currency') for p in ('yahoo.info','yahoo.get_info')) else 'UNKNOWN',
            'Split fallback':c['last_split_factor']['fallback_safety'],
            'Eligibility recovery potential':s['eligibility_recovery_simulation'][2]['eligibility_recovery_potential']})
    return rows


def render_input_resilience(st,client,user_id):
    if not is_cloud_runtime() or not verified_admin(client,user_id,st.secrets.get('ADMIN_EMAIL')):
        st.session_state.pop('_v481_result',None)
        st.warning('仅限 Cloud 中 ADMIN_EMAIL 对应的已登录管理员。');return
    st.header('Cloud Input Resilience Audit')
    st.caption('V4.8.1 · 只读逐字段取证 · 不实施 fallback，不修改生产估值或 Calibration Guard')
    if st.button('返回',key='v481_back'):
        st.session_state.pop('_v481_open',None);st.rerun()
    if st.button('运行五股 Provider Audit',key='v481_run'):
        saved=st.session_state.get('_v45_export_result') or {}
        production=saved.get('report') if saved.get('owner')==str(user_id) else None
        try:
            with st.spinner('串行读取公开数据；每条 Yahoo 路径只调用一次，Finnhub 使用现有限流器。'):
                report=run_cloud_audit(client,user_id,st.secrets,production_report=production)
            st.session_state['_v481_result']={'owner':str(user_id),'report':report}
        except (PermissionError,RuntimeError) as exc:
            # Only our controlled messages; provider exceptions never escape core.
            st.error('暂时无法运行审计，请确认权限或等待 5 分钟后重试。')
        except Exception:
            st.error('审计未完成；未输出请求、凭据或异常详情。')
    saved=st.session_state.get('_v481_result') or {}
    if saved.get('owner')!=str(user_id):
        st.session_state.pop('_v481_result',None);return
    report=saved['report']
    st.caption('Provider batch: '+report['batch_id']+' · '+report['generated_at'])
    st.info('已有生产批次仅用于输入/eligibility/reference 比较，时间单独标注；不把旧输入混入本轮 provider 计算。网络根因需要此 Cloud 导出的实际证据。')
    st.dataframe(summary_rows(report),hide_index=True,use_container_width=True)
    for stock in report['stocks']:
        with st.expander(stock['ticker']+' — acquisition / fields / candidates / simulations'):
            st.json(stock)
    st.json({'cache_audit':report['cache_audit'],'source_audit':report['source_audit'],'environment':report['environment']})
    st.download_button('下载 Provider Audit JSON',snapshot_json(report),
        'v481_cloud_input_resilience.json','application/json',key='v481_download')
