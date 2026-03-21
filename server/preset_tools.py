import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.settings')
django.setup()

from gateway.models import Tool, ToolVersion, ToolRelease


def create_or_update_preset_tool(tool_id, name, description, code, entry_point, schema, message='preset seed'):
    tool, created = Tool.objects.get_or_create(
        id=tool_id,
        defaults={
            'name': name,
            'description': description,
        },
    )

    changed = False
    if not tool.name:
        tool.name = name
        changed = True
    if not tool.description:
        tool.description = description
        changed = True
    if changed:
        tool.save()

    latest = ToolVersion.objects.filter(tool=tool).order_by('-version').first()
    next_version = 1 if latest is None else latest.version + 1
    version = ToolVersion.objects.create(
        tool=tool,
        version=next_version,
        code=code,
        entry_point=entry_point,
        schema=schema,
        message=message,
    )

    release, _ = ToolRelease.objects.get_or_create(tool=tool)
    release.prod_version = version
    release.test_version = version
    release.save()

    state = 'created' if created else 'updated'
    print(f'Preset Tool `{tool_id}` {state} with v{next_version}.')


def setup_preset_tools():
    # 工具 1：Double 计算器
    code1 = """def run(args):
    number = args.get('number', 0)
    return number * 2
"""
    create_or_update_preset_tool(
        tool_id='double',
        name='Double Number',
        description='Doubles the provided number',
        code=code1,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'number': {'type': 'number', 'description': 'The number to double'}
            },
            'required': ['number'],
        },
    )

    # 工具 2：Echo
    code2 = """def start(args):
    msg = args.get('message', '')
    print(f"Echoing: {msg}")
    return {'original': msg, 'length': len(msg)}
"""
    create_or_update_preset_tool(
        tool_id='echo',
        name='Echo Messages',
        description='Echo back the message',
        code=code2,
        entry_point='start',
        schema={
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'The message to echo'}
            },
            'required': ['message'],
        },
    )

    # 工具 3：Math 计算器
    code3 = """def run(args):
    import math

    op = args.get('op', 'sqrt')
    x = float(args.get('x', 0))
    y = float(args.get('y', 0))

    if op == 'sqrt':
        return {'op': op, 'result': math.sqrt(max(x, 0))}
    if op == 'pow':
        return {'op': op, 'result': math.pow(x, y)}
    if op == 'log':
        base = float(args.get('base', math.e))
        if x <= 0:
            return {'op': op, 'error': 'x must be > 0'}
        if base <= 0 or base == 1:
            return {'op': op, 'error': 'base must be > 0 and != 1'}
        return {'op': op, 'result': math.log(x, base)}
    if op == 'sin':
        return {'op': op, 'result': math.sin(x)}
    if op == 'cos':
        return {'op': op, 'result': math.cos(x)}

    return {'op': op, 'error': 'unsupported op'}
"""
    create_or_update_preset_tool(
        tool_id='math_calc',
        name='Math Calculator',
        description='Evaluate common math operations',
        code=code3,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'op': {
                    'type': 'string',
                    'enum': ['sqrt', 'pow', 'log', 'sin', 'cos'],
                    'description': 'Math operation',
                },
                'x': {'type': 'number', 'description': 'Primary value'},
                'y': {'type': 'number', 'description': 'Secondary value for pow'},
                'base': {'type': 'number', 'description': 'Base for log'},
            },
            'required': ['op', 'x'],
        },
    )

    # 工具 4：JSON 助手
    code4 = """def run(args):
    import json

    raw = args.get('text', '{}')
    mode = args.get('mode', 'pretty')

    try:
        obj = json.loads(raw)
    except Exception as e:
        return {'ok': False, 'error': str(e)}

    if mode == 'pretty':
        return {'ok': True, 'result': json.dumps(obj, ensure_ascii=False, indent=2)}
    if mode == 'minify':
        return {'ok': True, 'result': json.dumps(obj, ensure_ascii=False, separators=(',', ':'))}
    if mode == 'keys':
        if isinstance(obj, dict):
            return {'ok': True, 'keys': list(obj.keys())}
        return {'ok': True, 'keys': []}

    return {'ok': False, 'error': 'unsupported mode'}
"""
    create_or_update_preset_tool(
        tool_id='json_helper',
        name='JSON Helper',
        description='Parse, pretty-print, and inspect JSON',
        code=code4,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': 'JSON text'},
                'mode': {
                    'type': 'string',
                    'enum': ['pretty', 'minify', 'keys'],
                    'description': 'Output mode',
                },
            },
            'required': ['text'],
        },
    )

    # 工具 5：Time 工具
    code5 = """def run(args):
    import time

    action = args.get('action', 'now')
    fmt = args.get('format', '%Y-%m-%d %H:%M:%S')
    ts = args.get('timestamp')

    if action == 'now':
        return {'timestamp': time.time(), 'formatted': time.strftime(fmt, time.localtime())}
    if action == 'format':
        if ts is None:
            return {'error': 'timestamp is required'}
        return {'formatted': time.strftime(fmt, time.localtime(float(ts)))}
    if action == 'parse':
        text = args.get('text', '')
        if not text:
            return {'error': 'text is required'}
        return {'timestamp': time.mktime(time.strptime(text, fmt))}

    return {'error': 'unsupported action'}
"""
    create_or_update_preset_tool(
        tool_id='time_tools',
        name='Time Tools',
        description='Common time formatting and parsing utilities',
        code=code5,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'action': {
                    'type': 'string',
                    'enum': ['now', 'format', 'parse'],
                    'description': 'Time operation',
                },
                'timestamp': {'type': 'number', 'description': 'Unix timestamp'},
                'text': {'type': 'string', 'description': 'Time string for parse'},
                'format': {'type': 'string', 'description': 'strftime/strptime format'},
            },
            'required': ['action'],
        },
    )

    # 工具 6：Random 生成器
    code6 = """def run(args):
    import random

    mode = args.get('mode', 'randint')
    seed = args.get('seed')
    if seed is not None:
        random.seed(seed)

    if mode == 'randint':
        a = int(args.get('a', 0))
        b = int(args.get('b', 100))
        return {'result': random.randint(a, b)}

    if mode == 'choice':
        items = args.get('items', [])
        if not items:
            return {'error': 'items is empty'}
        return {'result': random.choice(items)}

    if mode == 'sample':
        items = args.get('items', [])
        k = int(args.get('k', 1))
        if not isinstance(items, list):
            return {'error': 'items must be a list'}
        return {'result': random.sample(items, max(0, min(k, len(items))))}

    return {'error': 'unsupported mode'}
"""
    create_or_update_preset_tool(
        tool_id='random_tools',
        name='Random Tools',
        description='Random sampling, choice, and number generation',
        code=code6,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'mode': {
                    'type': 'string',
                    'enum': ['randint', 'choice', 'sample'],
                    'description': 'Random mode',
                },
                'a': {'type': 'integer', 'description': 'Start for randint'},
                'b': {'type': 'integer', 'description': 'End for randint'},
                'items': {'type': 'array', 'description': 'Candidate items'},
                'k': {'type': 'integer', 'description': 'Sample size'},
                'seed': {'type': 'integer', 'description': 'Seed for reproducibility'},
            },
            'required': ['mode'],
        },
    )

    # 工具 7：Regex 助手
    code7 = """def run(args):
    import re

    mode = args.get('mode', 'findall')
    pattern = args.get('pattern', '')
    text = args.get('text', '')
    repl = args.get('repl', '')

    if not pattern:
        return {'error': 'pattern is required'}

    if mode == 'findall':
        return {'matches': re.findall(pattern, text)}
    if mode == 'search':
        matched = re.search(pattern, text)
        return {'matched': bool(matched), 'value': matched.group(0) if matched else None}
    if mode == 'sub':
        return {'result': re.sub(pattern, repl, text)}

    return {'error': 'unsupported mode'}
"""
    create_or_update_preset_tool(
        tool_id='regex_helper',
        name='Regex Helper',
        description='Regex find, search, and replace operations',
        code=code7,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'mode': {
                    'type': 'string',
                    'enum': ['findall', 'search', 'sub'],
                    'description': 'Regex mode',
                },
                'pattern': {'type': 'string', 'description': 'Regex pattern'},
                'text': {'type': 'string', 'description': 'Input text'},
                'repl': {'type': 'string', 'description': 'Replacement for sub'},
            },
            'required': ['mode', 'pattern', 'text'],
        },
    )

    # 工具 8：Collections 统计
    code8 = """def run(args):
    from collections import Counter

    text = args.get('text', '')
    top_k = int(args.get('top_k', 5))
    mode = args.get('mode', 'word')

    if mode == 'char':
        counter = Counter(text)
    else:
        counter = Counter([x for x in text.split() if x])

    return {
        'mode': mode,
        'total_unique': len(counter),
        'most_common': counter.most_common(max(1, top_k)),
    }
"""
    create_or_update_preset_tool(
        tool_id='collections_counter',
        name='Collections Counter',
        description='Use collections.Counter to count elements',
        code=code8,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': 'Input text'},
                'mode': {
                    'type': 'string',
                    'enum': ['word', 'char'],
                    'description': 'Count by words or chars',
                },
                'top_k': {'type': 'integer', 'description': 'How many top items to return'},
            },
            'required': ['text'],
        },
    )

    # 工具 9：Requests URL 助手（不发请求，只做构造）
    code9 = """def run(args):
    import requests

    method = str(args.get('method', 'GET')).upper()
    url = args.get('url', '')
    params = args.get('params', {}) or {}
    headers = args.get('headers', {}) or {}

    if not url:
        return {'error': 'url is required'}

    req = requests.Request(method=method, url=url, params=params, headers=headers)
    prepared = req.prepare()

    return {
        'method': method,
        'final_url': prepared.url,
        'headers': dict(prepared.headers),
    }
"""
    create_or_update_preset_tool(
        tool_id='requests_url_helper',
        name='Requests URL Helper',
        description='Build and inspect request URL and headers without sending',
        code=code9,
        entry_point='run',
        schema={
            'type': 'object',
            'properties': {
                'method': {'type': 'string', 'description': 'HTTP method, e.g. GET'},
                'url': {'type': 'string', 'description': 'Request URL'},
                'params': {'type': 'object', 'description': 'Query params object'},
                'headers': {'type': 'object', 'description': 'Request headers'},
            },
            'required': ['url'],
        },
    )


if __name__ == '__main__':
    setup_preset_tools()
