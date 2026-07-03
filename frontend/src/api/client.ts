import axios from 'axios'
import type {
  ActionLog,
  AgentTrace,
  ChatResponse,
  Incident,
  SecurityAlert,
  Topology,
} from './types'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

export const apiClient = axios.create({ baseURL })

export const wsUrl = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws/events'

export async function fetchTopology(): Promise<Topology> {
  const { data } = await apiClient.get<Topology>('/topology')
  return data
}

export async function fetchIncidents(): Promise<Incident[]> {
  const { data } = await apiClient.get<Incident[]>('/incidents')
  return data
}

export async function fetchIncidentActions(incidentId: string): Promise<ActionLog[]> {
  const { data } = await apiClient.get<ActionLog[]>(`/incidents/${incidentId}/actions`)
  return data
}

export async function approveIncident(incidentId: string, approved: boolean): Promise<Incident> {
  const { data } = await apiClient.post<Incident>(`/incidents/${incidentId}/approve`, { approved })
  return data
}

export async function fetchSecurityAlerts(): Promise<SecurityAlert[]> {
  const { data } = await apiClient.get<SecurityAlert[]>('/security/alerts')
  return data
}

export async function approveSecurityAlert(alertId: string, approved: boolean): Promise<{ status: string }> {
  const { data } = await apiClient.post<{ status: string }>(`/security/alerts/${alertId}/approve`, { approved })
  return data
}

export async function sendChatMessage(message: string, sessionId: string | null): Promise<ChatResponse> {
  const { data } = await apiClient.post<ChatResponse>('/chat', { message, session_id: sessionId })
  return data
}

export async function fetchAgentTraces(limit = 100): Promise<AgentTrace[]> {
  const { data } = await apiClient.get<AgentTrace[]>('/agent-traces', { params: { limit } })
  return data
}
