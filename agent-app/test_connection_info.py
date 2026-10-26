import json
from types import SimpleNamespace

import httpx
import pytest
import agent
import accounts
import connection_info as ci


def test_quota_missing_is_not_zero_and_multi_bucket_wins():
    rows = ci.quota_windows({'rateLimits':{'primary':{'usedPercent':99}},'rateLimitsByLimitId':{
        'codex':{'primary':{'usedPercent':25,'windowDurationMins':300,'resetsAt':1800000000},'secondary':{'usedPercent':None}},
        'other':{'primary':{'usedPercent':110,'windowDurationMins':60}}
    }})
    assert [r['remaining_percent'] for r in rows] == [75,None,0]
    assert rows[0]['window_minutes'] == 300
    assert ci.quota_windows({'rateLimits':None}) == []
    assert ci.quota_windows({'rateLimits':{'primary':{'usedPercent':float('nan')}}})[0]['remaining_percent'] is None


def test_codex_identity_comes_from_same_client_as_quota(monkeypatch):
    calls=[]
    class RPC:
        proc=None
        def start(self): pass
        def request(self,method,params):
            calls.append(method)
            if method=='account/read': return {'account':{'type':'chatgpt','email':'person@example.org','planType':'plus','secret':'do-not-return'}}
            return {'rateLimits':{'primary':{'usedPercent':37,'windowDurationMins':300}}}
    monkeypatch.setattr(accounts,'cli_path',lambda _: 'codex.exe')
    monkeypatch.setattr(accounts,'CodexRPC',RPC)
    result=ci.connection_info(agent.ModelSettings(connection='account'))
    assert result['identity']=='person@example.org'
    assert result['plan']=='plus'
    assert result['windows'][0]['remaining_percent']==63
    assert calls==['account/read','account/rateLimits/read']
    assert 'do-not-return' not in json.dumps(result)


def test_api_identity_never_uses_chatgpt_account_or_reveals_key(monkeypatch):
    monkeypatch.setattr(ci,'codex_details',lambda: pytest.fail('Do not read unrelated ChatGPT account'))
    result=ci.connection_info(agent.ModelSettings(api_key='sk-private-value',connection='api'))
    assert result['identity'] is None and len(result['credential_id'])==8
    assert 'sk-private-value' not in json.dumps(result)


def test_deepseek_balance_and_custom_url_no_credential_forwarding(monkeypatch):
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        return httpx.Response(200,json={'balance_infos':[{'currency':'CNY','total_balance':'12.30'}]},request=httpx.Request('GET',url))
    monkeypatch.setattr(ci.httpx,'get',get)
    settings=agent.ModelSettings(provider='deepseek',connection='api',base_url='https://api.deepseek.com/v1',api_key='private')
    result=ci.connection_info(settings)
    assert result['balances']==[{'currency':'CNY','available':12.3}]
    assert calls[0][1]['follow_redirects'] is False
    ci.connection_info(settings.model_copy(update={'base_url':'https://proxy.example/v1'}))
    assert len(calls)==1


def test_claude_identity_is_whitelisted(monkeypatch):
    monkeypatch.setattr(accounts,'cli_path',lambda _: 'claude.exe')
    monkeypatch.setattr(ci.subprocess,'run',lambda *a,**k: SimpleNamespace(stdout=json.dumps({'loggedIn':True,'authMethod':'claude.ai','email':'a@example.org','subscriptionType':'max','accessToken':'secret'})))
    result=ci.claude_details()
    assert result['identity']=='a@example.org' and result['plan']=='max'
    assert 'secret' not in json.dumps(result)
    assert result['windows']==[]


@pytest.mark.parametrize('payload',[None,[],{'balance_infos':None},{'balance_infos':[None]}, {'balance_infos':[{'currency':'CNY','total_balance':'2.00'},None]}])
def test_malformed_balance_is_unavailable_not_partial_or_server_error(monkeypatch,payload):
    monkeypatch.setattr(ci.httpx,'get',lambda url,**kw:httpx.Response(200,json=payload,request=httpx.Request('GET',url)))
    settings=agent.ModelSettings(provider='deepseek',base_url='https://api.deepseek.com',api_key='secret')
    result=ci.connection_info(settings)
    assert result['balances']==[]
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('payload',[None,[],42])
def test_missing_quota_payload_is_unknown(payload):
    assert ci.quota_windows(payload)==[]
