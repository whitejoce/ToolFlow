# Generated manually for safe schema migration to Event + Snapshot design.

import json
import re
import uuid
import django.db.models.deletion
from django.db import migrations, models


def _parse_version_tag(version_tag):
    if not version_tag:
        return None
    m = re.search(r"(\d+)", str(version_tag))
    if not m:
        return None
    return int(m.group(1))


def forwards_migrate_data(apps, schema_editor):
    Tool = apps.get_model('gateway', 'Tool')
    ToolVersion = apps.get_model('gateway', 'ToolVersion')
    ToolRelease = apps.get_model('gateway', 'ToolRelease')
    ExecutionTask = apps.get_model('gateway', 'ExecutionTask')
    Execution = apps.get_model('gateway', 'Execution')
    ExecutionLog = apps.get_model('gateway', 'ExecutionLog')

    # 1) ToolVersion: copy code/code schema and normalize numeric version.
    for tool in Tool.objects.all():
        versions = list(ToolVersion.objects.filter(tool=tool).order_by('created_at', 'id'))
        used_versions = set()
        for idx, tv in enumerate(versions, start=1):
            if not tv.code:
                tv.code = tv.code_blob or ""

            parsed = _parse_version_tag(getattr(tv, 'version_tag', None))
            candidate = parsed if parsed is not None else idx
            while candidate in used_versions:
                candidate += 1
            used_versions.add(candidate)
            tv.version = candidate

            if not tv.schema:
                schema = getattr(tool, 'input_schema', None)
                tv.schema = schema if schema else {"type": "object", "properties": {}}

            tv.save(update_fields=['code', 'version', 'schema'])

    # 2) ToolRelease: backfill release pointers from old active_version.
    for tool in Tool.objects.all():
        active = getattr(tool, 'active_version', None)
        if not active:
            active = ToolVersion.objects.filter(tool=tool).order_by('-version', '-created_at').first()
        release, _ = ToolRelease.objects.get_or_create(tool=tool)
        if active and not release.prod_version_id:
            release.prod_version_id = active.id
        if active and not release.test_version_id:
            release.test_version_id = active.id
        release.save()

    # 3) ExecutionTask -> Execution and logs.
    status_map = {
        'PENDING': 'pending',
        'RUNNING': 'running',
        'DONE': 'success',
        'FAILED': 'error',
    }

    for old in ExecutionTask.objects.all().order_by('created_at', 'id'):
        try:
            in_data = json.loads(old.arguments_json) if old.arguments_json else {}
        except Exception:
            in_data = {}

        try:
            out_data = json.loads(old.result_json) if old.result_json else {}
            if out_data is None:
                out_data = {}
        except Exception:
            out_data = {"raw": old.result_json}

        new_exec = Execution.objects.create(
            id=old.id,
            tool_id=old.tool_version.tool_id,
            version_id=old.tool_version_id,
            executor=old.executor_id,
            status=status_map.get(old.status, 'error'),
            input=in_data,
            output=out_data,
            error=old.error_msg,
            duration_ms=None,
            metadata={},
            created_at=old.created_at,
            updated_at=old.updated_at,
        )

        if old.logs:
            ExecutionLog.objects.create(
                id=uuid.uuid4(),
                execution_id=new_exec.id,
                level='error' if new_exec.status == 'error' else 'info',
                message='Migrated execution logs',
                data={'raw': old.logs},
                created_at=old.updated_at,
            )


def noop_reverse(apps, schema_editor):
    # Reverse migration intentionally omitted for this schema upgrade.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gateway', '0002_tool_input_schema'),
    ]

    operations = [
        migrations.CreateModel(
            name='Execution',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('tenant_id', models.CharField(blank=True, max_length=64, null=True)),
                ('executor', models.CharField(blank=True, max_length=64, null=True)),
                ('status', models.CharField(choices=[('pending', '待分配'), ('running', '执行中'), ('success', '成功完成'), ('error', '执行失败')], default='pending', max_length=16)),
                ('input', models.JSONField(blank=True, default=dict)),
                ('output', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True, null=True)),
                ('duration_ms', models.IntegerField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='ExecutionLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('level', models.CharField(choices=[('info', 'Info'), ('error', 'Error'), ('debug', 'Debug')], default='info', max_length=16)),
                ('message', models.TextField()),
                ('data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='ToolRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),

        migrations.AddField(
            model_name='tool',
            name='created_by',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name='tool',
            name='tenant_id',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='tool',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='tool',
            name='updated_by',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),

        migrations.AddField(
            model_name='toolversion',
            name='code',
            field=models.TextField(default='', help_text='Python executable source code'),
        ),
        migrations.AddField(
            model_name='toolversion',
            name='config',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='toolversion',
            name='message',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='toolversion',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='toolversion',
            name='schema',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='toolversion',
            name='status',
            field=models.CharField(default='draft', max_length=16),
        ),
        migrations.AddField(
            model_name='toolversion',
            name='version',
            field=models.PositiveIntegerField(default=1),
        ),

        migrations.AddField(
            model_name='execution',
            name='tool',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='gateway.tool'),
        ),
        migrations.AddField(
            model_name='execution',
            name='version',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='gateway.toolversion'),
        ),
        migrations.AddField(
            model_name='executionlog',
            name='execution',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='gateway.execution'),
        ),
        migrations.AddField(
            model_name='toolrelease',
            name='prod_version',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prod_release_tools', to='gateway.toolversion'),
        ),
        migrations.AddField(
            model_name='toolrelease',
            name='test_version',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='test_release_tools', to='gateway.toolversion'),
        ),
        migrations.AddField(
            model_name='toolrelease',
            name='tool',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='release', to='gateway.tool'),
        ),

        migrations.RunPython(forwards_migrate_data, reverse_code=noop_reverse),

        migrations.AlterField(
            model_name='tool',
            name='name',
            field=models.CharField(max_length=128, unique=True),
        ),
        migrations.AddConstraint(
            model_name='toolversion',
            constraint=models.UniqueConstraint(fields=('tool', 'version'), name='uniq_tool_version'),
        ),

        migrations.RemoveField(
            model_name='executiontask',
            name='tool_version',
        ),
        migrations.RemoveField(
            model_name='tool',
            name='active_version',
        ),
        migrations.RemoveField(
            model_name='tool',
            name='input_schema',
        ),
        migrations.RemoveField(
            model_name='toolversion',
            name='code_blob',
        ),
        migrations.RemoveField(
            model_name='toolversion',
            name='version_tag',
        ),
        migrations.DeleteModel(
            name='ExecutionTask',
        ),
    ]
