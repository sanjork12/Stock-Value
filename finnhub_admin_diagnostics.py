"""Temporary, admin-only diagnostic UI. Never persists credentials or reports."""
from collections import Counter
import csv
import io
import json
from pathlib import Path
import threading
import time

from scripts.audit_finnhub_capabilities import run_audit, SPECS, STATES, TICKERS

_RUN_LOCK = threading.Lock()
_LAST_RUN = None
COOLDOWN_SECONDS = 300


def is_cloud_runtime():
    # Fail closed outside Community Cloud's mounted application checkout.
    return Path(__file__).resolve().is_relative_to(Path('/mount/src'))


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def verified_admin(client, user_id, admin_email):
    """Use the authenticated server response, never user-editable metadata."""
    if not user_id or not isinstance(admin_email, str) or not admin_email.strip():
        return False
    try:
        response = client.auth.get_user()
        user = _field(response, 'user')
        email = _field(user, 'email')
        return bool(user and str(_field(user, 'id')) == str(user_id)
                    and isinstance(email, str)
                    and email.strip().casefold() == admin_email.strip().casefold())
    except Exception:
        return False


def sanitize_report(report, secret):
    # Defensive final boundary, including unusual provider field names.
    text = json.dumps(report, ensure_ascii=False)
    if secret:
        text = text.replace(secret, '[REDACTED]')
    return json.loads(text)


def capability_rows(report):
    """One row per observed status; never invent states for untested pairs."""
    rows=[]
    total=len(report.get('tickers') or TICKERS)
    for name, results in report.get('endpoints', {}).items():
        counts=Counter(item.get('status') for item in results.values())
        for status,count in counts.items():
            if status not in STATES:
                continue
            tickers=[ticker for ticker,item in results.items() if item.get('status') == status]
            fields=sorted({key for ticker in tickers for key in results[ticker].get('fields',[])})
            rows.append({'Capability':name, 'Endpoint':SPECS[name][0], 'Status':status,
                         'Coverage':f'{count}/{total}',
                         'Notes':f"{', '.join(tickers)}; tested {len(results)}/{total}; fields: {', '.join(fields) or '(none)'}"})
    return rows


def download_payloads(report):
    json_bytes=json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=['Capability','Endpoint','Status','Coverage','Notes'])
    writer.writeheader()
    for row in capability_rows(report):
        # Prevent spreadsheet formula interpretation in provider-derived fields.
        writer.writerow({key:("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value)
                         for key,value in row.items()})
    return json_bytes,buffer.getvalue().encode('utf-8-sig')


def run_cloud_audit(client, user_id, secrets, *, progress=None):
    """Recheck access at execution; lock and cooldown are shared across sessions."""
    global _LAST_RUN
    if not is_cloud_runtime() or not verified_admin(client,user_id,secrets.get('ADMIN_EMAIL')):
        raise PermissionError('诊断仅限 Cloud 中已验证的管理员。')
    key=secrets.get('FINNHUB_API_KEY')
    if not isinstance(key,str) or not key.strip() or key.strip() in {'...', 'YOUR_FINNHUB_API_KEY'}:
        raise ValueError('Streamlit Secrets 尚未配置有效的 FINNHUB_API_KEY。')
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError('已有诊断正在执行，请稍后重试。')
    try:
        if _LAST_RUN is not None and time.monotonic()-_LAST_RUN < COOLDOWN_SECONDS:
            raise RuntimeError('为避免限流，每次诊断之间需间隔至少 5 分钟。')
        _LAST_RUN=time.monotonic()
        return sanitize_report(run_audit(key.strip(),tickers=list(TICKERS),progress=progress),key.strip())
    finally:
        _RUN_LOCK.release()


def render_diagnostics(st, client, user_id):
    # Rendering and downloads are protected too, even after a session switch.
    if not is_cloud_runtime() or not verified_admin(client,user_id,st.secrets.get('ADMIN_EMAIL')):
        st.session_state.pop('_finnhub_audit_result',None)
        st.error('无权访问 Finnhub 能力诊断。')
        return
    st.subheader('Finnhub 能力诊断')
    st.caption('临时管理员诊断 · 7 只股票 · 串行调用 · 首次限流即停止 · 不改变估值或生产数据')
    if st.button('返回',key='finnhub_audit_back'):
        st.session_state.pop('_finnhub_audit_open',None)
        st.rerun()
    if st.button('开始能力诊断',key='finnhub_audit_run'):
        bar=st.progress(0,text='准备诊断…')
        def update(name,ticker,completed,total):
            bar.progress(completed/total,text=f'{name} · {ticker} · {completed}/{total}')
        try:
            report=run_cloud_audit(client,user_id,st.secrets,progress=update)
            st.session_state['_finnhub_audit_result']={'owner':str(user_id),'report':report}
        except (PermissionError,ValueError,RuntimeError) as exc:
            st.warning(str(exc))
        except Exception:
            # Do not let Streamlit print tracebacks containing request credentials.
            st.error('诊断未完成，请稍后重试。')
        finally:
            bar.empty()
    saved=st.session_state.get('_finnhub_audit_result')
    if saved and saved.get('owner') == str(user_id):
        report=saved['report']
        st.caption(f"诊断时间：{report['tested_at']} · 实际请求：{report['requests_sent']}")
        if report.get('rate_limit_observed'):
            st.warning('已遇到 RATE_LIMIT，后续请求已停止；未测试能力不推断权限。')
        st.dataframe(capability_rows(report),hide_index=True,use_container_width=True)
        json_bytes,csv_bytes=download_payloads(report)
        st.download_button('下载 JSON',json_bytes,'finnhub_capability_report.json','application/json',key='audit_json')
        st.download_button('下载 CSV',csv_bytes,'finnhub_capability_report.csv','text/csv',key='audit_csv')
