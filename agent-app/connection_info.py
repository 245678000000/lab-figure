"""Read-only identity and quota summaries. Never return or persist credentials."""
import hashlib
import math
import time
import subprocess
import json
from urllib.parse import urlsplit

import httpx
import accounts

CONSOLES = {
    'openai': 'https://platform.openai.com/usage',
    'claude': 'https://claude.ai/settings/usage',
    'deepseek': 'https://platform.deepseek.com/usage',
    'glm': 'https://open.bigmodel.cn/',
    'kimi': 'https://www.kimi.com/code/console',
    'qwen': 'https://bailian.console.aliyun.com/',
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def quota_windows(payload):
    if not isinstance(payload, dict):
        return []
    buckets = payload.get('rateLimitsByLimitId')
    if not isinstance(buckets, dict) or not buckets:
        old = payload.get('rateLimits')
        buckets = {old.get('limitId') or 'codex': old} if isinstance(old, dict) else {}
    rows = []
    for key, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        for period in ('primary', 'secondary'):
            window = bucket.get(period)
            if not isinstance(window, dict):
                continue
            used, duration, reset = (window.get(k) for k in ('usedPercent','windowDurationMins','resetsAt'))
            rows.append({'bucket':str(bucket.get('limitName') or key), 'period':period,
                         'remaining_percent':round(max(0,min(100,100-used)),1) if finite(used) else None,
                         'window_minutes':duration if finite(duration) and duration>0 else None,
                         'resets_at':reset if finite(reset) and reset>0 else None})
    return rows


def codex_details():
    result = dict(identity=None, plan=None, logged_in=None, windows=[], quota_message='尚未读取额度', message='无法确认登录状态')
    if not accounts.cli_path('codex'):
        result.update(logged_in=False,message='未安装 Codex 官方客户端',quota_message='请先安装并登录')
        return result
    # A fresh read sees account switches made by the official CLI outside this app.
    rpc = accounts.CodexRPC()
    try:
        rpc.start()
        response = rpc.request('account/read', {'refreshToken':False})
        if not isinstance(response, dict):
            raise ValueError('Invalid account response')
        account = response.get('account')
        if account is not None and not isinstance(account, dict):
            raise ValueError('Invalid account response')
        if not account or account.get('type') != 'chatgpt':
            result.update(logged_in=False,message='Codex 当前未使用 ChatGPT 账号登录',quota_message='账号未登录，无法读取订阅额度')
            return result
        result.update(logged_in=True, identity=account.get('email'), plan=account.get('planType'), message='官方客户端已登录')
        try:
            result['windows'] = quota_windows(rpc.request('account/rateLimits/read', {}))
            result['quota_message'] = '账号共享额度，非本应用独占' if result['windows'] else '官方接口暂未返回额度'
        except (ValueError, OSError):
            result['quota_message'] = '额度读取失败，请稍后刷新；不代表额度为零'
    except (ValueError, OSError):
        result['quota_message'] = '账号状态读取失败，无法确认额度'
    finally:
        if rpc.proc is not None:
            if rpc.proc.poll() is None:
                rpc.proc.terminate()
            try:
                rpc.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                rpc.proc.kill()
            for stream in (rpc.proc.stdin, rpc.proc.stdout):
                if stream:
                    stream.close()
    return result


def claude_details():
    result = dict(identity=None, plan=None, logged_in=None, windows=[],
                  quota_message='当前接入方式不提供订阅额度，请在官方用量页查看', message='无法确认登录状态')
    executable = accounts.cli_path('claude')
    if not executable:
        result.update(logged_in=False,message='未安装 Claude Code')
        return result
    try:
        reply = subprocess.run([executable,'auth','status'], capture_output=True,text=True,encoding='utf-8',
                               errors='replace',timeout=15,env=accounts.safe_env(),creationflags=accounts.FLAGS)
        data = json.loads(reply.stdout)
        if not isinstance(data, dict):
            raise ValueError('Invalid account response')
        logged = bool(data.get('loggedIn')) and data.get('authMethod') in ('claude.ai','oauth_token')
        result.update(logged_in=logged,identity=data.get('email') if logged else None,
                      plan=data.get('subscriptionType') if logged else None,
                      message='官方客户端已登录' if logged else '未使用 Claude 订阅账号登录')
    except (OSError,ValueError,subprocess.SubprocessError):
        pass
    return result


def connection_info(settings):
    provider = settings.provider
    info = {'provider':provider,'provider_name':accounts.PROVIDERS[provider]['name'],
            'connection':settings.connection,'enabled':settings.enabled,'model':settings.model or '客户端默认模型',
            'identity':None,'plan':None,'logged_in':None,'windows':[],'balances':[],
            'checked_at':time.time(),'console_url':CONSOLES.get(provider),
            'message':'','quota_message':'当前接入方式未提供额度查询，请查看服务商控制台'}
    if settings.connection == 'account':
        bridge = accounts.PROVIDERS[provider]['account']
        if bridge == 'codex':
            info.update(codex_details())
            info['console_url'] = 'https://chatgpt.com/codex/settings/usage'
        elif bridge == 'claude':
            info.update(claude_details())
        else:
            status = accounts.account_status(bridge) if bridge else {}
            info['message'] = status.get('message','此平台不支持账号登录')
            info['quota_message'] = '当前客户端桥接无法查询账号身份及额度，请在官方控制台核对'
        return info
    url = urlsplit(settings.base_url)
    info['endpoint'] = url.netloc
    info['model'] = settings.model or '未设置模型'
    if not settings.api_key:
        info.update(message='未设置 API 密钥',quota_message='填写密钥后可查询支持的平台')
        return info
    info['credential_id'] = hashlib.sha256(settings.api_key.encode()).hexdigest()[:8]
    info['message'] = '已配置 API 密钥；密钥不提供登录邮箱'
    # Never send a proxy/custom endpoint credential to a different service.
    if provider == 'deepseek' and settings.base_url.rstrip('/') in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
        try:
            reply = httpx.get('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+settings.api_key},
                              timeout=10,follow_redirects=False)
            reply.raise_for_status()
            data = reply.json()
            if not isinstance(data, dict):
                raise ValueError('Invalid balance response')
            for row in data.get('balance_infos',[]):
                if not isinstance(row, dict):
                    raise ValueError('Invalid balance row')
                amount = float(row['total_balance'])
                if math.isfinite(amount) and row.get('currency') in ('CNY','USD'):
                    info['balances'].append({'currency':row['currency'],'available':amount})
            info['quota_message'] = 'API 可用余额（含赠送和充值）' if info['balances'] else '接口未返回可用余额'
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            info['balances'] = []
            info['quota_message'] = '余额读取失败，请核对密钥或稍后刷新；不代表余额为零'
    return info
