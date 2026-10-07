"""Latest official quarters and evidence-bound multi-company news regression."""
from datetime import date, datetime, timezone
from copy import deepcopy
import re
import unittest
from unittest.mock import Mock

from industry.earnings_helpers import (get_latest_reported_quarter, get_latest_company_quarter,
    infer_period_end, audit_earnings_freshness, load_company_quarter_snapshots)
from industry.news.finnhub_live import normalize_finnhub_news, deduplicate, get_live_events
from industry.news.grounded_summary import ticker_roles, INSUFFICIENT

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


def article(**changes):
    raw = dict(id=42, headline="Broadcom, Oracle Earnings to Test Cloud Infrastructure's AI-Driven Momentum",
               summary='Broadcom and Oracle will report quarterly earnings this week. Investors are assessing cloud infrastructure demand. Broadcom revenue grew 86% to $29.6 billion. Oracle cloud revenue increased 62% to $11.6 billion.',
               source='Original Publisher', related='AVGO,ORCL,NVDA', datetime=NOW.timestamp(),
               url='https://publisher.test/article?id=42')
    raw.update(changes)
    return raw


class LatestSnapshotTests(unittest.TestCase):
    def test_report_dates_beat_fiscal_labels_and_exclude_future(self):
        rows = [dict(ticker='AMZN',fiscal_period='CY9999 Q4',report_date='2026-07-01'),
                dict(ticker='AMZN',fiscal_period='CY2026 Q2',report_date='2026-07-30'),
                dict(ticker='AMZN',fiscal_period='CY2026 Q3',report_date='2026-10-29'),
                dict(ticker='TSLA',fiscal_period='CY2026 Q2',report_date='2026-08-01')]
        self.assertEqual(get_latest_company_quarter('AMZN',as_of=NOW.date(),rows=rows)['report_date'],'2026-07-30')

    def test_amazon_and_tesla_real_maintained_latest(self):
        for ticker, rd in [('AMZN','2026-07-30'),('TSLA','2026-07-22')]:
            r = get_latest_reported_quarter(ticker, '2026-10-07')
            self.assertEqual(r['fiscal_period'], 'CY2026 Q2')
            self.assertEqual(r['report_date'], rd)
            self.assertEqual(r['data_status'], 'CURRENT')
            self.assertGreater(r['total_revenue'], 0)

    def test_asof_before_release_retains_history(self):
        self.assertEqual(get_latest_reported_quarter('AMZN','2026-07-29')['fiscal_period'],'CY2025 Q2')

    def test_known_newer_release_marks_even_recent_snapshot_stale(self):
        row = dict(ticker='AMZN',report_date='2026-07-01',fiscal_period='CY2026 Q1')
        self.assertEqual(get_latest_company_quarter('AMZN',as_of=NOW.date(),rows=[row])['data_status'],'STALE_DATA')

    def test_aliases_and_all_fifteen_audited(self):
        self.assertEqual(get_latest_reported_quarter('GOOGL',NOW.date()),get_latest_reported_quarter('GOOG',NOW.date()))
        audit = audit_earnings_freshness(as_of=NOW.date())
        self.assertEqual(len(audit),15)
        self.assertTrue(all(r['data_status']=='CURRENT' for r in audit))

    def test_fiscal_calendar_not_invented(self):
        self.assertIsNone(infer_period_end(dict(fiscal_period='FY2026 Q4')))
        self.assertIsNone(infer_period_end(dict(fiscal_period='FY2025 Q3',period_end='2025-09-30',report_date='2025-07-31')))

    def test_required_fields_and_quarter_units(self):
        fields = set('ticker fiscal_period period_end report_date total_revenue revenue_growth_yoy operating_income operating_margin net_income free_cash_flow capex capex_to_revenue segment_revenue_json segment_growth_json current_profit_engine future_expansion source_name source_url source_type last_verified_at'.split())
        for row in load_company_quarter_snapshots():
            self.assertTrue(fields <= row.keys())
            self.assertLessEqual(row['period_end'],row['report_date'])
            if row['segments']:
                self.assertAlmostEqual(sum(s['revenue'] for s in row['segments']),row['total_revenue'])
        amzn = get_latest_reported_quarter('AMZN',NOW.date())
        self.assertEqual(amzn['free_cash_flow'], (45387-53076)*1e6)
        self.assertIsNone(get_latest_reported_quarter('AAPL',NOW.date())['free_cash_flow'])


class DeepNewsTests(unittest.TestCase):
    def test_primary_secondary_and_incidental_ticker_rejected(self):
        raw=article();a=normalize_finnhub_news(raw,'AVGO')
        self.assertEqual(a['primary_tickers'],['AVGO','ORCL'])
        self.assertEqual(a['secondary_tickers'],['NVDA'])
        self.assertIsNone(normalize_finnhub_news(raw,'NVDA'))

    def test_core_comparison_can_promote_secondary(self):
        primary,_=ticker_roles('Oracle earnings','Oracle competes with Nvidia. Nvidia is a core competitor in this comparison.','ORCL,NVDA')
        self.assertIn('NVDA',primary)

    def test_global_url_id_and_normalized_title_union(self):
        first=normalize_finnhub_news(article(),'AVGO')
        second=normalize_finnhub_news(article(),'ORCL')
        third=normalize_finnhub_news(article(id=43,url='https://other.test/story'),'ORCL')
        self.assertEqual(len(deduplicate([first,second,third])),1)
        changed=deepcopy(first);changed.update(finnhub_id=999,original_headline='Different title',source_url=first['source_url']+'&utm_source=x')
        self.assertEqual(len(deduplicate([first,changed])),1)
        changed.update(source_url='https://else.test/',finnhub_id=first['finnhub_id'])
        self.assertEqual(len(deduplicate([first,changed])),1)

    def test_identity_query_params_are_not_all_stripped(self):
        a=normalize_finnhub_news(article(),'AVGO')
        b=deepcopy(a);b.update(finnhub_id=43,original_headline='Other distinct earnings',source_url='https://publisher.test/article?id=43')
        self.assertEqual(len(deduplicate([a,b])),2)

    def test_multi_ticker_provider_feed_shows_once(self):
        p=Mock();p.get_company_news.return_value=dict(data=[article()],fetched_at=NOW.isoformat(),status='AVAILABLE')
        result=get_live_events(['AVGO','ORCL','NVDA'],now=NOW,provider=p)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['involved_tickers'],['AVGO','NVDA','ORCL'])

    def test_summary_actually_used_and_numeric_evidence_preserved(self):
        raw=article();event=normalize_finnhub_news(raw,'AVGO')
        self.assertIn('86%',str(event['facts']))
        self.assertIn('$29.6 十亿',str(event['facts']))
        self.assertIn('$11.6 十亿',str(event['facts']))
        self.assertEqual(event['original_summary'],raw['summary'])
        self.assertTrue(event['fact_evidence'])
        for number in re.findall(r'\d+(?:\.\d+)?', ' '.join(event['facts'])):
            self.assertIn(number,raw['summary'])
        altered=normalize_finnhub_news(article(summary=raw['summary'].replace('86%','20%')),'AVGO')
        self.assertIn('20%',str(altered['facts']))
        self.assertNotIn('86%',str(altered['facts']))

    def test_chinese_title_source_and_structure(self):
        e=normalize_finnhub_news(article(),'AVGO')
        self.assertEqual(e['headline'],'博通与甲骨文财报将检验AI云基础设施需求是否持续强劲')
        self.assertEqual(e['source_url'],article()['url'])
        self.assertIn('Original Publisher',e['source_name'])
        for key in ['conclusion','facts','why_it_matters','impact_summary','watch_next']:
            self.assertTrue(e[key])
        self.assertGreaterEqual(len(e['facts']),2)
        self.assertLessEqual(len(e['facts']),4)

    def test_short_and_uninterpretable_summaries_explicitly_insufficient(self):
        for summary in ['', 'Earnings update.', 'A long article description with no supported concrete facts, numbers, named products or company events.']:
            e=normalize_finnhub_news(article(summary=summary),'AVGO')
            self.assertEqual(e['facts'],[INSUFFICIENT])
            self.assertEqual(e['summary_status'],'INSUFFICIENT_SUMMARY')

    def test_low_relevance_rejected_and_related_not_evidence(self):
        self.assertIsNone(normalize_finnhub_news(article(headline='Travel tips',summary='Summer holidays are lovely'),'AVGO'))
        self.assertIsNone(normalize_finnhub_news(article(headline='Broadcom shares rise',summary='Analyst raises price target.'),'AVGO'))

    def test_guidance_not_presented_as_actual_or_positive_fact(self):
        e=normalize_finnhub_news(article(headline='Oracle updates revenue guidance',summary='Oracle expects revenue to grow 30% to $19 billion next quarter. The company forecast remains a projection and not reported revenue.'),'ORCL')
        self.assertIn('尚未实现',str(e['facts']))
        self.assertEqual(e['impact_summary']['收入'],'不确定')

    def test_normalization_does_not_mutate_provider_input(self):
        raw=article();before=deepcopy(raw)
        normalize_finnhub_news(raw,'AVGO')
        self.assertEqual(raw,before)

    def test_negative_amount_and_negation_preserved(self):
        e=normalize_finnhub_news(article(headline='Oracle earnings results',summary='Oracle free cash flow was -$1.2 billion this quarter. The company reported the same cash flow figure in its quarterly results announcement.'),'ORCL')
        self.assertIn('-$1.2 十亿',str(e['facts']))
        e=normalize_finnhub_news(article(summary='Broadcom did not report revenue growth of 86%. Oracle denied a revenue forecast of $19 billion and did not confirm those figures.'),'AVGO')
        self.assertEqual(e['facts'],[INSUFFICIENT])

    def test_dedupe_keeps_richer_summary(self):
        weak=normalize_finnhub_news(article(summary='Earnings update.'),'AVGO')
        rich=normalize_finnhub_news(article(),'ORCL')
        merged=deduplicate([weak,rich])
        self.assertEqual(len(merged),1)
        self.assertIn('86%',str(merged[0]['facts']))
