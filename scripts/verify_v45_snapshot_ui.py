"""Offline real-widget check of Cloud export with synthetic production inputs."""
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
from test_v45_snapshot_export import SnapshotExportTests
import production_snapshot_admin as admin
from scripts.verify_peer_isolation import history
test=SnapshotExportTests()
test.setUp()
admin.render_snapshot_export(st,test.client,'u',history_loader=history,
    fundamentals_loader=lambda t:test.financials[t])
'''
    with TemporaryDirectory() as directory:
        path=Path(directory)/'app.py';path.write_text(source,encoding='utf-8')
        app=AppTest.from_file(str(path),default_timeout=20)
        app.secrets['ADMIN_EMAIL']='admin@test.com'
        app.run();assert not app.exception
        next(b for b in app.button if b.label=='运行五股生产分析快照').click().run()
        assert not app.exception
        report=app.session_state['_v45_export_result']['report']
        assert len(report['stocks'])==5
        assert all(s['capture_status']=='COMPLETE' for s in report['stocks'])
        assert len(app.get('download_button'))==2
        app.secrets['ADMIN_EMAIL']='ordinary@test.com'
        app.run();assert not app.exception
        assert len(app.get('download_button'))==0
        assert '_v45_export_result' not in app.session_state
    print('V4.5 snapshot UI: batch, downloads, access revocation PASS')


if __name__=='__main__':main()
