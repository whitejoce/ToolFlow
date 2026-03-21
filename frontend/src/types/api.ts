export type EnvName = 'prod' | 'test'
export type ExecutionStatus = 'pending' | 'running' | 'success' | 'error'
export type ActiveConflictPolicy = 'deprecated' | 'draft'

export type JsonMap = Record<string, unknown>

export interface ToolListItem {
  id: string
  name: string
  description: string
  created_at: string
  prod_version: number | null
  test_version: number | null
}

export interface CreateToolReq {
  id: string
  name: string
  description?: string
  operator?: string
}

export interface CreateToolResp {
  id: string
  name: string
}

export interface UpdateToolReq {
  name?: string
  description?: string
  operator?: string
}

export interface UpdateToolResp {
  id: string
  name: string
  description: string
}

export interface GetToolsResp {
  items: ToolListItem[]
}

export interface ToolVersionItem {
  id: string
  version: number
  code?: string
  entry_point: string
  status: string
  message: string
  schema: JsonMap
  config: JsonMap
  created_at: string
}

export interface CreateToolVersionReq {
  code: string
  entry_point?: string
  config?: JsonMap
  schema?: JsonMap
  message?: string
  status?: string
  metadata?: JsonMap
}

export type CreateToolVersionResp = ToolVersionItem

export interface ReleaseToolVersionReq {
  environment: EnvName
  version: number
}

export interface ReleaseToolVersionResp {
  tool_id: string
  environment: EnvName
  version: number
  updated_at: string
}

export interface RollbackToolReq {
  environment: EnvName
  to_version: number
}

export interface RollbackToolResp {
  tool_id: string
  rolled_back_environment: EnvName
  current_version: number
  updated_at: string
}

export interface RunToolTestReq {
  arguments?: JsonMap
  version?: number
}

export interface RunToolTestResp {
  execution_id: string
  tool_id: string
  version: number
  status: ExecutionStatus
  target_env: 'test'
  created_at: string
}

export interface GetToolVersionsResp {
  items: ToolVersionItem[]
}

export interface ExecutionListItem {
  id: string
  tool_id: string
  version: number
  executor: string | null
  status: ExecutionStatus
  target_env?: EnvName
  duration_ms: number | null
  created_at: string
  updated_at: string
}

export interface GetExecutionsResp {
  items: ExecutionListItem[]
  pagination: {
    page: number
    page_size: number
    total: number
  }
}

export interface ExecutionLogItem {
  id: string
  level: 'info' | 'error' | 'debug'
  message: string
  data: JsonMap
  created_at: string
}

export interface ExecutionDetailResp {
  id: string
  tool_id: string
  version: number
  executor: string | null
  status: ExecutionStatus
  target_env?: EnvName
  input: JsonMap
  output: JsonMap
  error: string | null
  duration_ms: number | null
  created_at: string
  updated_at: string
  logs: ExecutionLogItem[]
}

export interface MetricsOverviewResp {
  window: { from: string; to: string }
  counters: {
    total_24h: number
    success_24h: number
    failed_24h: number
    running_now: number
    pending_now: number
    success_rate_24h: number
    avg_duration_ms_24h: number
  }
}

export interface MetricsPoint {
  ts: string | null
  total: number
  success: number
  error: number
  running: number
  avg_duration_ms: number
}

export interface MetricsTimeseriesResp {
  window: { from: string; to: string; bucket: 'minute' }
  points: MetricsPoint[]
}

export interface RuntimeConfig {
  mcp: {
    django_port: number
    bridge_sse_port: number
  }
  server: {
    url: string
    poll_interval: number
  }
  worker: {
    pools: Array<{
      env: EnvName
      prefix: string
      count: number
    }>
  }
  tool_version: {
    active_conflict_policy: ActiveConflictPolicy
    require_test_success_before_release: boolean
  }
  sandbox: {
    execution_timeout: number
    allowed_modules: string[]
  }
}

export interface GetRuntimeConfigResp {
  config: RuntimeConfig
}

export interface UpdateRuntimeConfigReq extends RuntimeConfig {}
export interface UpdateRuntimeConfigResp {
  config: RuntimeConfig
}

export interface UpdateToolVersionStatusReq {
  status: 'draft' | 'active' | 'deprecated'
}

export interface UpdateToolVersionStatusResp extends ToolVersionItem {}
