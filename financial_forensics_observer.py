"""Request-local, opt-in observation of public numeric Yahoo fields only.

No raw response objects, auth objects, exception messages or arbitrary strings
are retained. Production loading decisions do not depend on this observer.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date, datetime
import math
import re

_OBSERVER=ContextVar('financial_forensics_observer',default=None)
INFO_NUMBERS=('currentPrice','regularMarketPrice','forwardEps','trailingEps','epsForward','forwardPE',
 'sharesOutstanding','impliedSharesOutstanding','marketCap','totalCash','totalDebt','freeCashflow',
 'operatingCashflow','earningsGrowth','revenueGrowth','totalRevenue','ebitda')
INFO_CURRENCIES=('currency','financialCurrency','financialCurrencyCode')
STATEMENT_ROWS={
 'cashflow':('Operating Cash Flow','Total Cash From Operating Activities','Cash Flow From Continuing Operating Activities',
             'Capital Expenditure','Capital Expenditures','Purchase Of PPE','Free Cash Flow'),
 'income_stmt':('Net Income','Net Income Common Stockholders','Diluted Average Shares','Basic Average Shares',
                'Total Revenue','Operating Revenue','Operating Income','EBIT','Diluted EPS','Basic EPS'),
 'balance_sheet':('Cash And Cash Equivalents','Cash Cash Equivalents And Short Term Investments','Cash Financial',
                  'Total Debt','Long Term Debt And Capital Lease Obligation','Net Debt','Ordinary Shares Number',
                  'Share Issued','Common Stock Shares Outstanding','Common Shares','Stockholders Equity',
                  'Total Stockholder Equity','Tangible Book Value','Net Tangible Assets')}


def numeric(value):
    if value is None or isinstance(value,bool):return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None


def currency(value):
    return value if isinstance(value,str) and re.fullmatch('[A-Z]{3}',value) else None


def period(value):
    if isinstance(value,(date,datetime)):return value.isoformat()[:10]
    if isinstance(value,str) and re.fullmatch(r'(FY\d{4}|\d{4}-\d{2}-\d{2}( 00:00:00)?)',value):return value[:10]
    return None


@contextmanager
def observe_financial_inputs():
    data={'info_paths':{},'selected_info_sources':{},'statements':{},'selected_fields':{},'estimates':[]}
    token=_OBSERVER.set(data)
    try:yield data
    finally:_OBSERVER.reset(token)


def observe_info(path,raw,status='AVAILABLE'):
    from reporting_basis_resolution import observe_provider
    observe_provider(path,raw)
    data=_OBSERVER.get()
    if data is None:return
    try:
        raw=raw if isinstance(raw,dict) else {}
        fields={key:(currency(raw.get(key)) if key in INFO_CURRENCIES else numeric(raw.get(key)))
                for key in INFO_NUMBERS+INFO_CURRENCIES}
        if path in data['info_paths']:
            previous=data['info_paths'][path]['fields']
            fields={key:fields[key] if key in raw else previous.get(key) for key in fields}
        data['info_paths'][path]={'status':status,'fields':fields}
        for key,value in fields.items():
            if value is not None:data['selected_info_sources'][key]=path+'.'+key
    except Exception:pass


def observe_statement(stage,path,frame,status='AVAILABLE'):
    from reporting_basis_resolution import observe_statement as observe_reporting_statement
    observe_reporting_statement(stage,path,frame)
    from enterprise_evidence_closure import observe_statement as observe_basis_statement
    observe_basis_statement(stage,path,frame)
    # Independent opt-in diagnostic observer; consumes the already loaded frame only.
    from enterprise_evidence import observe_statement_values
    observe_statement_values(stage,path,frame)
    data=_OBSERVER.get()
    if data is None:return
    try:
        valid=frame is not None and not frame.empty
        rows=list(STATEMENT_ROWS[stage])
        entry={'path':path,'status':status if valid else ('EMPTY' if status=='AVAILABLE' else status),
               'periods':[period(col) for col in list(frame.columns)[:8]] if valid else [],
               'rows_present':[row for row in rows if row in frame.index] if valid else [],
               'rows_missing':[row for row in rows if row not in frame.index] if valid else rows}
        data['statements'].setdefault(stage,[]).append(entry)
    except Exception:pass


def observe_estimate(estimate_period,value):
    data=_OBSERVER.get()
    if data is not None and estimate_period in ('0y','+1y','0q','+1q','FIRST_AVAILABLE_AVG','NOT_AVAILABLE','ERROR'):
        data['estimates'].append({'period':estimate_period,'value':numeric(value),
                                 'path':'ticker.get_earnings_estimate.avg'})


def observe_selected(field,value,source,raw_value=None):
    data=_OBSERVER.get()
    if data is not None and field in ('cash','debt','shares','revenue_growth'):
        data['selected_fields'][field]={'value':numeric(value),'raw_value':numeric(raw_value),'source':source}


def public_observations():
    return deepcopy(_OBSERVER.get() or {})
