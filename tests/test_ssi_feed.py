"""Documented SSI v3 contracts; synthetic fixtures, no credentials/network."""
from datetime import datetime
import json,time,sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.data import ssi_feed as feed
from src.data.ssi_feed import SSISession,SSIAPIError,normalize_board,event_time,VN

@pytest.fixture(autouse=True)
def isolation(monkeypatch,tmp_path):
    monkeypatch.setattr(feed,'CACHE',tmp_path/'latest.json')

def response(status=200,data=None):return SimpleNamespace(status_code=status,json=lambda:data,headers={})

def client(tmp_path,http=None):
    env=tmp_path/'.env';env.write_text('SSI_API_KEY=TEST_KEY\nSSI_API_SECRET=TEST_SECRET\nSSI_PRIVATE_KEY=UNUSED_RSA\n')
    http=http or Mock()
    http.post.return_value=response(data={'accessToken':'MEMORY_TOKEN','refreshToken':'MEMORY_REFRESH','expiresAt':time.time()+900,'refreshExpiresAt':time.time()+86400})
    c=SSISession(env,http=http);c._pace=lambda:None
    return c

def raw(symbol='FPT'):
    return {'symbol':symbol,'board':'HOSE','stockType':'Stock','lotSize':'100','symbolNameVi':'Synthetic',
        'price':'50100','refPrice':'50000','volume':'12345','average':'50050',
        'book_time':'2026/11/09 09:30:00','trade_time':'2026/11/09 09:30:00.001',
        'bids':[['50000','1000'],['49950','2000'],['49900','3000']],
        'asks':[['50100','1500'],['50200','2500'],['50300','3500']]}

def now():return datetime(2026,11,9,9,30,tzinfo=VN)

def test_price_volume_and_proxy_units_are_explicit():
    r=normalize_board([raw()],['FPT'],now=now())[0]
    assert r['last_price_vnd']==50100 and r['bids'][0]['volume']==1000
    assert r['cumulative_turnover_proxy_vnd']==50050*12345
    assert 'cumulative_turnover_vnd' not in r and r['turnover_basis']=='avg_match_price_times_volume_proxy'
    assert r['exchange_time']=='2026-11-09T09:30:00+07:00' and r['provider_market_status'] is None
    assert r['phase']=='receiver_clock_estimate' and r['change_percent']==pytest.approx(.2)

@pytest.mark.parametrize('kind,value,flag',[
    ('bids',[['ATO','1000']],'auction_observation'),('asks',[],'incomplete_levels'),
    ('board','HNX','unsupported_market_or_instrument'),('stockType','CoveredWarrant','unsupported_market_or_instrument'),
    ('book_time','2026/11/06 09:30:00','stale_or_missing_book_event')])
def test_bad_or_stale_books_cannot_become_valid(kind,value,flag):
    r=raw();r[kind]=value
    assert flag in normalize_board([r],['FPT'],now=now())[0]['book_flags']

def test_connection_gap_invalidates_old_book_even_with_recent_timestamp():
    r=raw();r['book_generation']=1
    flags=normalize_board([r],['FPT'],now=now(),connected=False,generation=2)[0]['book_flags']
    assert 'stream_disconnected' in flags and 'book_from_previous_connection' in flags

def test_auth_does_not_use_rsa_or_otp_and_never_persists_tokens(tmp_path):
    c=client(tmp_path)
    call=c.http.post.call_args
    assert call.args[0]==feed.AUTH_URL
    assert call.kwargs['json']=={'apiKey':'TEST_KEY','apiSecret':'TEST_SECRET'}
    assert call.kwargs['allow_redirects'] is False
    assert 'MEMORY_TOKEN' not in c.env_file.read_text()
    assert not any(s in json.dumps(c.public_auth()) for s in ('TEST_KEY','TEST_SECRET','UNUSED_RSA','MEMORY_TOKEN','MEMORY_REFRESH'))

def test_refresh_rotates_in_memory_without_reusing_old_refresh(tmp_path):
    c=client(tmp_path);c._expires=time.time()-1
    c.http.post.return_value=response(data={'accessToken':'NEW_TOKEN','refreshToken':'NEW_REFRESH','expiresAt':time.time()+900,'refreshExpiresAt':time.time()+86400})
    c._ensure_token()
    assert c.http.post.call_args.args[0].endswith('/auth/refresh')
    assert c.http.post.call_args.kwargs['json']=={'refreshToken':'MEMORY_REFRESH'}
    assert c._refresh=='NEW_REFRESH' and c._token=='NEW_TOKEN'

def add_second_pair(c,key='SECOND_KEY',secret='SECOND_SECRET'):
    with c.env_file.open('a') as handle:handle.write(f'SSI_API_KEY_2={key}\nSSI_API_SECRET_2={secret}\n')

def test_two_values_are_one_auth_pair_not_two_rotating_keys(tmp_path):
    c=client(tmp_path)
    assert c.public_auth()['credential_profiles']==1
    assert c.public_auth()['active_credential_slot']==1
    assert not c._failover_credentials()
    assert c.http.post.call_count==1

def test_incomplete_or_same_key_second_profile_is_not_an_independent_pair(tmp_path):
    c=client(tmp_path)
    add_second_pair(c,secret='')
    assert not c._failover_credentials()
    c.env_file.write_text('SSI_API_KEY=TEST_KEY\nSSI_API_SECRET=TEST_SECRET\nSSI_API_KEY_2=TEST_KEY\nSSI_API_SECRET_2=OTHER_SECRET\n')
    assert not c._failover_credentials()
    assert c.public_auth()['credential_profiles']==1

def test_auth_uses_second_complete_pair_when_first_is_rejected(tmp_path):
    env=tmp_path/'.env'
    env.write_text('SSI_API_KEY=FIRST_KEY\nSSI_API_SECRET=FIRST_SECRET\nSSI_API_KEY_2=SECOND_KEY\nSSI_API_SECRET_2=SECOND_SECRET\n')
    http=Mock();http.post.side_effect=[response(401),response(data={'accessToken':'SECOND_TOKEN','expiresAt':time.time()+900})]
    c=SSISession(env,http=http)
    assert c.public_auth()['active_credential_slot']==2
    assert http.post.call_count==2
    assert [call.kwargs['json']['apiKey'] for call in http.post.call_args_list]==['FIRST_KEY','SECOND_KEY']
    assert not any(value in json.dumps(c.public_auth()) for value in ('FIRST_KEY','FIRST_SECRET','SECOND_KEY','SECOND_SECRET','SECOND_TOKEN'))

def test_market_access_failure_switches_once_and_retries_with_new_token(tmp_path):
    c=client(tmp_path);add_second_pair(c);c.http.post.reset_mock()
    c.http.post.return_value=response(data={'accessToken':'SECOND_TOKEN','expiresAt':time.time()+900})
    c.http.get.side_effect=[response(401),response(data=[])]
    assert c._get('/api/v3/data/masterdata',{})==[]
    assert c.http.post.call_count==1 and c.http.get.call_count==2
    assert c.http.post.call_args.kwargs['json']=={'apiKey':'SECOND_KEY','apiSecret':'SECOND_SECRET'}
    assert c.http.get.call_args.kwargs['headers']=={'Authorization':'Bearer SECOND_TOKEN'}
    assert c.public_auth()['credential_switches']==1
    assert not c._failover_credentials()  # Failed primary is cooling down.

def test_two_market_access_failures_stop_after_one_switch(tmp_path):
    c=client(tmp_path);add_second_pair(c);c.http.get.return_value=response(403)
    with pytest.raises(SSIAPIError,match='market_access_denied'):c._get('/api/v3/data/masterdata',{})
    assert c.http.get.call_count==2 and c.http.post.call_count==2

def test_switch_invalidates_old_connection_book_until_a_new_quote(tmp_path):
    c=client(tmp_path);add_second_pair(c);c._generation=4;c._ws=Mock()
    row=raw();row['book_generation']=4
    assert c._failover_credentials()
    assert 'book_from_previous_connection' in normalize_board([row],['FPT'],now=now(),generation=c._generation)[0]['book_flags']
    c._ws.close.assert_called_once()

@pytest.mark.parametrize('scope',['auth','market'])
def test_rate_limit_respects_reset_without_switching_key(tmp_path,scope):
    c=client(tmp_path);add_second_pair(c);c.http.post.reset_mock()
    limited=response(429);limited.headers={'Retry-After':'120','X-RATELIMIT-RESET':str(time.time()+240)}
    if scope=='auth':
        c._token='';c._refresh='';c.http.post.return_value=limited;action=c._ensure_token
    else:
        c.http.get.return_value=limited;action=lambda:c._get('/api/v3/data/masterdata',{})
    with pytest.raises(SSIAPIError,match='rate_limited') as error:action()
    assert 235<error.value.retry_after<=240
    assert c.public_auth()['active_credential_slot']==1 and c.public_auth()['credential_switches']==0
    assert c.http.post.call_count==(1 if scope=='auth' else 0)

def test_empty_market_response_does_not_cycle_credentials(tmp_path):
    c=client(tmp_path);add_second_pair(c);c.http.post.reset_mock();c.http.get.return_value=response(data=[])
    assert c._get('/api/v3/data/masterdata',{})==[]
    c.http.post.assert_not_called()
    assert c.public_auth()['credential_switches']==0

def test_block_all_nonmarket_endpoints_before_http(tmp_path):
    c=client(tmp_path)
    for path in ('/api/v3/trading/order','/api/v3/account/info','/api/v3/auth/requestOtp','https://example.com'):
        with pytest.raises(SSIAPIError,match='endpoint_not_allowed'):c._get(path,{})
    c.http.get.assert_not_called()

def test_market_401_is_sanitized_without_auth_retry_storm(tmp_path):
    c=client(tmp_path);c.http.post.reset_mock();c.http.get.return_value=response(401,{'msg':'SECRET'})
    with pytest.raises(SSIAPIError,match='market_access_denied') as exc:c._get('/api/v3/data/masterdata',{})
    assert exc.value.http_status==401 and 'SECRET' not in str(exc.value)
    c.http.post.assert_not_called()

def test_accept_only_selected_market_topics_and_replace_all_levels(tmp_path):
    c=client(tmp_path);c._rows={'FPT':raw()};c._generation=4
    assert c._accept_frame({'channel':'DATA','topic':'quote.FPT','data':{'s':'FPT','t':'2026/11/09 09:31:00','bids':[['50000','1']],'asks':[]}})
    assert c._rows['FPT']['asks']==[] and len(c._rows['FPT']['bids'])==1
    assert c._rows['FPT']['book_generation']==4
    assert not c._accept_frame({'channel':'TRADING','topic':'order.private','data':{'s':'FPT'}})
    assert not c._accept_frame({'channel':'DATA','topic':'quote.XXX','data':{'s':'XXX'}})

def test_drop_duplicates_and_out_of_order_messages(tmp_path):
    c=client(tmp_path);c._rows={'FPT':raw()}
    frame={'channel':'DATA','topic':'trade.FPT','data':{'s':'FPT','t':'2026/11/09 09:31:00','p':'50100','a':'50050','v':'12400'}}
    assert c._accept_frame(frame) and not c._accept_frame(frame)
    frame['data']['t']='2026/11/09 09:29:00'
    assert not c._accept_frame(frame)
    assert c.public_auth()['duplicate_events']==1 and c.public_auth()['late_events']==1

def test_stream_raw_archive_never_contains_auth_or_private_channels(tmp_path):
    c=client(tmp_path);c._rows={'FPT':raw()}
    c._accept_frame({'channel':'DATA','topic':'quote.FPT','data':{'s':'FPT','t':'2026/11/09 09:31:00','bids':[],'asks':[]}})
    c._accept_frame({'channel':'TRADING','topic':'order.private','data':{'secret':'SHOULD_NOT_SAVE'}})
    c._flush_events()
    with sqlite3.connect(feed.CACHE.with_name('events.sqlite3')) as db:
        records=db.execute('SELECT payload FROM events').fetchall()
    assert len(records)==1 and 'SHOULD_NOT_SAVE' not in records[0][0] and 'MEMORY_TOKEN' not in records[0][0]

def test_membership_from_provider_only_and_exact_subset(tmp_path):
    c=client(tmp_path);c.universe_group='VN100';core=['FPT']+[f'A{i:02}' for i in range(29)]
    def get(path,params):return [{'symbol':s,'board':'HOSE','stockType':'Stock'} for s in (core if params['index']=='VN30' else core+[f'B{i:02}' for i in range(70)])]
    c._get=get;c._membership()
    assert len(c._groups['VN30'])==30 and len(c._groups['VN100'])==100
    assert set(c._groups['VN30'])<=set(c._groups['VN100'])

def test_incomplete_membership_is_not_relabelled(tmp_path):
    c=client(tmp_path);c._get=lambda *a:[{'symbol':'FPT','board':'HOSE','stockType':'Stock'}]
    with pytest.raises(SSIAPIError,match='unexpected_membership_count'):c._membership()

def test_reject_cache_of_another_provider(tmp_path):
    path=tmp_path/'old.json';path.write_text(json.dumps({'schema_version':2,'source':'other_provider'}))
    with pytest.raises(ValueError):feed.load_snapshot(path)

def test_unknown_phase_flag_is_preserved_and_not_assumed_continuous(tmp_path):
    c=client(tmp_path);c._rows={'FPT':raw()}
    assert c._accept_frame({'channel':'DATA','topic':'market.flag','data':{'b':'HOSE','f':'UNKNOWN','t':'2026/11/09 09:31:00'}})
    assert c._rows['FPT']['market_status']=='UNKNOWN'

def test_date_parser_does_not_create_current_date_for_partial_time():
    assert event_time('09:30:00') is None and event_time('garbage') is None
    assert event_time('2026/11/09 09:30:00.123').microsecond==123000
