"""Post-calculation diagnostic governance; never a valuation/blend input."""
from itertools import combinations
from statistics import median
from finnhub_service import number

CONSISTENT_SPREAD_PCT = 20.0
MODERATE_SPREAD_PCT = 40.0
REVIEW_MIN_EFFECTIVE_PEERS = 2.5


def cross_multiple_consistency(peer):
    """Percent units. Pairwise denominator is the pair's mean (symmetric).

    Only independently successful engine attempts count; never infer success
    from raw peer counts or from presence of an intermediate multiple statistic.
    No benchmark or internal valuation is read here.
    """
    output=dict(consistency_status='UNAVAILABLE',valid_multiple_count=0,
        multiple_mid_min=None,multiple_mid_max=None,multiple_mid_median=None,
        cross_multiple_spread_pct=None,max_pairwise_difference_pct=None,
        peer_production_eligibility='DIAGNOSTIC_ONLY',multiple_results=[])
    if peer.get('eligibility')=='NOT_ELIGIBLE':
        output['consistency_status']='NOT_APPLICABLE'
        return output
    seen=set()
    for attempt in peer.get('post_data_audit',{}).get('attempts',[]):
        mid=number(attempt.get('peer_mid'))
        method=attempt.get('Multiple')
        if attempt.get('Status')!='VALID' or mid is None or mid<=0 or not method or method in seen:continue
        seen.add(method)
        output['multiple_results'].append(dict(multiple=method,
            peer_low=attempt.get('peer_low'),peer_mid=mid,peer_high=attempt.get('peer_high'),
            confidence=attempt.get('confidence'),raw_peer_count=attempt.get('raw_peer_count'),
            effective_peer_count=attempt.get('effective_peer_count'),
            weighted_dispersion=attempt.get('weighted_dispersion')))
    mids=[m['peer_mid'] for m in output['multiple_results']]
    count=len(mids)
    output['valid_multiple_count']=count
    if not count:return output
    center=median(mids)
    spread=(max(mids)-min(mids))/center*100
    output.update(multiple_mid_min=min(mids),multiple_mid_max=max(mids),multiple_mid_median=center,
        cross_multiple_spread_pct=spread,
        max_pairwise_difference_pct=max((abs(a-b)/((a+b)/2)*100 for a,b in combinations(mids,2)),default=0.))
    status=('SINGLE_METHOD_ONLY' if count==1 else 'CONSISTENT' if spread<=CONSISTENT_SPREAD_PCT
            else 'MODERATE_DISAGREEMENT' if spread<=MODERATE_SPREAD_PCT else 'MULTIPLE_DISAGREEMENT')
    output['consistency_status']=status
    if (status=='CONSISTENT' and peer.get('valid') and peer.get('confidence') in ('MEDIUM','HIGH')
            and (number(peer.get('effective_peer_count')) or 0)>=REVIEW_MIN_EFFECTIVE_PEERS):
        output['peer_production_eligibility']='REVIEW_ELIGIBLE'
    return output
