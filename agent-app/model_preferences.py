"""Persist connection preferences, never credentials."""
import json
from urllib.parse import urlsplit


def save(store, settings):
    value = settings.model_dump(exclude={'api_key'})
    # URLs with embedded credentials or query tokens must never reach disk.
    url = urlsplit(value['base_url'])
    if url.username or url.password or url.query or url.fragment:
        raise ValueError('API 地址不能包含账号密码、查询参数或片段；密钥请填专用输入框。')
    folder = store / 'preferences'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'model-settings.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)


def load(store, model):
    try:
        value = json.loads((store / 'preferences/model-settings.json').read_text(encoding='utf-8'))
        value.pop('api_key', None)
        # A remembered API selection has no key after restart; do not claim connection.
        if value.get('connection') == 'api':
            value['enabled'] = False
        return model.model_validate(value)
    except (OSError, ValueError, TypeError):
        return model()
