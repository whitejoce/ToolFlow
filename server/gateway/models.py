from django.db import models
from django.db.models import Q
import uuid


class Tool(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    tenant_id = models.CharField(max_length=64, blank=True, null=True)
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField()
    created_by = models.CharField(max_length=128, blank=True, null=True)
    updated_by = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.id

class ToolVersion(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name='versions')
    version = models.PositiveIntegerField(default=1)
    code = models.TextField(default="", help_text="Python executable source code")
    entry_point = models.CharField(max_length=64, default="main", help_text="入口函数")
    config = models.JSONField(default=dict, blank=True)
    schema = models.JSONField(default=dict, blank=True)
    message = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, default="draft")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tool', 'version'], name='uniq_tool_version'),
            models.UniqueConstraint(
                fields=['tool'],
                condition=Q(status='active'),
                name='uniq_active_version_per_tool',
            ),
        ]


class ToolRelease(models.Model):
    tool = models.OneToOneField(Tool, on_delete=models.CASCADE, related_name='release')
    prod_version = models.ForeignKey(
        ToolVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prod_release_tools',
    )
    test_version = models.ForeignKey(
        ToolVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='test_release_tools',
    )
    updated_at = models.DateTimeField(auto_now=True)


class Execution(models.Model):
    STATUS_CHOICES = (
        ('pending', '待分配'),
        ('running', '执行中'),
        ('success', '成功完成'),
        ('error', '执行失败'),
    )

    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    tenant_id = models.CharField(max_length=64, blank=True, null=True)
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name='executions')
    version = models.ForeignKey(ToolVersion, on_delete=models.CASCADE, related_name='executions')
    executor = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(default=dict, blank=True)
    error = models.TextField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ExecutionLog(models.Model):
    LEVEL_CHOICES = (
        ('info', 'Info'),
        ('error', 'Error'),
        ('debug', 'Debug'),
    )

    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default='info')
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
