"""Run real Streamlit widgets without Cloud credentials or production API calls."""
import ast
from pathlib import Path
import sys
import textwrap
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest


def verify():
    temporary_apps = tempfile.TemporaryDirectory(prefix='stock-value-ui-')
    def app_from_source(text, name):
        path = Path(temporary_apps.name) / name
        path.write_text(text, encoding='utf-8')
        return AppTest.from_file(str(path))
    source = (ROOT / 'streamlit_app.py').read_text(encoding='utf-8')
    navigation = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'open_headlines')
    navigation_source = ast.get_source_segment(source, navigation)
    prelude = '''
import streamlit as st
from unittest.mock import patch
from datetime import datetime, timezone
from industry.company_panels import render_earnings_inline, render_latest_event_teaser
from industry.news.finnhub_live import normalize_finnhub_news
from industry.news.schema import translate_ui_term
raw = dict(id=42, headline='Broadcom, Oracle Earnings to Test Cloud Infrastructure AI Momentum',
 summary='Broadcom and Oracle will report earnings this week. Broadcom revenue grew 86% to $29.6 billion. Oracle cloud revenue increased 62% to $11.6 billion.',
 related='AVGO,ORCL,NVDA', url='https://publisher.test/story', source='Publisher',
 datetime=datetime.now(timezone.utc).timestamp())
event = normalize_finnhub_news(raw, 'AVGO')
def normalize_ticker(t): return t.upper()
'''
    panels = app_from_source(prelude + '\n' + navigation_source + '''
render_earnings_inline('AMZN')
render_earnings_inline('MU')
with patch('industry.company_panels.get_company_events', return_value=[event]):
    render_latest_event_teaser('AVGO', open_headlines_cb=open_headlines)
''', 'panels.py').run()
    assert not panels.exception, str(panels.exception)
    assert any(m.value == '$200.6B' and m.label == '营收' for m in panels.metric)
    assert any(m.value == '+379%' and m.label == '同比' for m in panels.metric)
    panels.button[0].click().run()
    assert not panels.exception, str(panels.exception)
    assert panels.session_state['headline_selected_event_id'] == panels.session_state['headline_selected_event']['event_id']
    assert panels.session_state['headline_range'] == '本季度'
    assert panels.session_state['_pending_nav_page'] == '头等大事'

    # Execute the production detail-rendering block, isolating only Auth/database
    # startup. This keeps the real widgets and fields under test.
    start = source.index('        for i, e in enumerate(show_rows):')
    end = source.index('\n\n\nelse:\n    st.info("未知页面。")', start)
    detail_block = textwrap.dedent(source[start:end])
    details = app_from_source(prelude + '''
st.session_state['headline_selected_event_id'] = event['event_id']
show_rows = [event]
def open_single_stock(t): pass
''' + detail_block, 'details.py').run()
    assert not details.exception, str(details.exception)
    assert details.expander[0].proto.expanded
    assert 'AVGO / NVDA / ORCL' in details.expander[0].label
    assert any('【一句话结论】' in m.value for m in details.markdown)
    assert any('【发生了什么】' in m.value for m in details.markdown)
    assert any('【影响判断】' in m.value for m in details.markdown)
    assert any('https://publisher.test/story' in m.value for m in details.markdown)
    print('PASS: real Streamlit financial panels, event-id navigation, matching expanded detail and source link')


if __name__ == '__main__':
    verify()
