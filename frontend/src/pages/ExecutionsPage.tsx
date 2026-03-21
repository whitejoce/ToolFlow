import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Descriptions, Divider, Drawer, Form, Input, Select, Space, Table, Tag, Typography } from 'antd'
import { CodeSandboxOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { getExecutionDetail, getExecutions } from '../api/admin'
import type { ExecutionListItem } from '../types/api'

const statusColor: Record<string, string> = {
  pending: 'gold',
  running: 'blue',
  success: 'green',
  error: 'red',
}

function formatDateTimeShort(value: string) {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${hh}:${mm}`
}

export default function ExecutionsPage() {
  const [form] = Form.useForm()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState<{
    status?: string
    toolId?: string
    executor?: string
    targetEnv?: 'prod' | 'test'
  }>({})
  const [selectedId, setSelectedId] = useState<string>('')

  const listQuery = useQuery({
    queryKey: ['executions', page, pageSize, filters.status, filters.toolId, filters.executor, filters.targetEnv],
    queryFn: () =>
      getExecutions({
        page,
        pageSize,
        status: filters.status,
        toolId: filters.toolId,
        executor: filters.executor,
        targetEnv: filters.targetEnv,
      }),
    refetchInterval: 10000,
  })

  const detailQuery = useQuery({
    queryKey: ['executionDetail', selectedId],
    queryFn: () => getExecutionDetail(selectedId),
    enabled: !!selectedId,
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'pending' || s === 'running' ? 5000 : false
    },
  })

  const columns: ColumnsType<ExecutionListItem> = useMemo(
    () => [
      { title: 'Execution ID', dataIndex: 'id', width: 280 },
      { title: 'Tool', dataIndex: 'tool_id', width: 120 },
      { title: 'Version', dataIndex: 'version', width: 90 },
      {
        title: 'Env',
        dataIndex: 'target_env',
        width: 90,
        render: (v: string | undefined) =>
          v ? <Tag color={v === 'test' ? 'gold' : 'cyan'}>{v}</Tag> : <Tag>-</Tag>,
      },
      {
        title: 'Status',
        dataIndex: 'status',
        width: 100,
        render: (v: string) => <Tag color={statusColor[v] ?? 'default'}>{v}</Tag>,
      },
      {
        title: 'Executor',
        dataIndex: 'executor',
        width: 180,
        render: (v: string | null) =>
          v ? (
            <Space size={6}>
              <CodeSandboxOutlined style={{ color: '#5b7cff' }} />
              <span>{v}</span>
            </Space>
          ) : (
            '-'
          ),
      },
      { title: 'Duration(ms)', dataIndex: 'duration_ms', width: 120 },
      {
        title: 'Created At',
        dataIndex: 'created_at',
        width: 160,
        render: (v: string) => formatDateTimeShort(v),
      },
      {
        title: 'Action',
        key: 'action',
        width: 100,
        render: (_, row) => <Button onClick={() => setSelectedId(row.id)}>Info</Button>,
      },
    ],
    [],
  )

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="Tool Execution Records" loading={listQuery.isLoading}>
        <Form
          form={form}
          layout="inline"
          onFinish={(values) => {
            setPage(1)
            setFilters(values)
          }}
        >
          <Form.Item name="status" label="Status">
            <Select
              allowClear
              style={{ width: 120 }}
              options={[
                { value: 'pending', label: 'pending' },
                { value: 'running', label: 'running' },
                { value: 'success', label: 'success' },
                { value: 'error', label: 'error' },
              ]}
            />
          </Form.Item>
          <Form.Item name="targetEnv" label="Env">
            <Select
              allowClear
              style={{ width: 100 }}
              options={[
                { value: 'prod', label: 'prod' },
                { value: 'test', label: 'test' },
              ]}
            />
          </Form.Item>
          <Form.Item name="toolId" label="Tool">
            <Input style={{ width: 190 }} placeholder="tool name" />
          </Form.Item>
          <Form.Item name="executor" label="Executor">
            <Input style={{ width: 190 }} placeholder="node-alpha-1" />
          </Form.Item>

          <Space size={8} style={{ marginBottom: 12 }}>
            <Button type="primary" htmlType="submit">
              Search
            </Button>
            <Button
              onClick={() => {
                form.resetFields()
                setPage(1)
                setFilters({})
              }}
            >
              Reset
            </Button>
          </Space>
        </Form>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.pagination.total ?? 0,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <Drawer
        open={!!selectedId}
        onClose={() => setSelectedId('')}
        width={780}
        title={selectedId ? `Execution ${selectedId}` : 'Execution Detail'}
      >
        {detailQuery.data ? (
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <Card size="small" styles={{ body: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 } }}>
              <Space size={10} wrap>
                <Typography.Text type="secondary">Execution</Typography.Text>
                <Typography.Text strong>{detailQuery.data.id}</Typography.Text>
              </Space>
              <Tag color={statusColor[detailQuery.data.status] ?? 'default'} style={{ marginInlineEnd: 0 }}>
                {detailQuery.data.status.toUpperCase()}
              </Tag>
            </Card>

            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="Tool">{detailQuery.data.tool_id}</Descriptions.Item>
              <Descriptions.Item label="Version">v{detailQuery.data.version}</Descriptions.Item>
              <Descriptions.Item label="Env">{detailQuery.data.target_env || '-'}</Descriptions.Item>
              <Descriptions.Item label="Executor">{detailQuery.data.executor || '-'}</Descriptions.Item>
              <Descriptions.Item label="Duration">{detailQuery.data.duration_ms ?? '-'} ms</Descriptions.Item>
              <Descriptions.Item label="Updated At">{formatDateTimeShort(detailQuery.data.updated_at)}</Descriptions.Item>
            </Descriptions>

            {detailQuery.data.error ? (
              <Alert type="error" showIcon message="Execution Error" description={detailQuery.data.error} />
            ) : null}

            <Divider style={{ margin: '4px 0 0' }}>Payload</Divider>

            <Card size="small" title="Input JSON">
              <pre>{JSON.stringify(detailQuery.data.input, null, 2)}</pre>
            </Card>

            <Card size="small" title="Output JSON">
              <pre>{JSON.stringify(detailQuery.data.output, null, 2)}</pre>
            </Card>

            <Card size="small" title="Runtime Logs">
              <pre>{JSON.stringify(detailQuery.data.logs, null, 2)}</pre>
            </Card>
          </Space>
        ) : null}
      </Drawer>
    </Space>
  )
}
