"""Report-only evidence collection must not alter the diagnostic model."""
from copy import deepcopy
from datetime import datetime,timezone
import unittest
from unittest.mock import Mock,patch

from scripts.report_peer_comparable import ReviewProvider,build_report
from peer_comparable import GROUPS,calculate_peer_comparable
from finnhub_service import FinnhubProvider


class PublicFixture:
    def __init__(self):
        self.calls=[]
        self.stamp=datetime.now(timezone.utc).isoformat()
    def configured(self):return True
    def get_company_profile(self,ticker):
        self.calls.append(('stock/profile2',ticker))
        return {'status':'AVAILABLE','fetched_at':self.stamp,
                'data':{'marketCapitalization':1000,'finnhubIndustry':'Software','not_exported':'fixture-private-text'}}
    def get_basic_financials(self,ticker):
        self.calls.append(('stock/metric',ticker))
        return {'status':'AVAILABLE','fetched_at':self.stamp,
                'data':{'Forward PE':20,'TTM PE':25,'EV/EBITDA TTM':10,'EV/Revenue TTM':5,
                        'Revenue Growth TTM YoY':10,'Operating Margin TTM':20}}


FIN={'forward_eps':5,'forward_eps_source':'forwardEps','trailing_eps':4,
     'trailing_eps_source':'trailingEps','shares':10,'cash':100,'debt':200,
     'revenue':2000,'ebitda':1000,'quote_currency':'USD','financial_currency':'USD'}


class ReviewReportTests(unittest.TestCase):
    def test_recorder_preserves_exact_model_result(self):
        direct,wrapped=PublicFixture(),PublicFixture()
        wrapped.stamp=direct.stamp
        now=datetime.now(timezone.utc)
        a=calculate_peer_comparable('NVDA',deepcopy(FIN),'semiconductor_growth',provider=direct,now=now)
        b=calculate_peer_comparable('NVDA',deepcopy(FIN),'semiconductor_growth',provider=ReviewProvider(wrapped),now=now)
        self.assertEqual(a.to_dict(),b.to_dict())

    def test_benchmark_never_changes_model_or_peer_selection(self):
        a=build_report(provider=PublicFixture(),financial_loader=lambda _:deepcopy(FIN),references={})
        b=build_report(provider=PublicFixture(),financial_loader=lambda _:deepcopy(FIN),
                       references={t:{'external_benchmark':999999} for t in ('NVDA','ORCL','AMZN','MSFT','GOOG')})
        for first,second in zip(a['peer_results'],b['peer_results']):
            for key in ('valid','selected_multiple','peer_median','peer_q1','peer_q3','low','mid','high',
                        'peers_considered','peers_included','peers_excluded'):
                self.assertEqual(first[key],second[key])

    def test_only_two_endpoints_and_no_duplicate_alphabet_or_peer_fetch(self):
        provider=PublicFixture()
        report=build_report(provider=provider,financial_loader=lambda _:deepcopy(FIN))
        self.assertEqual(len(report['comparison']),5)
        self.assertEqual(set(path for path,_ in provider.calls),{'stock/profile2','stock/metric'})
        self.assertEqual(len(provider.calls),len(set(provider.calls)))
        self.assertNotIn('GOOGL',[ticker for _,ticker in provider.calls])
        for detail in report['peer_results']:
            self.assertEqual(len(detail['composition']),len(detail['peers_considered']))
            for row in detail['composition']:
                self.assertIn('margin_pct',row)
                self.assertIn('growth_pct',row)
                self.assertIn('sources',row)
                self.assertNotIn('not_exported',str(row))
        # A configured review still must not silently fetch Yahoo estimates
        # when the caller did not supply a previously captured target snapshot.
        with patch('mag7_monitor._yfinance',side_effect=AssertionError('No Yahoo calls')):
            missing=build_report(provider=PublicFixture())
        self.assertTrue(all(row['target_data_status']=='TARGET_INPUT_SNAPSHOT_REQUIRED'
                            and row['current_internal_fair'] is None for row in missing['comparison']))

    def test_no_key_means_no_fabricated_data_or_target_request(self):
        loader=Mock(side_effect=AssertionError('No Yahoo calls when Finnhub is absent'))
        report=build_report(provider=FinnhubProvider(key_loader=lambda:None),financial_loader=loader)
        loader.assert_not_called()
        for row in report['comparison']:
            self.assertFalse(row['peer_valid'])
            self.assertIsNone(row['current_internal_fair'])
            self.assertIsNone(row['peer_fair_mid'])
            self.assertIsNone(row['difference_pct'])

    def test_rate_limit_stops_all_later_targets(self):
        provider=PublicFixture()
        def limited(ticker):
            provider.calls.append(('stock/profile2',ticker))
            return {'status':'RATE_LIMIT','data':{},'fetched_at':provider.stamp}
        provider.get_company_profile=limited
        build_report(provider=provider,financial_loader=lambda _:deepcopy(FIN))
        self.assertEqual(provider.calls,[('stock/profile2','NVDA')])

    def test_existing_model_accepts_high_dispersion_but_review_does_not(self):
        provider=PublicFixture()
        original=provider.get_basic_financials
        def metrics(ticker):
            response=original(ticker)
            if ticker in ('AVGO','AMD','MRVL'):
                response['data']['Forward PE']={'AVGO':10,'AMD':25,'MRVL':50}[ticker]
            return response
        provider.get_basic_financials=metrics
        report=build_report(provider=provider,financial_loader=lambda _:deepcopy(FIN))
        nvda=next(row for row in report['comparison'] if row['ticker']=='NVDA')
        self.assertTrue(nvda['peer_valid'])  # existing model, deliberately unchanged
        self.assertGreater(nvda['peer_dispersion'],.6)
        self.assertFalse(nvda['review_eligible'])


if __name__=='__main__':unittest.main()
