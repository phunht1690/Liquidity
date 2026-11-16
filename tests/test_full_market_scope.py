"""Full-board coverage and compatibility with genuine older pilot captures."""
from copy import deepcopy
from datetime import datetime
import pytest

from src.data.market_rules import resolve_universe
from src.data.ssi_feed import SSIAPIError,VN
from src.data.ssi_runtime import collector_settings,poll_delay,store_snapshot
from src.data.product import build_product
from src.data.chart_archive import read_chart_archive
from tests.test_ssi_feed import client
from tests.test_live_analytics import snapshots,config


def catalogs():
    return {board:[{'symbol':f'{prefix}{i:03}','board':board,'stockType':'Stock','lotSize':100}
        for i in range(count)] for board,prefix,count in [('HOSE','A',409),('HNX','H',299),('UPCOM','U',809)]}


def provider(catalog):
    def get(path,query):
        if 'index' in query:return catalog['HOSE'][:30 if query['index']=='VN30' else 100]
        board=query['board']
        return catalog[board]+[{'symbol':'ZZ99','board':board,'stockType':'Bond'},
            {'symbol':'OLD','board':board,'stockType':'Stock','lastTradingDate':'2000/01/01'},
            {'symbol':'NEW','board':board,'stockType':'Stock','firstTradingDate':'2099/01/01'},
            {'symbol':'../BAD','board':board,'stockType':'Stock'}]
    return get


def test_full_market_has_all_active_cash_equities_and_no_duplicate_index_rows(tmp_path):
    session=client(tmp_path);session.universe_group='ALL';session._get=provider(catalogs());session._membership()
    assert {k:len(v) for k,v in session._groups.items()}=={'VN30':30,'VN100':100,'HOSE':409,'HNX':299,'UPCOM':809}
    assert len(session._rows)==1517
    assert set(session._groups['VN30'])<=set(session._groups['VN100'])<=set(session._groups['HOSE'])
    assert not any(k.endswith('_PILOT') for k in session._groups)
    assert session._universe_labels['HNX']=='HNX' and session._catalog_counts['UPCOM']==809


def test_catalog_outage_keeps_verified_cached_board_instead_of_shrinking_scope(tmp_path):
    session=client(tmp_path);session.universe_group='ALL';get=provider(catalogs());session._get=get;session._membership()
    session._membership_day=None
    def temporary(path,query):
        if query.get('board')=='HNX':raise SSIAPIError('source_unavailable',503)
        return get(path,query)
    session._get=temporary;session._membership()
    assert len(session._groups['HNX'])==299 and session._membership_provenance['HNX']=='saved_ssi_board_catalog'
    assert any('HNX' in warning for warning in session._metadata_warnings)


def test_legacy_hose_mode_retains_its_explicit_pilot_labels(tmp_path):
    session=client(tmp_path);session.universe_group='HOSE';session._get=provider(catalogs());session._membership()
    assert len(session._groups['HOSE'])==409 and len(session._groups['HNX_PILOT'])==15
    assert 'HNX' not in session._groups


def test_all_market_sampling_continues_through_upcom_afternoon():
    settings=collector_settings({'ssi':{'universe_group':'ALL','live_poll_seconds':5,'off_hours_poll_seconds':30}})
    assert settings['universe_group']=='ALL'
    assert poll_delay(settings,datetime(2026,11,16,14,55,tzinfo=VN))==5
    assert poll_delay(settings,datetime(2026,11,16,15,1,tzinfo=VN))==30


def pilot_series():
    series=deepcopy(snapshots(2))
    for snapshot in series:
        row=snapshot['quotes'][0];row.update(symbol='PVS',market_code='HNX',units_verified=True)
        snapshot['quotes']=[row]
        snapshot['membership'].update(universes={'HNX_PILOT':['PVS']},labels={'HNX_PILOT':'HNX · thử nghiệm'})
    return series


def test_full_board_request_does_not_relabel_old_pilot_archive(tmp_path):
    series=pilot_series();database=tmp_path/'saved.sqlite3'
    for snapshot in series:store_snapshot(snapshot,database=database,cache=tmp_path/'latest.json')
    result=read_chart_archive({'universe':['HNX'],'symbol':['PVS']},config(),database=database)
    assert result['universe']=='HNX_PILOT' and result['requested_universe']=='HNX'
    assert len(result['symbols'])==1 and result['universes'][0]['label']=='HNX · thử nghiệm'


def test_existing_browser_pilot_selection_resolves_to_new_full_board():
    series=pilot_series()
    for snapshot in series:snapshot['membership'].update(universes={'HNX':['PVS']},labels={'HNX':'HNX'})
    result=build_product({'universe':['HNX_PILOT'],'symbol':['PVS']},series,{'now':series[-1]['captured_at'],'latest_snapshot':series[-1]},config())
    assert result['universe']=='HNX' and result['available_universes'][0]['pilot'] is False
    assert resolve_universe({'UPCOM':['ACV']},'UPCOM_PILOT')=='UPCOM'
    assert resolve_universe({'UPCOM_PILOT':['ACV']},'UPCOM')=='UPCOM_PILOT'
    with pytest.raises(ValueError):build_product({'universe':['ALL']},series,{'latest_snapshot':series[-1]},config())
