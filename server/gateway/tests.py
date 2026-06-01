import json

from django.test import TestCase

from .models import Tool, ToolRelease, ToolVersion

# Test1 ：当工具的发布版本不是active状态，就不会出现在列表中
class McpToolListTests(TestCase):
    def test_tools_list_omits_tool_when_released_version_is_not_active(self):
        tool = Tool.objects.create(
            id='echo',
            name='Echo',
            description='Echo tool',
        )
        version = ToolVersion.objects.create(
            tool=tool,
            version=1,
            code='def run(args): return args',
            entry_point='run',
            schema={'type': 'object', 'properties': {}},
            status='active',
        )
        ToolRelease.objects.create(tool=tool, prod_version=version)

        resp = self.client.post(
            '/mcp/',
            data=json.dumps({
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/list',
                'params': {},
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['result']['tools'][0]['name'], 'echo')

        version.status = 'deprecated'
        version.save(update_fields=['status'])

        resp = self.client.post(
            '/mcp/',
            data=json.dumps({
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'tools/list',
                'params': {},
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['result']['tools'], [])
