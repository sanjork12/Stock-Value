"""Offline real-widget check of the administrator simulation switch."""
from pathlib import Path
import json
from tempfile import TemporaryDirectory
from streamlit.testing.v1 import AppTest


def main():
    root=Path(__file__).resolve().parents[1]
    source=f'''
import sys
sys.path.insert(0,{str(root)!r})
import streamlit as st
from unittest.mock import patch
from tests.test_admin_fallback_switch import AdminFallbackSwitchTests
import financial_forensics_admin as admin
test=AdminFallbackSwitchTests()
test.setUp()
with patch.object(admin,'is_cloud_runtime',return_value=True), \
     patch.object(admin,'capture_financial_diagnostic',side_effect=test.capture), \
     patch('analysis_service.fetch_historical_snapshot',return_value=test.row):
    admin.render_financial_diagnostics(st,test.client,'owner')
'''
    with TemporaryDirectory() as directory:
        path=Path(directory)/'app.py'
        path.write_text(source,encoding='utf-8')
        app=AppTest.from_file(str(path),default_timeout=20)
        app.secrets['ADMIN_EMAIL']='admin@example.test'
        app.run()
        assert not app.exception
        assert app.checkbox[0].label=='模拟关键财务输入缺失'
        assert not app.checkbox[0].value
        app.selectbox[0].select('NVDA').run()
        app.checkbox[0].check().run()
        assert any('测试模式：正在模拟实时财务输入缺失' in w.value for w in app.warning)
        next(b for b in app.button if b.label=='Run diagnostic').click().run()
        assert not app.exception
        report=app.session_state['_financial_diagnostic_result']['reports']['NVDA']
        assert report['valuation']['source_status']=='cached_last_reliable'
        displayed=next(json.loads(item.value) for item in app.json if 'final_fair_value' in item.value)
        assert displayed['final_fair_value']==report['valuation']['fair_value']
        assert displayed['final_valuation_mode']==report['valuation']['valuation_mode']
        assert displayed['source_status']=='cached_last_reliable'
        assert displayed['last_reliable_calculated_at']==report['valuation']['calculated_at']
        assert displayed['fallback_reason']=='current_financial_input_incomplete'
        assert any('实时财务输入暂不完整，当前显示最近一次可靠估值。' in w.value for w in app.warning)
        assert any(report['valuation']['calculated_at'] in c.value for c in app.caption)
        app.checkbox[0].uncheck().run()
        assert not any('当前显示最近一次可靠估值' in w.value for w in app.warning)
        next(b for b in app.button if b.label=='Run diagnostic').click().run()
        assert not app.exception
        report=app.session_state['_financial_diagnostic_result']['reports']['NVDA']
        assert report['valuation']['source_status']=='live'
        displayed=next(json.loads(item.value) for item in app.json if 'final_fair_value' in item.value)
        assert displayed['final_fair_value']==report['valuation']['fair_value']
        assert displayed['final_valuation_mode']==report['valuation']['valuation_mode']
        assert displayed['source_status']=='live'
        assert displayed['last_reliable_calculated_at'] is None
        assert displayed['fallback_reason'] is None
        assert report['fields']['eps.forward_eps']['value'] is not None
        # AMZN must also cache after EPS loss even though its class permits a
        # statement proxy during normal normalization. Keep the DCF guard real.
        amzn_source=source.replace('test.setUp()', '''test.setUp()
from tests.test_single_source_valuation_inputs import amzn_inputs,analyze_amzn
from last_reliable_valuation import reliable_snapshot
test.raw=amzn_inputs()
test.row={'raw':{'last_reliable':reliable_snapshot(analyze_amzn())}}''')
        path.write_text(amzn_source,encoding='utf-8')
        amzn=AppTest.from_file(str(path),default_timeout=20)
        amzn.secrets['ADMIN_EMAIL']='admin@example.test'
        amzn.run()
        amzn.selectbox[0].select('AMZN').run()
        amzn.checkbox[0].check().run()
        next(b for b in amzn.button if b.label=='Run diagnostic').click().run()
        assert not amzn.exception
        report=amzn.session_state['_financial_diagnostic_result']['reports']['AMZN']
        assert not report['valuation_failure_trace']['available']
        assert report['valuation']['source_status']=='cached_last_reliable'
        displayed=next(json.loads(item.value) for item in amzn.json if 'final_fair_value' in item.value)
        assert displayed['final_fair_value']==report['valuation']['fair_value']
        assert displayed['last_reliable_calculated_at']==report['valuation']['calculated_at']
        assert displayed['fallback_reason']=='current_financial_input_incomplete'
    print('Administrator fallback switch: simulated cache display and restored live UI PASS')


if __name__=='__main__':main()
