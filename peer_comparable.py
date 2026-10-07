"""Independent Finnhub comparable model. No financial normalization or API targets.

Metrics are dimensionless multiples; Finnhub growth, margin and ROE are percent
points. Currency-safe per-share/enterprise inputs come only from the existing
normalized target financials. A target never counts as its own peer.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import math
import os
from statistics import median

from finnhub_service import get_finnhub_provider, number
from financial_normalization import FORWARD_EPS_SOURCES, is_statement_eps_source, statement_inputs_currency_safe


# Explicit business families allow justified cross-class comparisons without
# changing any existing valuation class assignment.
GROUPS = {
    'enterprise_software': ['MSFT','ORCL','CRM','NOW','SAP','IBM'],
    'digital_advertising': ['GOOG','META','TTD','PINS','SNAP'],
    'commerce_platform': ['AMZN','BABA','JD','MELI','EBAY'],
    'consumer_devices': ['AAPL','DELL','HPQ','SONY'],
    'semiconductor_growth': ['NVDA','AVGO','AMD','MRVL'],
    'bank': ['JPM','BAC','WFC','C','GS','MS'],
    'high_growth_software': ['PLTR','NOW','CRM','SNOW','CRWD'],
    'memory_cycle': ['MU','WDC','STX'],
}
BUSINESS = {t:g for g, tickers in GROUPS.items() for t in tickers}
BUSINESS.update(NOW='enterprise_software', CRM='enterprise_software', WDC='storage_hardware', STX='storage_hardware')
CLASS_COMPATIBILITY = {
 'enterprise_software': {'mega_cap_tech','mature_growth','high_growth_software','generic_profitable'},
 'digital_advertising': {'mega_cap_tech','consumer_platform','generic_profitable'},
 'commerce_platform': {'mega_cap_tech','consumer_platform','mature_growth','generic_profitable'},
 'consumer_devices': {'mega_cap_tech','mature_growth','generic_profitable'},
 'semiconductor_growth': {'semiconductor_growth'}, 'bank': {'bank'},
 'high_growth_software': {'high_growth_software','mature_growth','generic_profitable'},
 'memory_cycle': {'cyclical_semiconductor'},
}
# Additional mapped tickers have peer-only business/class tags, never overrides
# for the project's existing classification engine.
PEER_CLASSES = {t:next(iter(CLASS_COMPATIBILITY[g])) for g,ts in GROUPS.items() if len(CLASS_COMPATIBILITY[g])==1 for t in ts}
PEER_CLASSES.update(CRM='mature_growth',NOW='high_growth_software',SAP='mature_growth',IBM='mature_growth',
 TTD='consumer_platform',PINS='consumer_platform',SNAP='consumer_platform',JD='consumer_platform',
 MELI='consumer_platform',EBAY='consumer_platform',DELL='mature_growth',HPQ='mature_growth',SONY='mature_growth',CRWD='high_growth_software')
WEIGHTS = {'mega_cap_tech':.15,'semiconductor_growth':.20,'mature_growth':.20,
           'bank':.15,'consumer_platform':.15,'high_growth_software':.15,'cyclical_semiconductor':.15}
MULTIPLE_KEYS = {'Forward P/E':'Forward PE','P/E TTM':'TTM PE','P/B':'P/B',
                 'EV/EBITDA':'EV/EBITDA TTM','EV/Revenue':'EV/Revenue TTM'}
MAX_DATA_AGE_HOURS = 72


@dataclass
class PeerComparableResult:
    target_ticker: str
    valuation_class: str
    valid: bool = False
    applicable: bool = False
    peer_group: str | None = None
    peers_considered: list = field(default_factory=list)
    peers_included: list = field(default_factory=list)
    peers_excluded: list = field(default_factory=list)
    exclusion_reasons: dict = field(default_factory=dict)
    selected_multiple: str | None = None
    target_multiple: float | None = None
    peer_median: float | None = None
    peer_q1: float | None = None
    peer_q3: float | None = None
    target_metric: str | None = None
    target_metric_value: float | None = None
    low: float | None = None
    mid: float | None = None
    high: float | None = None
    confidence: str = 'UNAVAILABLE'
    dispersion: float | None = None
    warnings: list = field(default_factory=list)
    provenance: dict = field(default_factory=lambda: {'source':'Finnhub','endpoints':['stock/profile2','stock/metric']})

    def to_dict(self):
        return asdict(self)


def canonical(ticker):
    ticker = str(ticker).strip().upper()
    return 'GOOG' if ticker == 'GOOGL' else ticker


def peer_model_mode():
    value = os.environ.get('PEER_MODEL_MODE')
    if value is None:
        try:
            import streamlit as st
            value = st.secrets.get('PEER_MODEL_MODE','diagnostic')
        except Exception:
            value = 'diagnostic'
    return 'active' if str(value).strip().lower() == 'active' else 'diagnostic'


def group_for(ticker, valuation_class):
    t = canonical(ticker)
    if t == 'PLTR': return 'high_growth_software'
    family = BUSINESS.get(t)
    if family in GROUPS: return family
    return {'semiconductor_growth':'semiconductor_growth','bank':'bank',
            'high_growth_software':'high_growth_software','cyclical_semiconductor':'memory_cycle'}.get(valuation_class)


def quantile(values, fraction):
    values = sorted(values)
    position = (len(values)-1)*fraction
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi]-values[lo])*(position-lo)


def _positive(value):
    value = number(value)
    return value if value is not None and value > 0 else None


def _metric_inputs(multiple, f):
    """Return target metric/EV conversion inputs; never synthesize missing data."""
    if multiple == 'Forward P/E':
        eps = _positive(f.get('forward_eps'))
        source = str(f.get('forward_eps_source') or '')
        if not eps or source not in FORWARD_EPS_SOURCES or source == 'price/forwardPE' or is_statement_eps_source(source):
            return None
        return ('Forward EPS',eps,None)
    if multiple == 'P/E TTM':
        eps = _positive(f.get('trailing_eps'))
        if eps and not is_statement_eps_source(f.get('trailing_eps_source')):
            return ('Trailing EPS',eps,None)
        return None
    if not statement_inputs_currency_safe(f):
        return None
    if multiple == 'P/B':
        bvps = _positive(f.get('book_value_per_share'))
        return ('BVPS',bvps,None) if bvps else None
    metric = _positive(f.get('ebitda' if multiple == 'EV/EBITDA' else 'revenue'))
    shares = _positive(f.get('canonical_shares'))
    cash, debt = number(f.get('cash')), number(f.get('debt'))
    if not metric or not shares or cash is None or debt is None or cash < 0 or debt < 0:
        return None
    if f.get('shares_severe_mismatch') or (f.get('class_specific_shares') and f.get('canonical_shares_source') in (None,'sharesOutstanding')):
        return None
    return ('EBITDA' if multiple == 'EV/EBITDA' else 'Revenue',metric,(cash,debt,shares))


def _multiple_order(group, valuation_class, target_metrics):
    if valuation_class == 'bank': return ['P/B','P/E TTM']
    if valuation_class == 'cyclical_semiconductor': return ['EV/EBITDA']
    if group == 'enterprise_software': return ['Forward P/E','EV/EBITDA','EV/Revenue']
    if valuation_class == 'high_growth_software': return ['EV/Revenue','Forward P/E','EV/EBITDA']
    choices = ['Forward P/E','EV/EBITDA']
    if valuation_class == 'semiconductor_growth' and (number(target_metrics.get('Revenue Growth TTM YoY')) or 0) >= 20:
        choices.append('EV/Revenue')
    return choices


def _freshness(response, now):
    try:
        timestamp = datetime.fromisoformat(str(response.get('fetched_at')).replace('Z','+00:00'))
        if timestamp.tzinfo is None: return None
        return (now-timestamp).total_seconds()/3600
    except (ValueError,TypeError):
        return None


def calculate_peer_comparable(ticker, financials, valuation_class, *, provider=None, now=None, peer_tickers=None):
    r = PeerComparableResult(canonical(ticker),valuation_class)
    r.peer_group = group_for(ticker, valuation_class)
    if not r.peer_group:
        r.warnings.append('unsupported_business_model');return r
    r.applicable = True
    p = provider or get_finnhub_provider()
    now = now or datetime.now(timezone.utc)
    r.provenance['fetched_at'] = now.isoformat()
    candidates = list(dict.fromkeys(canonical(t) for t in (peer_tickers if peer_tickers is not None else GROUPS[r.peer_group])))
    r.peers_considered = [t for t in candidates if t != r.target_ticker]
    all_tickers = [r.target_ticker]+r.peers_considered
    records = {}
    blocked = False
    for t in all_tickers:
        if blocked:
            records[t] = {'reason':'RATE_LIMIT'}
            r.provenance[t] = {'source':'Finnhub','profile_status':'SKIPPED_RATE_LIMIT',
                               'metrics_status':'SKIPPED_RATE_LIMIT','peer_data_age_hours':None}
            continue
        try:
            profile = p.get_company_profile(t)
            metrics = p.get_basic_financials(t) if profile.get('status') == 'AVAILABLE' else {}
        except Exception:
            records[t] = {'reason':'NETWORK_ERROR'}
            r.provenance[t] = {'source':'Finnhub','profile_status':'NETWORK_ERROR',
                               'metrics_status':'NETWORK_ERROR','peer_data_age_hours':None}
            continue
        statuses = [profile.get('status'), metrics.get('status')]
        if 'RATE_LIMIT' in statuses: blocked = True
        ages = [_freshness(x,now) for x in (profile,metrics)]
        r.provenance[t] = {'source':'Finnhub','profile_fetched_at':profile.get('fetched_at'),
            'metrics_fetched_at':metrics.get('fetched_at'),'peer_data_age_hours':max(ages) if all(a is not None for a in ages) else None,
            'profile_status':statuses[0],'metrics_status':statuses[1]}
        if any(status != 'AVAILABLE' for status in statuses):
            records[t] = {'reason':next((s for s in statuses if s and s != 'AVAILABLE'),'NO_DATA')};continue
        if any(a is None or a < -0.1 or a > MAX_DATA_AGE_HOURS for a in ages):
            r.warnings.append(t+':stale_or_unknown_fetch_time')
            records[t] = {'reason':'stale_or_unknown_fetch_time'};continue
        records[t] = {'profile':profile.get('data') or {},'metrics':metrics.get('data') or {}}
    target = records[r.target_ticker]
    if target.get('reason'):
        r.warnings.append('target_reference_'+target['reason'])
        r.exclusion_reasons = {t:records[t].get('reason','target_reference_unavailable') for t in r.peers_considered}
        r.peers_excluded = list(r.peers_considered)
        return r
    target_metrics = target['metrics']
    if not (_positive(target['profile'].get('marketCapitalization')) or _positive(target_metrics.get('Market Capitalization'))):
        r.warnings.append('target_missing_or_nonpositive_market_cap')
        r.peers_excluded = list(r.peers_considered)
        r.exclusion_reasons = {t:'target_missing_or_nonpositive_market_cap' for t in r.peers_considered}
        return r
    orders = _multiple_order(r.peer_group,valuation_class,target_metrics)
    attempts = []
    for multiple in orders:
        if valuation_class == 'high_growth_software' and r.peer_group != 'enterprise_software' and multiple == 'Forward P/E':
            history = financials.get('historical_eps') or []
            if len(history) < 3 or any(not _positive(x.get('eps')) for x in history[:3]):
                attempts.append({'multiple':multiple,'reason':'stable_target_profitability_unverified'});continue
        metric_inputs = _metric_inputs(multiple,financials)
        if not metric_inputs:
            attempts.append({'multiple':multiple,'reason':'missing_or_unsafe_target_metric'});continue
        key = MULTIPLE_KEYS[multiple]
        reasons, included, values = {}, [], {}
        tm = target_metrics
        for t in r.peers_considered:
            rec = records[t]
            reason = rec.get('reason')
            m = rec.get('metrics',{})
            cap = _positive(rec.get('profile',{}).get('marketCapitalization')) or _positive(m.get('Market Capitalization'))
            peer_class = PEER_CLASSES.get(t)
            if not peer_class:
                from valuation_engine import infer_valuation_class
                peer_class = infer_valuation_class(t,{'industry':rec.get('profile',{}).get('finnhubIndustry')})
            family = BUSINESS.get(t)
            r.provenance[t].update(valuation_class=peer_class,business_model=family)
            if not reason and family != r.peer_group:
                # High growth software can compare software businesses, provided
                # growth, margins and profit basis independently pass below.
                if not (r.peer_group == 'high_growth_software' and family == 'enterprise_software'):
                    reason = 'business_model_mismatch'
            if not reason and peer_class not in CLASS_COMPATIBILITY[r.peer_group]:reason = 'valuation_class_mismatch'
            if not reason and not cap:reason = 'missing_or_nonpositive_market_cap'
            value = _positive(m.get(key))
            if not reason and not value:reason = 'missing_or_nonpositive_selected_multiple'
            for field, maximum in [('Revenue Growth TTM YoY',50),('Operating Margin TTM',25)]:
                a,b = number(tm.get(field)),number(m.get(field))
                if not reason and (a is None or b is None):reason = 'missing_comparability_'+field
                if not reason and abs(a-b)>maximum:reason = 'extreme_difference_'+field
            if not reason and multiple in ('Forward P/E','P/E TTM','EV/EBITDA') and (not _positive(m.get('TTM PE')) or not _positive(tm.get('TTM PE'))):
                reason = 'noncomparable_profitability_basis'
            if not reason and multiple == 'EV/Revenue' and (number(tm.get('Operating Margin TTM')) > 0) != (number(m.get('Operating Margin TTM')) > 0):
                reason = 'noncomparable_profitability_basis'
            if not reason and valuation_class == 'high_growth_software' and r.peer_group != 'enterprise_software' and multiple == 'Forward P/E':
                eps_growth = number(m.get('EPS Growth TTM YoY'))
                if eps_growth is None or eps_growth < 0 or not _positive(m.get('Operating Margin TTM')):
                    reason = 'stable_peer_profitability_unverified'
            if not reason and multiple == 'P/B' and (not _positive(m.get('ROE TTM')) or not _positive(tm.get('ROE TTM'))):
                reason = 'missing_or_nonpositive_roe'
            if reason:reasons[t] = reason
            else:included.append(t);values[t] = value
        if len(values) >= 3:
            vals = list(values.values());q1,q3,center = quantile(vals,.25),quantile(vals,.75),median(vals)
            spread = q3-q1
            for t,value in list(values.items()):
                if value < max(0,q1-1.5*spread) or value > q3+1.5*spread or value > center*3 or value < center/3:
                    reasons[t] = 'peer_excluded_as_outlier';values.pop(t);included.remove(t)
        attempts.append({'multiple':multiple,'included':included,'excluded':reasons})
        r.selected_multiple = multiple
        r.target_multiple = number(tm.get(key))
        r.target_metric,r.target_metric_value,enterprise = metric_inputs
        r.peers_included,r.exclusion_reasons,r.peers_excluded = included,reasons,list(reasons)
        if len(values) < 3:continue
        vals = list(values.values())
        r.peer_q1,r.peer_median,r.peer_q3 = quantile(vals,.25),median(vals),quantile(vals,.75)
        r.dispersion = (r.peer_q3-r.peer_q1)/r.peer_median
        adjustment = 1.0
        if multiple == 'P/B':
            target_roe = _positive(financials.get('roe'))
            if target_roe is None:
                r.warnings.append('missing_target_roe_for_pb_adjustment');continue
            peer_roe = median(records[t]['metrics']['ROE TTM'] for t in included)/100
            adjustment = max(.75,min(1.25,target_roe/peer_roe))
            r.provenance['roe_adjustment'] = {'target_roe':target_roe,'peer_median_roe':peer_roe,'factor':adjustment,'bounds':[.75,1.25]}
        prices = [r.target_metric_value*x*adjustment for x in (r.peer_q1,r.peer_median,r.peer_q3)]
        if enterprise:
            cash,debt,shares = enterprise
            prices = [(ev+cash-debt)/shares for ev in prices]
            r.provenance['enterprise_conversion'] = {'cash':cash,'debt':debt,'canonical_shares':shares,'canonical_shares_source':financials.get('canonical_shares_source')}
        if any(not math.isfinite(x) or x<=0 for x in prices):
            r.warnings.append('nonpositive_equity_value');continue
        r.low,r.mid,r.high = prices
        r.valid = True
        r.confidence = 'HIGH' if len(values)>=5 and r.dispersion<.25 else 'LOW' if r.dispersion>.6 else 'MEDIUM'
        if r.peer_group in ('commerce_platform','consumer_devices'):
            r.confidence = 'LOW';r.warnings.append('heterogeneous_business_mix')
        r.provenance['peer_multiples'] = values
        break
    r.provenance['selection_attempts'] = attempts
    r.provenance['target_metric_source'] = financials.get('forward_eps_source') if r.selected_multiple=='Forward P/E' else 'existing_normalized_financials'
    r.warnings.append('fetched_at_is_retrieval_time_not_fundamental_period')
    if not r.valid:
        r.warnings.append('fewer_than_three_comparable_peers_or_unsafe_target_inputs')
        if not r.selected_multiple:
            r.peers_excluded = list(r.peers_considered)
            r.exclusion_reasons = {t:records[t].get('reason','missing_or_unsafe_target_metric') for t in r.peers_considered}
    return r


def as_blend_model(peer):
    return {'name':'Peer Comparable','model_id':'peer_comparable','valid':peer.valid,'applicable':peer.applicable,
            'low':peer.low,'mid':peer.mid,'high':peer.high,'fair':peer.mid,
            'warnings':list(peer.warnings),'reason':None if peer.valid else 'peer_unavailable',
            'executed':True,'confidence':peer.confidence,'inputs':peer.to_dict()}
