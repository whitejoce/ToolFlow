
import json
import time
from pathlib import Path
from datetime import timedelta
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncMinute
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Tool, ToolRelease, ToolVersion, Execution, ExecutionLog

DEFAULT_TIMEOUT = 10
POLL_INTERVAL = 0.5


def _runtime_config_path() -> Path:
    root_dir = Path(__file__).resolve().parents[2]
    return root_dir / 'runtime' / 'config.json'


def _default_runtime_config() -> dict:
    return {
        'mcp': {
            'django_port': 8000,
            'bridge_sse_port': 8001,
        },
        'server': {
            'url': 'http://127.0.0.1:8000',
            'poll_interval': 2.0,
        },
        'worker': {
            'pools': [
                {'env': 'prod', 'prefix': 'node-prod', 'count': 2},
                {'env': 'test', 'prefix': 'node-test', 'count': 1},
            ],
        },
        'tool_version': {
            'active_conflict_policy': 'deprecated',
            'require_test_success_before_release': False,
        },
        'sandbox': {
            'execution_timeout': 10,
            'allowed_modules': ['math', 'json', 'time', 'random', 're', 'collections', 'requests'],
        },
    }


def _load_runtime_config() -> dict:
    path = _runtime_config_path()
    if not path.exists():
        cfg = _default_runtime_config()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding='utf-8')
        return cfg

    with path.open('r', encoding='utf-8') as f:
        cfg = json.load(f)

    if not isinstance(cfg, dict):
        return _default_runtime_config()
    return cfg


def _save_runtime_config(cfg: dict) -> None:
    path = _runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding='utf-8')


def _active_conflict_policy() -> str:
    cfg = _load_runtime_config()
    policy = (((cfg.get('tool_version') or {}).get('active_conflict_policy')) or 'deprecated').lower()
    return policy if policy in ['deprecated', 'draft'] else 'deprecated'


def _require_test_success_before_release() -> bool:
    cfg = _load_runtime_config()
    return bool(((cfg.get('tool_version') or {}).get('require_test_success_before_release')))

@csrf_exempt
def api_journey(request):
    if request.method != 'POST':
        return JsonResponse({'error': {'code': -32600, 'message': 'Method not allowed'}}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'jsonrpc': '2.0', 'error': {'code': -32700, 'message': 'Parse error'}, 'id': None})
    
    method = data.get('method')
    req_id = data.get('id')
    
    resp = {'jsonrpc': '2.0'}
    if req_id is not None:
        resp['id'] = req_id
        
    if method == 'initialize':
        resp['result'] = {
            'protocolVersion': '2024-11-05',
            'capabilities': {
                'tools': {'listChanged': True}
            },
            'serverInfo': {
                'name': 'ToolFlow MCP Server',
                'version': '1.0.0'
            }
        }
        return JsonResponse(resp)
        
    elif method == 'notifications/initialized':
        return JsonResponse({})

    elif method == 'ping':
        resp['result'] = {}
        return JsonResponse(resp)
        
    elif method == 'tools/list':
        tools = Tool.objects.all()
        tools_list = []
        for t in tools:
            release = getattr(t, 'release', None)
            active_version = None
            if release and release.prod_version:
                active_version = release.prod_version
            elif release and release.test_version:
                active_version = release.test_version

            if not active_version:
                continue

            schema = active_version.schema if active_version.schema else {'type': 'object', 'properties': {}}
            tools_list.append({
                'name': t.id,
                'description': t.description,
                'inputSchema': schema
            })
        resp['result'] = {'tools': tools_list}
        return JsonResponse(resp)
        
    elif method == 'tools/call':
        params = data.get('params', {})
        tool_name = params.get('name')
        args = params.get('arguments', {})
        
        try:
            tool = Tool.objects.get(id=tool_name)
            release = getattr(tool, 'release', None)
            selected_version = None
            if release and release.prod_version:
                selected_version = release.prod_version
            elif release and release.test_version:
                selected_version = release.test_version

            if not selected_version:
                resp['error'] = {'code': -32602, 'message': f'No active version'}
                return JsonResponse(resp)

            task = Execution.objects.create(
                tool=tool,
                version=selected_version,
                input=args,
                status='pending',
                metadata={'target_env': 'prod'}
            )
            
            start_time = time.time()
            done = False
            while time.time() - start_time < DEFAULT_TIMEOUT:
                task.refresh_from_db()
                if task.status in ['success', 'error']:
                    done = True
                    break
                time.sleep(POLL_INTERVAL)
            
            if not done:
                resp['error'] = {'code': -32000, 'message': 'Task execution timed out'}
                return JsonResponse(resp)
            
            is_error = (task.status == 'error')
            
            content_list = []
            if is_error:
                content_list.append({'type': 'text', 'text': task.error or 'Unknown error'})
            else:
                try:
                    res_obj = task.output if isinstance(task.output, dict) else {}
                    content_text = json.dumps(res_obj, ensure_ascii=False)
                except:
                    content_text = str(task.output)
                content_list.append({'type': 'text', 'text': str(content_text)})

            all_logs = list(task.logs.order_by('created_at').values_list('message', flat=True))
            if all_logs:
                content_list.append({'type': 'text', 'text': '\n[Logs]:\n' + '\n'.join(all_logs)})
                
            resp['result'] = {
                'content': content_list,
                'isError': is_error
            }
            return JsonResponse(resp)
            
        except Tool.DoesNotExist:
            resp['error'] = {'code': -32601, 'message': 'Tool not found'}
            return JsonResponse(resp)
            
    resp['error'] = {'code': -32601, 'message': 'Method not found'}
    return JsonResponse(resp)

@csrf_exempt
def pop_task(request):
    if request.method == 'POST':
        data = json.loads(request.body) if request.body else {}
        executor_id = data.get('executor_id', 'unknown')
        executor_env = data.get('executor_env', 'prod')

        # Concurrency-safe claim: update only if current status is still pending.
        # This prevents the same execution from being taken by multiple workers.
        task = None
        candidates = Execution.objects.filter(status='pending').order_by('created_at')[:100]
        for candidate in candidates:
            target_env = (candidate.metadata or {}).get('target_env', 'prod')
            if target_env != executor_env:
                continue

            with transaction.atomic():
                claimed = Execution.objects.filter(
                    id=candidate.id,
                    status='pending'
                ).update(status='running', executor=executor_id)

            if claimed == 1:
                task = Execution.objects.select_related('version').get(id=candidate.id)
                break

        if not task:
            return JsonResponse({'task': None})

        return JsonResponse({
            'task_id': str(task.id),
            'code': task.version.code,
            'entry': task.version.entry_point,
            'args': task.input or {}
        })
    return JsonResponse({}, status=405)

@csrf_exempt
def report_task(request, task_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            task = Execution.objects.get(id=task_id)
            incoming_status = data.get('status', 'DONE')
            mapped = {
                'PENDING': 'pending',
                'RUNNING': 'running',
                'DONE': 'success',
                'FAILED': 'error',
                'pending': 'pending',
                'running': 'running',
                'success': 'success',
                'error': 'error',
            }
            task.status = mapped.get(incoming_status, 'error')
            if 'result' in data:
                task.output = data['result']
            if 'error' in data:
                task.error = data['error']

            if task.status in ['success', 'error']:
                task.duration_ms = int((timezone.now() - task.created_at).total_seconds() * 1000)

            task.save()

            if 'logs' in data and data['logs']:
                ExecutionLog.objects.create(
                    execution=task,
                    level='error' if task.status == 'error' else 'info',
                    message='Executor runtime logs',
                    data={'raw': data['logs']},
                )

            return JsonResponse({'success': True})
        except Execution.DoesNotExist:
            return JsonResponse({'error': 'Task not found'}, status=404)
    return JsonResponse({}, status=405)


def _parse_json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body)


def _serialize_version(version):
    return {
        'id': str(version.id),
        'version': version.version,
        'code': version.code,
        'entry_point': version.entry_point,
        'status': version.status,
        'message': version.message,
        'schema': version.schema,
        'config': version.config,
        'created_at': version.created_at.isoformat(),
    }


@csrf_exempt
def admin_runtime_config(request):
    if request.method == 'GET':
        cfg = _load_runtime_config()
        return JsonResponse({'config': cfg})

    if request.method == 'PUT':
        try:
            data = _parse_json_body(request)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({'error': 'config body must be object'}, status=400)

        policy = (((data.get('tool_version') or {}).get('active_conflict_policy')) or 'deprecated').lower()
        if policy not in ['deprecated', 'draft']:
            return JsonResponse({'error': 'active_conflict_policy must be deprecated or draft'}, status=400)

        guard = ((data.get('tool_version') or {}).get('require_test_success_before_release'))
        if not isinstance(guard, bool):
            return JsonResponse({'error': 'require_test_success_before_release must be boolean'}, status=400)

        _save_runtime_config(data)
        return JsonResponse({'config': data})

    return JsonResponse({}, status=405)


@csrf_exempt
def admin_tools(request):
    if request.method == 'GET':
        rows = []
        for tool in Tool.objects.all().order_by('id'):
            release = getattr(tool, 'release', None)
            rows.append({
                'id': tool.id,
                'name': tool.name,
                'description': tool.description,
                'created_at': tool.created_at.isoformat(),
                'prod_version': release.prod_version.version if release and release.prod_version else None,
                'test_version': release.test_version.version if release and release.test_version else None,
            })
        return JsonResponse({'items': rows})

    if request.method == 'POST':
        try:
            data = _parse_json_body(request)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        tool_id = data.get('id')
        name = data.get('name')
        description = data.get('description', '')
        if not tool_id or not name:
            return JsonResponse({'error': 'id and name are required'}, status=400)

        if Tool.objects.filter(id=tool_id).exists():
            return JsonResponse({'error': 'tool already exists'}, status=409)

        tool = Tool.objects.create(
            id=tool_id,
            name=name,
            description=description,
            created_by=data.get('operator', 'system'),
            updated_by=data.get('operator', 'system'),
        )
        ToolRelease.objects.get_or_create(tool=tool)
        return JsonResponse({'id': tool.id, 'name': tool.name}, status=201)

    return JsonResponse({}, status=405)


@csrf_exempt
def admin_tool_detail(request, tool_id):
    try:
        tool = Tool.objects.get(id=tool_id)
    except Tool.DoesNotExist:
        return JsonResponse({'error': 'tool not found'}, status=404)

    if request.method == 'GET':
        release = getattr(tool, 'release', None)
        return JsonResponse({
            'id': tool.id,
            'name': tool.name,
            'description': tool.description,
            'created_at': tool.created_at.isoformat(),
            'prod_version': release.prod_version.version if release and release.prod_version else None,
            'test_version': release.test_version.version if release and release.test_version else None,
        })

    if request.method == 'PATCH':
        try:
            data = _parse_json_body(request)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        new_name = data.get('name')
        new_description = data.get('description')

        if new_name is not None:
            if not isinstance(new_name, str) or not new_name.strip():
                return JsonResponse({'error': 'name must be non-empty string'}, status=400)
            if Tool.objects.exclude(id=tool.id).filter(name=new_name).exists():
                return JsonResponse({'error': 'name already exists'}, status=409)
            tool.name = new_name.strip()

        if new_description is not None:
            if not isinstance(new_description, str):
                return JsonResponse({'error': 'description must be string'}, status=400)
            tool.description = new_description

        tool.updated_by = data.get('operator', tool.updated_by)
        tool.save(update_fields=['name', 'description', 'updated_by', 'updated_at'])

        return JsonResponse({'id': tool.id, 'name': tool.name, 'description': tool.description})

    return JsonResponse({}, status=405)


@csrf_exempt
def admin_tool_versions(request, tool_id):
    try:
        tool = Tool.objects.get(id=tool_id)
    except Tool.DoesNotExist:
        return JsonResponse({'error': 'tool not found'}, status=404)

    if request.method == 'GET':
        versions = ToolVersion.objects.filter(tool=tool).order_by('-version', '-created_at')
        return JsonResponse({'items': [_serialize_version(v) for v in versions]})

    if request.method == 'POST':
        try:
            data = _parse_json_body(request)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        code = data.get('code')
        entry_point = data.get('entry_point', 'main')
        new_status = data.get('status', 'draft')
        if not code:
            return JsonResponse({'error': 'code is required'}, status=400)

        with transaction.atomic():
            latest = ToolVersion.objects.select_for_update().filter(tool=tool).order_by('-version').first()
            next_version = 1 if latest is None else latest.version + 1

            if new_status == 'active':
                demote_to = _active_conflict_policy()
                ToolVersion.objects.select_for_update().filter(tool=tool, status='active').update(status=demote_to)

            version = ToolVersion.objects.create(
                tool=tool,
                version=next_version,
                code=code,
                entry_point=entry_point,
                config=data.get('config', {}),
                schema=data.get('schema', {'type': 'object', 'properties': {}}),
                message=data.get('message', ''),
                status=new_status,
                metadata=data.get('metadata', {}),
            )
        return JsonResponse(_serialize_version(version), status=201)

    return JsonResponse({}, status=405)


@csrf_exempt
def admin_tool_release(request, tool_id):
    if request.method != 'POST':
        return JsonResponse({}, status=405)

    try:
        tool = Tool.objects.get(id=tool_id)
        data = _parse_json_body(request)
    except Tool.DoesNotExist:
        return JsonResponse({'error': 'tool not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    env = data.get('environment', 'prod')
    version_num = data.get('version')
    if env not in ['prod', 'test']:
        return JsonResponse({'error': 'environment must be prod or test'}, status=400)
    if not isinstance(version_num, int):
        return JsonResponse({'error': 'version must be int'}, status=400)

    try:
        version = ToolVersion.objects.get(tool=tool, version=version_num)
    except ToolVersion.DoesNotExist:
        return JsonResponse({'error': 'version not found'}, status=404)

    if env == 'prod' and _require_test_success_before_release():
        has_test_success = Execution.objects.filter(
            tool=tool,
            version=version,
            status='success',
            metadata__trigger='admin_test_run',
        ).exists()
        if not has_test_success:
            return JsonResponse(
                {'error': 'release blocked: run-test must succeed before publishing to prod'},
                status=409,
            )

    with transaction.atomic():
        release, _ = ToolRelease.objects.select_for_update().get_or_create(tool=tool)

        if env == 'prod':
            demote_to = _active_conflict_policy()
            ToolVersion.objects.select_for_update().filter(tool=tool, status='active').exclude(id=version.id).update(status=demote_to)
            if version.status != 'active':
                version.status = 'active'
                version.save(update_fields=['status'])
            release.prod_version = version
        else:
            release.test_version = version

        release.save()

    return JsonResponse({
        'tool_id': tool.id,
        'environment': env,
        'version': version.version,
        'updated_at': release.updated_at.isoformat(),
    })


@csrf_exempt
def admin_tool_version_status(request, tool_id, version_num):
    if request.method != 'PATCH':
        return JsonResponse({}, status=405)

    try:
        tool = Tool.objects.get(id=tool_id)
        version = ToolVersion.objects.get(tool=tool, version=version_num)
        data = _parse_json_body(request)
    except Tool.DoesNotExist:
        return JsonResponse({'error': 'tool not found'}, status=404)
    except ToolVersion.DoesNotExist:
        return JsonResponse({'error': 'version not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    new_status = str(data.get('status', '')).strip().lower()
    if new_status not in ['draft', 'active', 'deprecated']:
        return JsonResponse({'error': 'status must be draft, active, or deprecated'}, status=400)

    with transaction.atomic():
        if new_status == 'active':
            demote_to = _active_conflict_policy()
            ToolVersion.objects.select_for_update().filter(tool=tool, status='active').exclude(id=version.id).update(status=demote_to)

        version.status = new_status
        version.save(update_fields=['status'])

    return JsonResponse(_serialize_version(version))


@csrf_exempt
def admin_tool_rollback(request, tool_id):
    if request.method != 'POST':
        return JsonResponse({}, status=405)

    try:
        tool = Tool.objects.get(id=tool_id)
        data = _parse_json_body(request)
    except Tool.DoesNotExist:
        return JsonResponse({'error': 'tool not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    env = data.get('environment', 'prod')
    to_version = data.get('to_version')
    if env not in ['prod', 'test']:
        return JsonResponse({'error': 'environment must be prod or test'}, status=400)
    if not isinstance(to_version, int):
        return JsonResponse({'error': 'to_version must be int'}, status=400)

    try:
        target = ToolVersion.objects.get(tool=tool, version=to_version)
    except ToolVersion.DoesNotExist:
        return JsonResponse({'error': 'target version not found'}, status=404)

    release, _ = ToolRelease.objects.get_or_create(tool=tool)
    if env == 'prod':
        release.prod_version = target
    else:
        release.test_version = target
    release.save()

    return JsonResponse({
        'tool_id': tool.id,
        'rolled_back_environment': env,
        'current_version': target.version,
        'updated_at': release.updated_at.isoformat(),
    })


@csrf_exempt
def admin_tool_run_test(request, tool_id):
    if request.method != 'POST':
        return JsonResponse({}, status=405)

    try:
        tool = Tool.objects.get(id=tool_id)
        data = _parse_json_body(request)
    except Tool.DoesNotExist:
        return JsonResponse({'error': 'tool not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    args = data.get('arguments', {})
    if not isinstance(args, dict):
        return JsonResponse({'error': 'arguments must be object'}, status=400)

    specified_version = data.get('version')
    selected_version = None

    if specified_version is not None:
        if not isinstance(specified_version, int):
            return JsonResponse({'error': 'version must be int'}, status=400)
        try:
            selected_version = ToolVersion.objects.get(tool=tool, version=specified_version)
        except ToolVersion.DoesNotExist:
            return JsonResponse({'error': 'version not found'}, status=404)
    else:
        release = getattr(tool, 'release', None)
        if release and release.test_version:
            selected_version = release.test_version
        else:
            selected_version = ToolVersion.objects.filter(tool=tool).order_by('-version', '-created_at').first()

    if not selected_version:
        return JsonResponse({'error': 'no version available for test run'}, status=400)

    task = Execution.objects.create(
        tool=tool,
        version=selected_version,
        input=args,
        status='pending',
        metadata={
            'target_env': 'test',
            'trigger': 'admin_test_run',
        },
    )

    return JsonResponse({
        'execution_id': str(task.id),
        'tool_id': tool.id,
        'version': selected_version.version,
        'status': task.status,
        'target_env': 'test',
        'created_at': task.created_at.isoformat(),
    }, status=201)


@csrf_exempt
def admin_executions(request):
    if request.method != 'GET':
        return JsonResponse({}, status=405)

    status = request.GET.get('status')
    tool_id = request.GET.get('tool_id')
    executor = request.GET.get('executor')
    target_env = request.GET.get('target_env')
    page = int(request.GET.get('page', 1))
    page_size = min(int(request.GET.get('page_size', 20)), 200)

    qs = Execution.objects.select_related('tool', 'version').order_by('-created_at')
    if status:
        qs = qs.filter(status=status)
    if tool_id:
        qs = qs.filter(tool_id=tool_id)
    if executor:
        qs = qs.filter(executor=executor)
    if target_env in ['prod', 'test']:
        qs = qs.filter(metadata__target_env=target_env)

    total = qs.count()
    start = (page - 1) * page_size
    rows = qs[start:start + page_size]

    items = []
    for r in rows:
        items.append({
            'id': str(r.id),
            'tool_id': r.tool_id,
            'version': r.version.version,
            'executor': r.executor,
            'status': r.status,
            'target_env': (r.metadata or {}).get('target_env'),
            'duration_ms': r.duration_ms,
            'created_at': r.created_at.isoformat(),
            'updated_at': r.updated_at.isoformat(),
        })

    return JsonResponse({
        'items': items,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total,
        }
    })


@csrf_exempt
def admin_execution_detail(request, execution_id):
    if request.method != 'GET':
        return JsonResponse({}, status=405)

    try:
        e = Execution.objects.select_related('tool', 'version').get(id=execution_id)
    except Execution.DoesNotExist:
        return JsonResponse({'error': 'execution not found'}, status=404)

    log_rows = []
    for l in e.logs.order_by('created_at'):
        log_rows.append({
            'id': str(l.id),
            'level': l.level,
            'message': l.message,
            'data': l.data,
            'created_at': l.created_at.isoformat(),
        })

    return JsonResponse({
        'id': str(e.id),
        'tool_id': e.tool_id,
        'version': e.version.version,
        'executor': e.executor,
        'status': e.status,
        'target_env': (e.metadata or {}).get('target_env'),
        'input': e.input,
        'output': e.output,
        'error': e.error,
        'duration_ms': e.duration_ms,
        'created_at': e.created_at.isoformat(),
        'updated_at': e.updated_at.isoformat(),
        'logs': log_rows,
    })


@csrf_exempt
def admin_metrics_overview(request):
    if request.method != 'GET':
        return JsonResponse({}, status=405)

    now = timezone.now()
    since = now - timedelta(hours=24)
    qs = Execution.objects.filter(created_at__gte=since)

    total = qs.count()
    success = qs.filter(status='success').count()
    failed = qs.filter(status='error').count()
    running = Execution.objects.filter(status='running').count()
    pending = Execution.objects.filter(status='pending').count()
    avg_duration = qs.filter(duration_ms__isnull=False).aggregate(v=Avg('duration_ms'))['v']

    return JsonResponse({
        'window': {
            'from': since.isoformat(),
            'to': now.isoformat(),
        },
        'counters': {
            'total_24h': total,
            'success_24h': success,
            'failed_24h': failed,
            'running_now': running,
            'pending_now': pending,
            'success_rate_24h': 0 if total == 0 else round((success / total) * 100, 2),
            'avg_duration_ms_24h': 0 if avg_duration is None else round(avg_duration, 2),
        }
    })


@csrf_exempt
def admin_metrics_timeseries(request):
    if request.method != 'GET':
        return JsonResponse({}, status=405)

    now = timezone.now()
    window_minutes = int(request.GET.get('window_minutes', 180))
    window_minutes = max(5, min(window_minutes, 7 * 24 * 60))
    since = now - timedelta(minutes=window_minutes)

    qs = (
        Execution.objects.filter(created_at__gte=since)
        .annotate(bucket=TruncMinute('created_at'))
        .values('bucket')
        .annotate(
            total=Count('id'),
            success=Count('id', filter=Q(status='success')),
            error=Count('id', filter=Q(status='error')),
            running=Count('id', filter=Q(status='running')),
            avg_duration_ms=Avg('duration_ms'),
        )
        .order_by('bucket')
    )

    rows = []
    for r in qs:
        rows.append({
            'ts': r['bucket'].isoformat() if r['bucket'] else None,
            'total': r['total'],
            'success': r['success'],
            'error': r['error'],
            'running': r['running'],
            'avg_duration_ms': 0 if r['avg_duration_ms'] is None else round(r['avg_duration_ms'], 2),
        })

    return JsonResponse({
        'window': {
            'from': since.isoformat(),
            'to': now.isoformat(),
            'bucket': 'minute',
        },
        'points': rows,
    })

