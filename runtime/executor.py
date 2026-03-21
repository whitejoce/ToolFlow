import json
import traceback
import io
import time
import requests
import threading
import builtins
from contextlib import redirect_stdout, redirect_stderr

with open('config.json', 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

# 如果 config.json 配置了 mcp.django_port，则覆盖 server url 以保持同一核心
django_port = CONFIG.get('mcp', {}).get('django_port')
if django_port:
    SERVER_URL = f"http://127.0.0.1:{django_port}"
else:
    SERVER_URL = CONFIG['server']['url']

POLL_INTERVAL = CONFIG['server']['poll_interval']
ALLOWED_MODULES = set(CONFIG['sandbox']['allowed_modules'])

class ExecResult:
    def __init__(self, data, logs):
        self.data = data
        self.logs = logs

class SafeExecError(Exception):
    def __init__(self, cause, logs):
        super().__init__(f'Execution failed: {cause}')
        self.logs = logs

def get_safe_builtins():
    original_import = builtins.__import__
    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        base_module = name.split('.')[0]
        if base_module not in ALLOWED_MODULES:
            raise ImportError(f'Security Sandbox Denied: Module {name} is not in the whitelist.')
        return original_import(name, globals, locals, fromlist, level)
    
    safe_dict = builtins.__dict__.copy()
    safe_dict['__import__'] = safe_import
    safe_dict['open'] = None
    return safe_dict

def run_ephemeral(code_str: str, entry: str, args: dict, limits: dict = None) -> ExecResult:
    namespace = {'__builtins__': get_safe_builtins()}
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    
    func_name = entry.split(':')[-1] if ':' in entry else entry
    
    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        try:
            exec(code_str, namespace)
            if func_name not in namespace:
                raise ValueError(f'Entry point not found.')
            func = namespace[func_name]
            result = func(args)
        except Exception as e:
            logs = stdout_buf.getvalue() + stderr_buf.getvalue() + '\n' + traceback.format_exc()
            raise SafeExecError(str(e), logs)
            
    logs = stdout_buf.getvalue() + stderr_buf.getvalue()
    return ExecResult(data=result, logs=logs)

class Task:
    def __init__(self, task_id, code, entry, args):
        self.id = task_id
        self.code = code
        self.entry = entry
        self.args = args

def run_worker(worker_id, worker_env='prod'):
    print(f'Starting Worker {worker_id} [{worker_env}], polling {SERVER_URL} ...')
    while True:
        try:
            resp = requests.post(
                f'{SERVER_URL}/api/tasks/pop',
                json={'executor_id': worker_id, 'executor_env': worker_env}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get('task_id'):
                    task = Task(data['task_id'], data['code'], data['entry'], data['args'])
                    print(f'[{task.id}] Working on {worker_id}...')
                    try:
                        res = run_ephemeral(task.code, task.entry, task.args)
                        requests.post(f'{SERVER_URL}/api/tasks/{task.id}/report', json={'status': 'DONE', 'result': res.data, 'logs': res.logs})
                    except SafeExecError as e:
                        requests.post(f'{SERVER_URL}/api/tasks/{task.id}/report', json={'status': 'FAILED', 'error': str(e), 'logs': e.logs})
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

def executor_main():
    worker_cfg = CONFIG.get('worker', {})
    pools = worker_cfg.get('pools')

    # Backward compatibility for old config format
    if not pools:
        pools = [{
            'env': worker_cfg.get('env', 'prod'),
            'prefix': worker_cfg.get('prefix', 'node-alpha'),
            'count': worker_cfg.get('count', 3),
        }]

    threads = []
    for pool in pools:
        env = pool.get('env', 'prod')
        prefix = pool.get('prefix', f'node-{env}')
        count = int(pool.get('count', 0))
        for i in range(count):
            worker_id = f'{prefix}-{i+1}'
            t = threading.Thread(target=run_worker, args=(worker_id, env))
            t.daemon = True
            t.start()
            threads.append(t)
    
    while True:
        time.sleep(1)

if __name__ == '__main__':
    executor_main()
