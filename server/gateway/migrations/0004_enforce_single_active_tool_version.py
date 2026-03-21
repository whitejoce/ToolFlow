from django.db import migrations, models
from django.db.models import Q


def dedupe_active_versions(apps, schema_editor):
    ToolVersion = apps.get_model('gateway', 'ToolVersion')

    tool_ids = ToolVersion.objects.values_list('tool_id', flat=True).distinct()
    for tool_id in tool_ids:
        active_versions = list(
            ToolVersion.objects.filter(tool_id=tool_id, status='active').order_by('-version', '-created_at')
        )
        if len(active_versions) <= 1:
            continue

        for stale in active_versions[1:]:
            stale.status = 'draft'
            stale.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('gateway', '0003_execution_executionlog_toolrelease_and_more'),
    ]

    operations = [
        migrations.RunPython(dedupe_active_versions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='toolversion',
            constraint=models.UniqueConstraint(
                fields=('tool',),
                condition=Q(status='active'),
                name='uniq_active_version_per_tool',
            ),
        ),
    ]
