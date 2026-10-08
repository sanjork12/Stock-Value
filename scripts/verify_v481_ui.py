"""Offline real Streamlit widget validation; fixtures never enter deployed UI."""
from pathlib import Path
from tempfile import TemporaryDirectory
from streamlit.testing.v1 import AppTest


def main():
    root=Path(__file__).resolve().parents[1]
    source=f'''
import sys
sys.path.insert(0,{str(root)!r})
sys.path.insert(0,{str(root/'tests')!r})
import streamlit as st
from unittest.mock import Mock,patch
import input_resilience_admin as admin
from test_input_resilience_audit import Yahoo,provider
from test_quality_acquisition import Healthy
original=admin.run_cloud_audit
def offline(*args,**kwargs):
    kwargs.update(yahoo_factory=Yahoo,provider=provider())
    return original(*args,**kwargs)
simulation=admin.run_cloud_simulation
def simulate(*args,**kwargs):
    kwargs.update(factory=Healthy,provider=provider())
    return simulation(*args,**kwargs)
with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'verified_admin',return_value=not st.session_state.get('deny',False)),patch.object(admin,'run_cloud_audit',side_effect=offline),patch.object(admin,'run_cloud_simulation',side_effect=simulate):
    admin.render_input_resilience(st,Mock(),'u')
'''
    with TemporaryDirectory() as directory:
        path=Path(directory)/'app.py';path.write_text(source,encoding='utf-8')
        app=AppTest.from_file(str(path),default_timeout=20)
        app.secrets['ADMIN_EMAIL']='admin@example.com'
        app.secrets['FINNHUB_API_KEY']='fake-secret'
        app.run();assert not app.exception
        next(b for b in app.button if b.label=='运行五股 Provider Audit').click().run()
        assert not app.exception
        report=app.session_state['_v481_result']['report']
        assert len(report['stocks'])==5
        assert len(app.dataframe)==1 and len(app.expander)==5
        assert len(app.get('download_button'))==1
        assert 'fake-secret' not in str(report)
        next(b for b in app.button if b.label=='运行五股 Acquisition Simulation').click().run()
        assert not app.exception
        simulated=app.session_state['_v482_simulation']['report']
        assert len(simulated['stocks'])==5
        assert all(len(s['scenarios'])==5 for s in simulated['stocks'])
        assert not simulated['production_cache_write']
        assert len(app.get('download_button'))==2
        app.session_state['deny']=True;app.run()
        assert not app.exception
        assert '_v481_result' not in app.session_state
        assert '_v482_simulation' not in app.session_state
        assert len(app.get('download_button'))==0
    print('V4.8.1 UI PASS: batch, summary, expanders, export, access revocation')


if __name__=='__main__':main()
