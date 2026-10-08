"""Offline Streamlit widget verification; never contacts public providers."""
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
from unittest.mock import patch
from test_peer_diagnostic_admin import PeerAdminTests
from test_peer_review_report import PublicFixture
import peer_diagnostic_admin as admin
test=PeerAdminTests()
test.setUp()
original=admin.run_cloud_peer_diagnostic
def run(client,user,secrets,tickers):
    return original(client,user,secrets,tickers,provider=PublicFixture(),internal_loader=lambda _:test.baseline)
with patch.object(admin,'run_cloud_peer_diagnostic',side_effect=run):
    admin.render_peer_diagnostics(st,test.client,'u')
'''
    with TemporaryDirectory() as directory:
        path=Path(directory)/'app.py';path.write_text(source,encoding='utf-8')
        app=AppTest.from_file(str(path),default_timeout=20)
        app.secrets['ADMIN_EMAIL']='admin@test.com'
        app.run()
        assert not app.exception
        next(b for b in app.button if b.label=='运行单股诊断').click().run()
        assert not app.exception
        assert len(app.session_state['_peer_diagnostic_result']['report']['comparison'])==1
        next(b for b in app.button if b.label=='运行五股诊断').click().run()
        assert not app.exception
        assert len(app.session_state['_peer_diagnostic_result']['report']['comparison'])==5
        assert len(app.get('download_button'))==2
        app.secrets['ADMIN_EMAIL']='ordinary@test.com'
        app.run()
        assert not app.exception
        assert len(app.get('download_button'))==0
        assert '_peer_diagnostic_result' not in app.session_state
    print('Peer admin UI: single, batch, downloads and access revocation PASS')


if __name__=='__main__':main()
