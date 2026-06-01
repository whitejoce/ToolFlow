import { useQuery } from '@tanstack/react-query'
import { Card, Col, Empty, Row, Select, Space, Statistic, Tag, Typography } from 'antd'
import { CodeSandboxOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { getExecutors, getExecutorsStreamUrl, getMetricsOverview } from '../api/admin'
import type { ExecutorItem } from '../types/api'

const healthMeta: Record<string, { color: string; label: string }> = {
  running: { color: 'blue', label: 'Running' },
  idle: { color: 'green', label: 'Idle' },
  offline: { color: 'default', label: 'Offline' },
}

function formatOptionalDateTime(value: string | null) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

export default function MetricsPage() {
  const [envFilter, setEnvFilter] = useState<'all' | 'prod' | 'test'>('all')
  const [executors, setExecutors] = useState<ExecutorItem[]>([])
  const [executorLoading, setExecutorLoading] = useState(true)

  const overviewQuery = useQuery({
    queryKey: ['metricsOverview'],
    queryFn: getMetricsOverview,
    refetchInterval: 10000,
  })

  useEffect(() => {
    let active = true
    setExecutorLoading(true)

    getExecutors()
      .then((data) => {
        if (active) setExecutors(data.items)
      })
      .finally(() => {
        if (active) setExecutorLoading(false)
      })

    const source = new EventSource(getExecutorsStreamUrl())
    source.addEventListener('executors', (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { items: ExecutorItem[] }
      if (active) {
        setExecutors(data.items)
        setExecutorLoading(false)
      }
    })
    source.onerror = () => {
      if (active) setExecutorLoading(false)
    }

    return () => {
      active = false
      source.close()
    }
  }, [])

  const counters = overviewQuery.data?.counters
  const filteredExecutors = envFilter === 'all' ? executors : executors.filter((item) => item.env === envFilter)

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
        loading={executorLoading}
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
                <Col key={executor.executor_id} xs={24} sm={12} lg={8} xl={6}>
                  <Card className={statusClass} size="small" hoverable>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Space size={6}>
                        <CodeSandboxOutlined style={{ color: '#5b7cff' }} />
                        <Typography.Text strong>{executor.executor_id}</Typography.Text>
                      </Space>
                      <Space size={8}>
                        <Tag color={executor.env === 'prod' ? 'cyan' : 'gold'}>{executor.env}</Tag>
                        <Tag color={meta.color}>{meta.label}</Tag>
                      </Space>
                      <Typography.Text type="secondary">Current Tool: {executor.current_tool_id || '-'}</Typography.Text>
                      <Typography.Text type="secondary">Current Execution: {executor.current_execution_id ? (executor.current_execution_id.length > 25 ? `${executor.current_execution_id.slice(0, 25)}...` : executor.current_execution_id) : '-'}</Typography.Text>
                      <Typography.Text type="secondary">Last Seen: {formatOptionalDateTime(executor.last_seen_at)}</Typography.Text>
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
