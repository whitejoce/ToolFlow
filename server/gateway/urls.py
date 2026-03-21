from django.urls import path
from . import views

urlpatterns = [
    path('mcp/', views.api_journey, name='mcp_journey'),
    path('api/tasks/pop', views.pop_task, name='pop_task'),
    path('api/tasks/<uuid:task_id>/report', views.report_task, name='report_task'),

    # Admin APIs for frontend
    path('api/admin/tools', views.admin_tools, name='admin_tools'),
    path('api/admin/tools/<str:tool_id>', views.admin_tool_detail, name='admin_tool_detail'),
    path('api/admin/tools/<str:tool_id>/versions', views.admin_tool_versions, name='admin_tool_versions'),
    path('api/admin/tools/<str:tool_id>/versions/<int:version_num>/status', views.admin_tool_version_status, name='admin_tool_version_status'),
    path('api/admin/tools/<str:tool_id>/release', views.admin_tool_release, name='admin_tool_release'),
    path('api/admin/tools/<str:tool_id>/rollback', views.admin_tool_rollback, name='admin_tool_rollback'),
    path('api/admin/tools/<str:tool_id>/run-test', views.admin_tool_run_test, name='admin_tool_run_test'),

    path('api/admin/executions', views.admin_executions, name='admin_executions'),
    path('api/admin/executions/<uuid:execution_id>', views.admin_execution_detail, name='admin_execution_detail'),

    path('api/admin/metrics/overview', views.admin_metrics_overview, name='admin_metrics_overview'),
    path('api/admin/metrics/timeseries', views.admin_metrics_timeseries, name='admin_metrics_timeseries'),
    path('api/admin/config', views.admin_runtime_config, name='admin_runtime_config'),
]
