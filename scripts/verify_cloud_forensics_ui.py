"""Real Streamlit admin widget verification using explicit test doubles only."""
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest


def verify():
    source='''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'tests'))
import streamlit as st
from unittest.mock import patch
from test_cloud_financial_forensics import ForensicsTests,YahooFixture,client
import financial_forensics_admin as admin
admin._LAST_RUN.clear()
report=ForensicsTests().capture(fixture=YahooFixture(partial=True))
report['environment']['runtime']='STREAMLIT_CLOUD'
with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'capture_financial_diagnostic',return_value=report):
    admin.render_financial_diagnostics(st,client(),'u1')
'''
    with tempfile.TemporaryDirectory(prefix='financial-forensics-ui-') as directory:
        path=Path(directory)/'app.py';path.write_text(source,encoding='utf-8')
        app=AppTest.from_file(str(path),default_timeout=20)
        app.secrets['ADMIN_EMAIL']='admin@example.test'
        app.run()
        assert not app.exception,str(app.exception)
        assert list(app.selectbox[0].options)==['AVGO','NVDA','MU','PLTR','COIN','CRCL','AMZN','MSFT']
        app.selectbox[0].select('NVDA').run()
        next(button for button in app.button if button.label=='Run diagnostic').click().run()
        assert not app.exception,str(app.exception)
        assert any('UNAVAILABLE because: forward_and_trailing_eps_unavailable' in x.value for x in app.warning)
        assert len(app.dataframe)==2
        assert len(app.get('download_button'))==1
        assert len(app.get('file_uploader'))==1
        assert app.session_state['_financial_diagnostic_result']['owner']=='u1'
        print('PASS: actual admin widgets, allowed tickers, explicit failure trace, field/model tables and JSON download')
        failure_path=Path(directory)/'failure.py'
        failure_path.write_text(source.replace('return_value=report','side_effect=TypeError("fixture-private-token")'),encoding='utf-8')
        failed=AppTest.from_file(str(failure_path),default_timeout=20)
        failed.secrets['ADMIN_EMAIL']='admin@example.test'
        failed.run()
        next(button for button in failed.button if button.label=='Run diagnostic').click().run()
        assert not failed.exception,str(failed.exception)
        assert any('CAPTURE_INPUTS' in item.value and 'TYPE_ERROR' in item.value for item in failed.error)
        assert all('fixture-private-token' not in item.value for item in failed.error)
        assert len(failed.get('download_button'))==1
        print('PASS: failed Cloud run renders sanitized stage/category and downloadable error JSON')


if __name__=='__main__':verify()
