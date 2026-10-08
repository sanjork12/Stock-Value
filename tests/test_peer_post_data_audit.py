from copy import deepcopy
import unittest
from test_peer_review_report import FIN,PublicFixture
from scripts.report_peer_comparable import ReviewProvider,build_report
from peer_comparable import calculate_peer_comparable
from peer_post_data_audit import audit_multiples


class PostDataAuditTests(unittest.TestCase):
    def audit(self,financials=None,provider=None):
        p=ReviewProvider(provider or PublicFixture())
        f=deepcopy(FIN if financials is None else financials)
        before=calculate_peer_comparable('ORCL',f,'mega_cap_tech',provider=p).to_dict()
        calls=len(p.provider.calls)
        audit=audit_multiples('ORCL',f,'mega_cap_tech',p)
        self.assertEqual(len(p.provider.calls),calls)
        after=calculate_peer_comparable('ORCL',f,'mega_cap_tech',provider=p).to_dict()
        before['provenance'].pop('fetched_at');after['provenance'].pop('fetched_at')
        # Fetch-age changes with wall time, while every valuation decision stays fixed.
        for item in (before,after):
            for value in item['provenance'].values():
                if isinstance(value,dict):value.pop('peer_data_age_hours',None)
        self.assertEqual(before,after)
        return audit

    def test_all_attempts_even_after_first_success(self):
        audit=self.audit()
        self.assertEqual([a['Multiple'] for a in audit['attempts']],['Forward P/E','EV/EBITDA','EV/Revenue'])
        self.assertEqual(audit['attempts'][0]['Status'],'VALID')
        self.assertFalse(audit['early_exit_on_first_eligible_multiple'])

    def test_target_missing_not_labeled_insufficient(self):
        audit=self.audit({})
        self.assertTrue(all(a['Status']=='TARGET_INPUT_UNSAFE' for a in audit['attempts']))
        self.assertTrue(all(a['After Comparability'] is None for a in audit['attempts']))

    def test_explicit_peer_exclusion(self):
        p=PublicFixture();original=p.get_basic_financials
        def metrics(t):
            response=original(t)
            if t=='IBM':response['data']['Forward PE']=None
            return response
        p.get_basic_financials=metrics
        audit=self.audit(provider=p)
        ibm=next(r for r in audit['attempts'][0]['peer_trace'] if r['peer_ticker']=='IBM')
        self.assertEqual(ibm['exact_exclusion_reason'],'missing_or_nonpositive_selected_multiple')
        self.assertFalse(ibm['multiple_available'])

    def test_failed_first_attempt_continues_to_alternate(self):
        p=PublicFixture();original=p.get_basic_financials
        def metrics(t):
            response=original(t);response['data']['Forward PE']=None
            return response
        p.get_basic_financials=metrics
        f=dict(FIN,canonical_shares=10)
        audit=self.audit(f,p)
        self.assertEqual(audit['attempts'][0]['Status'],'INSUFFICIENT_MULTIPLE_DATA')
        self.assertEqual(audit['attempts'][1]['Status'],'VALID')
        self.assertTrue(audit['alternate_multiple_succeeds'])


if __name__=='__main__':unittest.main()
