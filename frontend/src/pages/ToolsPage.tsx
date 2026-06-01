import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Card,
  Col,
  Collapse,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createTool,
  createToolVersion,
  getExecutionDetail,
  getTools,
  getToolVersions,
  releaseToolVersion,
  runToolTest,
  updateTool,
  updateToolVersionStatus,
} from '../api/admin'
import { useEffect, useMemo, useState } from 'react'
import type { ToolListItem, ToolVersionItem } from '../types/api'
import Editor from '@monaco-editor/react'

const { Text } = Typography

const versionStatusColor: Record<string, string> = {
  active: 'green',
  draft: 'gold',
  deprecated: 'red',
}

const DEFAULT_CODE = `def main(arguments, context):
    message = arguments.get("message", "hello")
    return {"echo": message, "executor": context.get("executor")}
`

const jsonSchemaTemplate = '{\n  "type": "object",\n  "properties": {\n    "message": {"type": "string"}\n  }\n}'

const sectionLabelStyle = { display: 'block', marginBottom: 6 }

type SchemaField = {
  key: string
  label: string
  type: string
  required: boolean
  description: string
  enumValues: Array<string | number> | null
  defaultValue: unknown
}

export default function ToolsPage() {
  const [apiMessage, contextHolder] = message.useMessage()
  const queryClient = useQueryClient()
  const [createToolOpen, setCreateToolOpen] = useState(false)
  const [runTestOpen, setRunTestOpen] = useState(false)
  const [selectedToolId, setSelectedToolId] = useState<string>('')
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<number | null>(null)
  const [selectedExecutionId, setSelectedExecutionId] = useState<string>('')
  const [editorCode, setEditorCode] = useState(DEFAULT_CODE)
  const [versionMessage, setVersionMessage] = useState('')
  const [toolDescription, setToolDescription] = useState('')
  const [entryPoint, setEntryPoint] = useState('main')
  const [versionStatus, setVersionStatus] = useState<'draft' | 'active' | 'deprecated'>('draft')
  const [schemaText, setSchemaText] = useState(jsonSchemaTemplate)
  const [configText, setConfigText] = useState('{\n}')
  const [pendingLatestVersion, setPendingLatestVersion] = useState<number | null>(null)

  const [createForm] = Form.useForm()
  const [testForm] = Form.useForm()

  const toolsQuery = useQuery({
    queryKey: ['tools'],
    queryFn: getTools,
  })

  const versionsQuery = useQuery({
    queryKey: ['toolVersions', selectedToolId],
    queryFn: () => getToolVersions(selectedToolId),
    enabled: !!selectedToolId,
  })

  const executionDetailQuery = useQuery({
    queryKey: ['executionDetailFromTools', selectedExecutionId],
    queryFn: () => getExecutionDetail(selectedExecutionId),
    enabled: !!selectedExecutionId,
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'pending' || status === 'running' ? 2500 : false
    },
  })

  const createToolMutation = useMutation({
    mutationFn: createTool,
    onSuccess: (data) => {
      apiMessage.success(`Tool ${data.id} created`)
      setCreateToolOpen(false)
      createForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['tools'] })
    },
    onError: (error: Error) => apiMessage.error(error.message || 'Failed to create tool'),
  })

  const createVersionMutation = useMutation({
    mutationFn: (payload: {
      toolId: string
      code: string
      entry_point: string
      message: string
      schema: Record<string, unknown>
      config: Record<string, unknown>
    }) =>
      createToolVersion(payload.toolId, {
        code: payload.code,
        entry_point: payload.entry_point,
        message: payload.message,
        schema: payload.schema,
        config: payload.config,
      }),
    onSuccess: (data) => {
      apiMessage.success(`New version v${data.version} created`)
      queryClient.invalidateQueries({ queryKey: ['toolVersions', selectedToolId] })
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      setPendingLatestVersion(data.version)
    },
    onError: (error: Error) => apiMessage.error(error.message || 'Failed to create version'),
  })

  const releaseMutation = useMutation({
    mutationFn: (payload: { toolId: string; version: number }) =>
      releaseToolVersion(payload.toolId, {
        environment: 'prod',
        version: payload.version,
      }),
    onSuccess: (data) => {
      apiMessage.success(`Prod released v${data.version}. Status was synchronized by backend.`)
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      queryClient.invalidateQueries({ queryKey: ['toolVersions', selectedToolId] })
    },
    onError: () => {
      apiMessage.error('Release failed. If Release Protection is enabled, run-test must succeed first.')
    },
  })

  const updateToolMutation = useMutation({
    mutationFn: (payload: { toolId: string; description: string }) =>
      updateTool(payload.toolId, {
        name: selectedTool?.name || payload.toolId,
        description: payload.description,
        operator: 'frontend-admin',
      }),
    onSuccess: () => {
      apiMessage.success('Tool metadata updated')
      queryClient.invalidateQueries({ queryKey: ['tools'] })
    },
    onError: (error: Error) => apiMessage.error(error.message || 'Failed to update tool metadata'),
  })

  const updateStatusMutation = useMutation({
    mutationFn: (payload: { toolId: string; version: number; status: 'draft' | 'active' | 'deprecated' }) =>
      updateToolVersionStatus(payload.toolId, payload.version, { status: payload.status }),
    onSuccess: (data) => {
      apiMessage.success(`Status updated: v${data.version} -> ${data.status}`)
      queryClient.invalidateQueries({ queryKey: ['toolVersions', selectedToolId] })
      queryClient.invalidateQueries({ queryKey: ['tools'] })
    },
    onError: (error: Error) => apiMessage.error(error.message || 'Failed to update status'),
  })

  const runTestMutation = useMutation({
    mutationFn: (payload: { toolId: string; argumentsObj: Record<string, unknown>; version?: number }) =>
      runToolTest(payload.toolId, {
        arguments: payload.argumentsObj,
        version: payload.version,
      }),
    onSuccess: (data) => {
      apiMessage.success(`Test submitted. Execution: ${data.execution_id}`)
      setRunTestOpen(false)
      setSelectedExecutionId(data.execution_id)
      queryClient.invalidateQueries({ queryKey: ['executions'] })
    },
    onError: (error: Error) => apiMessage.error(error.message || 'Run test failed'),
  })

  const items = toolsQuery.data?.items ?? []
  const versionItems = versionsQuery.data?.items ?? []

  const selectedTool = useMemo(
    () => items.find((item) => item.id === selectedToolId) ?? null,
    [items, selectedToolId],
  )

  const selectedVersion = useMemo(
    () => versionItems.find((item) => item.version === selectedVersionNumber) ?? null,
    [versionItems, selectedVersionNumber],
  )

  const runTestSchemaFields = useMemo<SchemaField[]>(() => {
    const schema = selectedVersion?.schema
    if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return []

    const root = schema as Record<string, unknown>
    const properties = root.properties
    if (!properties || typeof properties !== 'object' || Array.isArray(properties)) return []

    const requiredList = Array.isArray(root.required)
      ? root.required.filter((x): x is string => typeof x === 'string')
      : []

    const fields: SchemaField[] = []
    for (const [key, rawProp] of Object.entries(properties as Record<string, unknown>)) {
      if (!rawProp || typeof rawProp !== 'object' || Array.isArray(rawProp)) continue
      const prop = rawProp as Record<string, unknown>
      const type = typeof prop.type === 'string' ? prop.type : 'string'
      const enumValues = Array.isArray(prop.enum)
        ? prop.enum.filter((v): v is string | number => typeof v === 'string' || typeof v === 'number')
        : null

      fields.push({
        key,
        label: key,
        type,
        required: requiredList.includes(key),
        description: typeof prop.description === 'string' ? prop.description : '',
        enumValues,
        defaultValue: prop.default,
      })
    }

    return fields
  }, [selectedVersion])

  function toPrettyJson(value: unknown, fallback = '{}') {
    try {
      return JSON.stringify(value ?? {}, null, 2)
    } catch {
      return fallback
    }
  }

  useEffect(() => {
    if (!selectedToolId && items.length > 0) {
      setSelectedToolId(items[0].id)
    }
  }, [items, selectedToolId])

  useEffect(() => {
    setSelectedVersionNumber(null)
    setPendingLatestVersion(null)
  }, [selectedToolId])

  useEffect(() => {
    if (versionItems.length === 0) {
      // Keep current selection when query refresh returns an empty transient state.
      return
    }

    if (pendingLatestVersion !== null) {
      // After save, switch only when the new version appears in the refreshed list.
      if (versionItems[0].version >= pendingLatestVersion) {
        setSelectedVersionNumber(versionItems[0].version)
        setPendingLatestVersion(null)
      }
      return
    }

    const currentStillExists =
      selectedVersionNumber !== null &&
      versionItems.some((item) => item.version === selectedVersionNumber)
    if (currentStillExists) {
      return
    }

    // Version list is sorted by version desc; the first item is latest.
    setSelectedVersionNumber(versionItems[0].version)
  }, [versionItems, selectedVersionNumber, pendingLatestVersion])

  useEffect(() => {
    if (!selectedVersion) {
      // Avoid clearing editor while waiting for list refresh after creating a new version.
      if (selectedVersionNumber === null && versionItems.length === 0) {
        setEditorCode(DEFAULT_CODE)
        setEntryPoint('main')
        setVersionStatus('draft')
        setVersionMessage('')
        setSchemaText(jsonSchemaTemplate)
        setConfigText('{\n}')
      }
      return
    }

    setEditorCode(selectedVersion.code || DEFAULT_CODE)
    setEntryPoint(selectedVersion.entry_point || 'main')
    setVersionStatus((selectedVersion.status as 'draft' | 'active' | 'deprecated') || 'draft')
    setVersionMessage(selectedVersion.message || '')
    setSchemaText(toPrettyJson(selectedVersion.schema, jsonSchemaTemplate))
    setConfigText(toPrettyJson(selectedVersion.config, '{\n}'))
  }, [selectedVersion])

  useEffect(() => {
    if (!selectedTool) {
      setToolDescription('')
      return
    }
    setToolDescription(selectedTool.description || '')
  }, [selectedTool])

  useEffect(() => {
    if (!runTestOpen) return

    const generatedArgs: Record<string, unknown> = {}
    for (const field of runTestSchemaFields) {
      if (field.defaultValue !== undefined) {
        generatedArgs[field.key] = field.defaultValue
      } else if (field.type === 'number' || field.type === 'integer') {
        generatedArgs[field.key] = 0
      } else if (field.type === 'boolean') {
        generatedArgs[field.key] = false
      } else {
        generatedArgs[field.key] = ''
      }
    }

    testForm.setFieldsValue({
      version: selectedVersionNumber ?? undefined,
      generatedArgs,
      argumentsText: runTestSchemaFields.length === 0 ? '{\n  "message": "hello from frontend"\n}' : '',
    })
  }, [runTestOpen, runTestSchemaFields, selectedVersionNumber, testForm])

  function parseJsonSafe(label: string, raw: string) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>
      }
      throw new Error(`${label} must be a JSON object`)
    } catch (error) {
      const msg = error instanceof Error ? error.message : `${label} format error`
      apiMessage.error(msg)
      return null
    }
  }

  function sanitizeGeneratedArgs(values: Record<string, unknown> | undefined) {
    if (!values) return {}
    const result: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(values)) {
      if (v === '' || v === undefined) continue
      result[k] = v
    }
    return result
  }

  const toolColumns: ColumnsType<ToolListItem> = [
    {
      title: 'Tool ID',
      dataIndex: 'id',
      render: (value: string) => <Text strong>{value}</Text>,
    },
    {
      title: 'Description',
      dataIndex: 'description',
      render: (value: string) => <Text type="secondary">{value || '-'}</Text>,
    },
  ]

  const versionColumns: ColumnsType<ToolVersionItem> = [
    {
      title: 'Version',
      dataIndex: 'version',
      width: 100,
      render: (v: number) => <Tag color="purple">v{v}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 120,
      render: (s: string) => <Tag color={versionStatusColor[s] || 'default'}>{s}</Tag>,
    },
    { title: 'Entry', dataIndex: 'entry_point', width: 140 },
    {
      title: 'Release Notes',
      dataIndex: 'message',
      render: (m: string) => <Text type="secondary">{m || '-'}</Text>,
    },
  ]

  function submitToolMeta() {
    if (!selectedToolId) {
      apiMessage.warning('Please select a tool first')
      return
    }

    if (selectedTool && toolDescription === (selectedTool.description || '')) {
      apiMessage.info('No metadata changes')
      return
    }

    updateToolMutation.mutate({
      toolId: selectedToolId,
      description: toolDescription,
    })
  }

  function submitCreateVersion() {
    if (!selectedToolId) {
      apiMessage.warning('Please select a tool first')
      return
    }
    if (!editorCode.trim()) {
      apiMessage.warning('Code cannot be empty')
      return
    }
    const schemaObj = parseJsonSafe('Schema', schemaText)
    const configObj = parseJsonSafe('Config', configText)
    if (!schemaObj || !configObj) return

    if (selectedVersion) {
      const noChanges =
        editorCode === (selectedVersion.code || '') &&
        (entryPoint || 'main') === (selectedVersion.entry_point || 'main') &&
        versionMessage === (selectedVersion.message || '') &&
        JSON.stringify(schemaObj) === JSON.stringify(selectedVersion.schema || {}) &&
        JSON.stringify(configObj) === JSON.stringify(selectedVersion.config || {})

      if (noChanges) {
        apiMessage.info('No content changes, skip creating a new version')
        return
      }
    }

    createVersionMutation.mutate({
      toolId: selectedToolId,
      code: editorCode,
      entry_point: entryPoint || 'main',
      message: versionMessage,
      schema: schemaObj,
      config: configObj,
    })
  }

  function handleReleaseProd() {
    if (!selectedToolId || !selectedVersionNumber) {
      apiMessage.warning('Please select a version first')
      return
    }
    releaseMutation.mutate({
      toolId: selectedToolId,
      version: selectedVersionNumber,
    })
  }

  function handleStatusChange(nextStatus: 'draft' | 'active' | 'deprecated') {
    setVersionStatus(nextStatus)
    if (!selectedToolId || !selectedVersionNumber || !selectedVersion) return
    if (selectedVersion.status === nextStatus) return

    updateStatusMutation.mutate({
      toolId: selectedToolId,
      version: selectedVersionNumber,
      status: nextStatus,
    })
  }

  return (
    <>
      {contextHolder}
      <Row gutter={16}>
        <Col xs={24} lg={8} xl={7}>
          <Card
            title="Tool Catalog"
            loading={toolsQuery.isLoading}
            extra={
              <Button type="primary" onClick={() => setCreateToolOpen(true)}>
                New Tool
              </Button>
            }
            styles={{ body: { padding: 10 } }}
          >
            <Table
              rowKey="id"
              columns={toolColumns}
              dataSource={items}
              pagination={false}
              size="small"
              onRow={(record) => ({
                onClick: () => setSelectedToolId(record.id),
                style: {
                  cursor: 'pointer',
                  background: record.id === selectedToolId ? 'rgba(24, 144, 255, 0.08)' : undefined,
                },
              })}
            />
          </Card>
        </Col>

        <Col xs={24} lg={16} xl={17}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card
              title={selectedTool ? `${selectedTool.name} Workspace` : 'Select a tool from the left'}
              styles={{ body: { padding: 18 } }}
              extra={
                <Space>
                  <Tag color={versionStatusColor[selectedVersion?.status || ''] || 'default'}>
                    Runtime Status: {selectedVersion?.status || '-'}
                  </Tag>
                  <Tag color="blue">prod: {selectedTool?.prod_version ?? '-'}</Tag>
                  <Tag color="gold">test: {selectedTool?.test_version ?? '-'}</Tag>
                </Space>
              }
            >
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Collapse
                  defaultActiveKey={['tool-metadata', 'version-ops']}
                  bordered={false}
                  size="small"
                  items={[
                    {
                      key: 'tool-metadata',
                      label: 'Tool Metadata',
                      children: (
                        <div style={{ padding: 12, border: '1px solid #edf2f8', borderRadius: 10, background: '#fafcff' }}>
                          <Row gutter={12}>
                            <Col xs={24} md={7}>
                              <Text type="secondary" style={sectionLabelStyle}>Tool ID</Text>
                              <Input value={selectedToolId} disabled />
                            </Col>
                            <Col xs={24} md={7}>
                              <Text type="secondary" style={sectionLabelStyle}>Current Version Status</Text>
                              <Select
                                style={{ width: '100%' }}
                                value={versionStatus}
                                onChange={handleStatusChange}
                                loading={updateStatusMutation.isPending}
                                options={[
                                  { value: 'draft', label: 'draft' },
                                  { value: 'active', label: 'active' },
                                  { value: 'deprecated', label: 'deprecated' },
                                ]}
                              />
                            </Col>
                            <Col xs={24} md={10}>
                              <div style={{ marginTop: 30, display: 'flex', justifyContent: 'flex-end' }}>
                                <Button onClick={submitToolMeta} loading={updateToolMutation.isPending}>
                                  Save Tool Metadata
                                </Button>
                              </div>
                            </Col>
                          </Row>

                          <div style={{ marginTop: 12 }}>
                            <Text type="secondary" style={sectionLabelStyle}>Description</Text>
                            <Input.TextArea
                              rows={3}
                              value={toolDescription}
                              onChange={(e) => setToolDescription(e.target.value)}
                              placeholder="Tool description"
                            />
                          </div>
                        </div>
                      ),
                    },
                    {
                      key: 'version-ops',
                      label: 'Version & Actions',
                      children: (
                        <div style={{ padding: 12, border: '1px solid #edf2f8', borderRadius: 10 }}>
                          <Row gutter={12}>
                            <Col xs={24} md={5}>
                              <Text type="secondary" style={sectionLabelStyle}>Version</Text>
                              <Select
                                style={{ width: '100%' }}
                                placeholder="Select version"
                                value={selectedVersionNumber ?? undefined}
                                onChange={setSelectedVersionNumber}
                                options={versionItems.map((item) => ({ value: item.version, label: `v${item.version}` }))}
                              />
                            </Col>
                            <Col xs={24} md={5}>
                              <Text type="secondary" style={sectionLabelStyle}>Entry Point</Text>
                              <Input value={entryPoint} onChange={(e) => setEntryPoint(e.target.value)} />
                            </Col>
                            <Col xs={24} md={14}>
                              <div style={{ marginTop: 30, display: 'flex', justifyContent: 'flex-end' }}>
                                <Space wrap>
                                  <Button type="primary" onClick={submitCreateVersion} loading={createVersionMutation.isPending}>
                                    Save New Version
                                  </Button>
                                  <Button onClick={() => setRunTestOpen(true)} disabled={!selectedToolId} loading={runTestMutation.isPending}>
                                    Run Test
                                  </Button>
                                  <Button onClick={handleReleaseProd} loading={releaseMutation.isPending}>
                                    Release to Prod
                                  </Button>
                                </Space>
                              </div>
                            </Col>
                          </Row>
                        </div>
                      ),
                    },
                  ]}
                />
                
                <div>
                  <Text type="secondary" style={sectionLabelStyle}>Release Notes</Text>
                  <Input
                    placeholder="Release notes for this new version"
                    value={versionMessage}
                    onChange={(e) => setVersionMessage(e.target.value)}
                  />
                </div>

                <div style={{ border: '1px solid #d6dbe5', borderRadius: 14, overflow: 'hidden' }}>
                  <Editor
                    language="python"
                    height="340px"
                    value={editorCode}
                    onChange={(value) => setEditorCode(value ?? '')}
                    options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false }}
                    theme="vs"
                  />
                </div>

                <Row gutter={12}>
                  <Col xs={24} md={12}>
                    <Text type="secondary" style={sectionLabelStyle}>Schema(JSON)</Text>
                    <Input.TextArea rows={8} value={schemaText} onChange={(e) => setSchemaText(e.target.value)} />
                  </Col>
                  <Col xs={24} md={12}>
                    <Text type="secondary" style={sectionLabelStyle}>Config(JSON)</Text>
                    <Input.TextArea rows={8} value={configText} onChange={(e) => setConfigText(e.target.value)} />
                  </Col>
                </Row>

              </Space>
            </Card>

            <Card title={selectedToolId ? `${selectedToolId} Version History` : 'Version History'} loading={versionsQuery.isLoading}>
              <Table rowKey="id" columns={versionColumns} dataSource={versionItems} pagination={false} size="small" />
            </Card>
          </Space>
        </Col>
      </Row>

      <Modal
        title="Create Tool"
        open={createToolOpen}
        onCancel={() => setCreateToolOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createToolMutation.isPending}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={(values: { id: string; description?: string }) => {
            createToolMutation.mutate({
              id: values.id,
              name: values.id,
              description: values.description,
              operator: 'frontend-admin',
            })
          }}
        >
          <Form.Item name="id" label="Tool ID" rules={[{ required: true }]}> 
            <Input placeholder="echo" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Run Test (routed to test executors)"
        open={runTestOpen}
        onCancel={() => setRunTestOpen(false)}
        onOk={() => testForm.submit()}
        confirmLoading={runTestMutation.isPending}
      >
        <Form
          form={testForm}
          layout="vertical"
          onFinish={(values: {
            version?: number
            argumentsText?: string
            generatedArgs?: Record<string, unknown>
          }) => {
            let argsObj: Record<string, unknown> = {}

            if (runTestSchemaFields.length > 0) {
              argsObj = sanitizeGeneratedArgs(values.generatedArgs)
            }

            const rawJson = (values.argumentsText || '').trim()
            if (rawJson) {
              const parsed = parseJsonSafe('arguments', rawJson)
              if (!parsed) return
              argsObj = { ...argsObj, ...parsed }
            }

            if (!selectedToolId) return
            runTestMutation.mutate({
              toolId: selectedToolId,
              argumentsObj: argsObj,
              version: values.version,
            })
          }}
        >
          <Form.Item name="version" label="Target Version (optional)">
            <InputNumber min={1} style={{ width: '100%' }} placeholder="Empty means current test release/latest" />
          </Form.Item>

          {runTestSchemaFields.length > 0 ? (
            <Row gutter={12}>
              {runTestSchemaFields.map((field) => (
                <Col key={field.key} xs={24} md={12}>
                  <Form.Item
                    name={['generatedArgs', field.key]}
                    label={`${field.label}${field.required ? ' *' : ''}`}
                    rules={field.required ? [{ required: true, message: `${field.label} is required` }] : undefined}
                    tooltip={field.description || undefined}
                  >
                    {field.enumValues && field.enumValues.length > 0 ? (
                      <Select
                        options={field.enumValues.map((v) => ({ value: v, label: String(v) }))}
                        placeholder={`Select ${field.label}`}
                      />
                    ) : field.type === 'number' || field.type === 'integer' ? (
                      <InputNumber style={{ width: '100%' }} placeholder={`Enter ${field.label}`} />
                    ) : field.type === 'boolean' ? (
                      <Select
                        options={[
                          { value: true, label: 'true' },
                          { value: false, label: 'false' },
                        ]}
                        placeholder={`Select ${field.label}`}
                      />
                    ) : (
                      <Input placeholder={`Enter ${field.label}`} />
                    )}
                  </Form.Item>
                </Col>
              ))}
            </Row>
          ) : (
            <Form.Item name="argumentsText" label="Arguments(JSON)" rules={[{ required: true }]}>
              <Input.TextArea rows={8} />
            </Form.Item>
          )}

          {runTestSchemaFields.length > 0 ? (
            <Form.Item name="argumentsText" label="Advanced JSON Override (optional, overrides same keys)">
              <Input.TextArea rows={4} placeholder={'Example:\n{\n  "trace": true\n}'} />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>

      <Drawer
        width={780}
        title={selectedExecutionId ? `Execution ${selectedExecutionId}` : 'Execution Detail'}
        open={!!selectedExecutionId}
        onClose={() => setSelectedExecutionId('')}
      >
        {executionDetailQuery.data ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Tag color={executionDetailQuery.data.status === 'success' ? 'green' : executionDetailQuery.data.status === 'error' ? 'red' : 'blue'}>
              {executionDetailQuery.data.status}
            </Tag>
            <Text>Tool: {executionDetailQuery.data.tool_id}</Text>
            <Text>Version: v{executionDetailQuery.data.version}</Text>
            <Text>Executor: {executionDetailQuery.data.executor || '-'}</Text>
            <Card size="small" title="Input(JSON)">
              <pre>{JSON.stringify(executionDetailQuery.data.input, null, 2)}</pre>
            </Card>
            <Card size="small" title="Output(JSON)">
              <pre>{JSON.stringify(executionDetailQuery.data.output, null, 2)}</pre>
            </Card>
            <Card size="small" title="Error">
              <pre>{executionDetailQuery.data.error || '-'}</pre>
            </Card>
            <Card size="small" title="Logs">
              <pre>{JSON.stringify(executionDetailQuery.data.logs, null, 2)}</pre>
            </Card>
          </Space>
        ) : null}
      </Drawer>
    </>
  )
}
