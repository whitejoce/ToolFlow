import { useQuery } from '@tanstack/react-query'
import { Card, Col, Empty, Row, Select, Space, Statistic, Tag, Typography } from 'antd'
import { CodeSandboxOutlined } from '@ant-design/icons'
import { useMemo, useState } from 'react'
import { getExecutions, getMetricsOverview } from '../api/admin'
import type { ExecutionListItem } from '../types/api'

const healthMeta: Record<string, { color: string; label: string }> = {
  success: { color: 'green', label: 'Running' },
  running: { color: 'blue', label: 'Running' },
  pending: { color: 'gold', label: 'Pending' },
  error: { color: 'red', label: 'Error' },
}

function inferEnv(execution: ExecutionListItem) {
  if (execution.target_env === 'prod' || execution.target_env === 'test') {
    return execution.target_env
  }
  const name = (execution.executor || '').toLowerCase()
  if (name.includes('test')) return 'test'
  if (name.includes('prod')) return 'prod'
  // Default to prod when no explicit marker is present to avoid misclassifying stable executors.
  return 'prod'
}

export default function MetricsPage() {
  const [envFilter, setEnvFilter] = useState<'all' | 'prod' | 'test'>('all')

  const overviewQuery = useQuery({
    queryKey: ['metricsOverview'],
    queryFn: getMetricsOverview,
    refetchInterval: 10000,
  })

  const executorQuery = useQuery({
    queryKey: ['executorStateCards'],
    queryFn: () => getExecutions({ page: 1, pageSize: 200 }),
    refetchInterval: 5000,
  })

  const counters = overviewQuery.data?.counters

  const executors = useMemo(() => {
    const rows: Array<{
      name: string
      env: 'prod' | 'test'
      status: string
      updatedAt: string
      toolId: string
      durationMs: number | null
    }> = []

    const latestByExecutor = new Map<string, ExecutionListItem>()
    for (const item of executorQuery.data?.items ?? []) {
      if (!item.executor) continue
      if (!latestByExecutor.has(item.executor)) {
        latestByExecutor.set(item.executor, item)
      }
    }

    for (const [executor, exec] of latestByExecutor.entries()) {
      const env = inferEnv(exec)
      rows.push({
        name: executor,
        env,
        status: exec.status,
        updatedAt: exec.updated_at,
        toolId: exec.tool_id,
        durationMs: exec.duration_ms,
      })
    }

    rows.sort((a, b) => {
      if (a.env !== b.env) return a.env.localeCompare(b.env)
      return a.name.localeCompare(b.name)
    })
    return rows
  }, [executorQuery.data])

  const filteredExecutors = useMemo(() => {
    if (envFilter === 'all') return executors
    return executors.filter((item) => item.env === envFilter)
  }, [envFilter, executors])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card className="metric-card">
            <Statistic title="Total 24h" value={counters?.total_24h ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="metric-card">
            <Statistic title="Success 24h" value={counters?.success_24h ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="metric-card">
            <Statistic title="Failed 24h" value={counters?.failed_24h ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card className="metric-card">
            <Statistic title="Success Rate" value={counters?.success_rate_24h ?? 0} suffix="%" />
          </Card>
        </Col>
      </Row>

      <Card
        title="Executor List"
        extra={
          <Select
            value={envFilter}
            onChange={setEnvFilter}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: 'All' },
              { value: 'prod', label: 'prod' },
              { value: 'test', label: 'test' },
            ]}
          />
        }
        loading={executorQuery.isLoading}
      >
        <Row gutter={[16, 16]}>
          {filteredExecutors.length === 0 ? (
            <Col span={24}>
              <Empty description="No executor activity" />
            </Col>
          ) : (
            filteredExecutors.map((executor) => {
              const meta = healthMeta[executor.status] ?? { color: 'default', label: 'Offline' }
              const statusClass = `executor-card executor-card-${executor.status}`
              return (
                <Col key={executor.name} xs={24} sm={12} lg={8} xl={6}>
                  <Card className={statusClass} size="small" hoverable>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Space size={6}>
                        <CodeSandboxOutlined style={{ color: '#5b7cff' }} />
                        <Typography.Text strong>{executor.name}</Typography.Text>
                      </Space>
                      <Space size={8}>
                        <Tag color={executor.env === 'prod' ? 'cyan' : 'gold'}>{executor.env}</Tag>
                        <Tag color={meta.color}>{meta.label}</Tag>
                      </Space>
                      <Typography.Text type="secondary">Latest Tool: {executor.toolId}</Typography.Text>
                      <Typography.Text type="secondary">Latest Duration: {executor.durationMs ?? '-'} ms</Typography.Text>
                      <Typography.Text type="secondary">Updated At: {new Date(executor.updatedAt).toLocaleString()}</Typography.Text>
                    </Space>
                  </Card>
                </Col>
              )
            })
          )}
        </Row>
      </Card>
    </Space>
  )
}
