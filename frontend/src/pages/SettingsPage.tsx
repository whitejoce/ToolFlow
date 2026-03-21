import { useMutation, useQuery } from '@tanstack/react-query'
import { Button, Card, Col, Form, Input, InputNumber, Row, Select, Space, Switch, message } from 'antd'
import { getRuntimeConfig, updateRuntimeConfig } from '../api/admin'
import { useEffect } from 'react'
import type { RuntimeConfig } from '../types/api'

export default function SettingsPage() {
  const [form] = Form.useForm()
  const [apiMessage, contextHolder] = message.useMessage()

  const configQuery = useQuery({
    queryKey: ['runtimeConfig'],
    queryFn: getRuntimeConfig,
  })

  useEffect(() => {
    const cfg = configQuery.data?.config
    if (!cfg) return
    form.setFieldsValue({
      djangoPort: cfg.mcp.django_port,
      ssePort: cfg.mcp.bridge_sse_port,
      serverUrl: cfg.server.url,
      pollInterval: cfg.server.poll_interval,
      executionTimeout: cfg.sandbox.execution_timeout,
      allowedModulesText: cfg.sandbox.allowed_modules.join(', '),
      poolsText: JSON.stringify(cfg.worker.pools, null, 2),
      activeConflictPolicy: cfg.tool_version.active_conflict_policy,
      requireTestSuccessBeforeRelease: cfg.tool_version.require_test_success_before_release ?? false,
    })
  }, [configQuery.data, form])

  const saveMutation = useMutation({
    mutationFn: updateRuntimeConfig,
    onSuccess: () => apiMessage.success('Configuration saved to runtime/config.json. Please restart gateway service.'),
    onError: (error: Error) => apiMessage.error(error.message || 'Failed to save configuration'),
  })

  function parsePools(raw: string) {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      throw new Error('worker pools must be an array')
    }
    for (const item of parsed) {
      if (!item || typeof item !== 'object') throw new Error('each pool item must be an object')
      if (!['prod', 'test'].includes(String((item as Record<string, unknown>).env || ''))) {
        throw new Error('pool.env must be prod or test')
      }
    }
    return parsed as RuntimeConfig['worker']['pools']
  }

  function submit(values: {
    djangoPort: number
    ssePort: number
    serverUrl: string
    pollInterval: number
    executionTimeout: number
    allowedModulesText: string
    poolsText: string
    activeConflictPolicy: 'deprecated' | 'draft'
    requireTestSuccessBeforeRelease: boolean
  }) {
    try {
      const pools = parsePools(values.poolsText)
      const allowedModules = values.allowedModulesText
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean)

      saveMutation.mutate({
        mcp: {
          django_port: values.djangoPort,
          bridge_sse_port: values.ssePort,
        },
        server: {
          url: values.serverUrl,
          poll_interval: values.pollInterval,
        },
        worker: {
          pools,
        },
        tool_version: {
          active_conflict_policy: values.activeConflictPolicy,
          require_test_success_before_release: values.requireTestSuccessBeforeRelease,
        },
        sandbox: {
          execution_timeout: values.executionTimeout,
          allowed_modules: allowedModules,
        },
      })
    } catch (error) {
      apiMessage.error(error instanceof Error ? error.message : 'Invalid configuration format')
    }
  }

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card title="Configuration" loading={configQuery.isLoading}>
          <Form form={form} layout="vertical" onFinish={submit}>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Django Port" name="djangoPort" rules={[{ required: true }]}>
                  <InputNumber min={1} max={65535} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Bridge SSE Port" name="ssePort" rules={[{ required: true }]}>
                  <InputNumber min={1} max={65535} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Server URL" name="serverUrl" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Poll Interval(s)" name="pollInterval" rules={[{ required: true }]}>
                  <InputNumber min={0.1} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Execution Timeout(s)" name="executionTimeout" rules={[{ required: true }]}>
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Active Conflict Policy" name="activeConflictPolicy" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { value: 'deprecated', label: 'deprecated (demote previous active to deprecated)' },
                      { value: 'draft', label: 'draft (demote previous active to draft)' },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item
              label="Release Protection (require successful run-test before publishing to prod)"
              name="requireTestSuccessBeforeRelease"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Form.Item label="Allowed Modules (comma separated)" name="allowedModulesText" rules={[{ required: true }]}>
              <Input.TextArea rows={3} />
            </Form.Item>

            <Form.Item
              label="Worker Pools (JSON array)"
              name="poolsText"
              rules={[{ required: true }]}
              extra={'Example: [{"env":"prod","prefix":"node-prod","count":2}]'}
            >
              <Input.TextArea rows={8} />
            </Form.Item>

            <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
              Save Configuration
            </Button>
          </Form>
        </Card>
      </Space>
    </>
  )
}
