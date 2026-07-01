export interface Interface {
  id: string
  name: string
  status: string
  ip_address: string | null
}

export interface Device {
  id: string
  name: string
  node_type: string
  role: string
  management_address: string | null
  gns3_node_id: string | null
  interfaces: Interface[]
}

export interface TopologyLink {
  id: string
  port_a_id: string
  port_b_id: string
  status: string
}

export interface Topology {
  devices: Device[]
  links: TopologyLink[]
}

export interface Incident {
  id: string
  timestamp: string
  description: string
  root_cause: string | null
  status: string
  device_ids: string[]
  resolved_at: string | null
}

export interface ActionLog {
  id: string
  incident_id: string
  tool: string
  parameters: Record<string, unknown>
  result: Record<string, unknown>
  timestamp: string
}

export interface SecurityAlert {
  id: string
  timestamp: string
  source_ip: string
  attack_type: string
  severity: string
  status: string
  attack_techniques: string[]
}

export interface ChatMessageTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  session_id: string
  reply: string
  tool_calls: Array<{ name: string; arguments: Record<string, unknown>; output: unknown }>
  requires_confirmation: boolean
  pending_action: Record<string, unknown> | null
}
