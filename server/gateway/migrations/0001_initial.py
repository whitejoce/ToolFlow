# Generated manually after squashing gateway migrations.

import uuid
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Tool',
            fields=[
                ('id', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('tenant_id', models.CharField(blank=True, max_length=64, null=True)),
                ('name', models.CharField(max_length=128, unique=True)),
                ('description', models.TextField()),
                ('created_by', models.CharField(blank=True, max_length=128, null=True)),
                ('updated_by', models.CharField(blank=True, max_length=128, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='ToolVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('code', models.TextField(default='', help_text='Python executable source code')),
                ('entry_point', models.CharField(default='main', help_text='入口函数', max_length=64)),
                ('config', models.JSONField(blank=True, default=dict)),
                ('schema', models.JSONField(blank=True, default=dict)),
                ('message', models.CharField(blank=True, default='', max_length=255)),
                ('status', models.CharField(default='draft', max_length=16)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tool', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='gateway.tool')),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(fields=('tool', 'version'), name='uniq_tool_version'),
                    models.UniqueConstraint(condition=Q(status='active'), fields=('tool',), name='uniq_active_version_per_tool'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ToolRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('prod_version', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prod_release_tools', to='gateway.toolversion')),
                ('test_version', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='test_release_tools', to='gateway.toolversion')),
                ('tool', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='release', to='gateway.tool')),
            ],
        ),
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
                ('tool', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='gateway.tool')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='gateway.toolversion')),
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
                ('execution', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='gateway.execution')),
            ],
        ),
    ]
