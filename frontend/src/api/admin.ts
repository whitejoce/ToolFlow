import { http } from '../lib/http'
import type {
  CreateToolReq,
  CreateToolResp,
  CreateToolVersionReq,
  CreateToolVersionResp,
  ExecutionDetailResp,
  GetExecutionsResp,
  GetRuntimeConfigResp,
  GetToolsResp,
  GetToolVersionsResp,
  MetricsOverviewResp,
  MetricsTimeseriesResp,
  ReleaseToolVersionReq,
  ReleaseToolVersionResp,
  RollbackToolReq,
  RollbackToolResp,
  RunToolTestReq,
  RunToolTestResp,
  UpdateToolReq,
  UpdateToolResp,
  UpdateToolVersionStatusReq,
  UpdateToolVersionStatusResp,
  UpdateRuntimeConfigReq,
  UpdateRuntimeConfigResp,
} from '../types/api'

export async function getTools() {
  const { data } = await http.get<GetToolsResp>('/api/admin/tools')
  return data
}

export async function getToolVersions(toolId: string) {
  const { data } = await http.get<GetToolVersionsResp>(`/api/admin/tools/${toolId}/versions`)
  return data
}

export async function createTool(payload: CreateToolReq) {
  const { data } = await http.post<CreateToolResp>('/api/admin/tools', payload)
  return data
}

export async function updateTool(toolId: string, payload: UpdateToolReq) {
  const { data } = await http.patch<UpdateToolResp>(`/api/admin/tools/${toolId}`, payload)
  return data
}

export async function createToolVersion(toolId: string, payload: CreateToolVersionReq) {
  const { data } = await http.post<CreateToolVersionResp>(`/api/admin/tools/${toolId}/versions`, payload)
  return data
}

export async function updateToolVersionStatus(toolId: string, version: number, payload: UpdateToolVersionStatusReq) {
  const { data } = await http.patch<UpdateToolVersionStatusResp>(`/api/admin/tools/${toolId}/versions/${version}/status`, payload)
  return data
}

export async function releaseToolVersion(toolId: string, payload: ReleaseToolVersionReq) {
  const { data } = await http.post<ReleaseToolVersionResp>(`/api/admin/tools/${toolId}/release`, payload)
  return data
}

export async function rollbackToolVersion(toolId: string, payload: RollbackToolReq) {
  const { data } = await http.post<RollbackToolResp>(`/api/admin/tools/${toolId}/rollback`, payload)
  return data
}

export async function runToolTest(toolId: string, payload: RunToolTestReq) {
  const { data } = await http.post<RunToolTestResp>(`/api/admin/tools/${toolId}/run-test`, payload)
  return data
}

export async function getExecutions(params: {
  page: number
  pageSize: number
  status?: string
  toolId?: string
  executor?: string
  targetEnv?: string
}) {
  const { data } = await http.get<GetExecutionsResp>('/api/admin/executions', {
    params: {
      page: params.page,
      page_size: params.pageSize,
      status: params.status || undefined,
      tool_id: params.toolId || undefined,
      executor: params.executor || undefined,
      target_env: params.targetEnv || undefined,
    },
  })
  return data
}

export async function getExecutionDetail(executionId: string) {
  const { data } = await http.get<ExecutionDetailResp>(`/api/admin/executions/${executionId}`)
  return data
}

export async function getMetricsOverview() {
  const { data } = await http.get<MetricsOverviewResp>('/api/admin/metrics/overview')
  return data
}

export async function getMetricsTimeseries(windowMinutes: number) {
  const { data } = await http.get<MetricsTimeseriesResp>('/api/admin/metrics/timeseries', {
    params: { window_minutes: windowMinutes },
  })
  return data
}

export async function getRuntimeConfig() {
  const { data } = await http.get<GetRuntimeConfigResp>('/api/admin/config')
  return data
}

export async function updateRuntimeConfig(payload: UpdateRuntimeConfigReq) {
  const { data } = await http.put<UpdateRuntimeConfigResp>('/api/admin/config', payload)
  return data
}
