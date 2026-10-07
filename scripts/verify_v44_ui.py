"""Exercise real Streamlit peer widgets with explicitly synthetic data."""
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest


def verify():
    with tempfile.TemporaryDirectory(prefix='stock-peer-ui-') as directory:
        path=Path(directory)/'app.py'
        path.write_text('''
from peer_comparable_ui import render_peer_comparable
from peer_comparable import PeerComparableResult
peer=PeerComparableResult('NVDA','semiconductor_growth',valid=True,applicable=True,
 peer_group='semiconductor_growth',selected_multiple='Forward P/E',
 low=75,mid=100,high=125,confidence='MEDIUM',peers_included=['AVGO','AMD','MRVL'],
 peers_excluded=['TEST'],exclusion_reasons={'TEST':'peer_excluded_as_outlier'})
render_peer_comparable(peer.to_dict(),'diagnostic')
render_peer_comparable(PeerComparableResult('MU','cyclical_semiconductor').to_dict(),'diagnostic')
render_peer_comparable(None)
''',encoding='utf-8')
        app=AppTest.from_file(str(path)).run()
        assert not app.exception,str(app.exception)
        assert any('75.00 / 100.00 / 125.00' in x.value for x in app.markdown)
        assert any('不可用' in x.value for x in app.info)
        assert len(app.get('download_button'))==2
        assert len(app.dataframe)==1
        assert any('不改变内部' in x.value for x in app.caption)
        print('PASS: peer ranges, exclusions, diagnostic caption, JSON downloads and unavailable/history states')


if __name__=='__main__':verify()
