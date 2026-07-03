import { useCallback, useEffect, useState } from 'react'
import { Bot, Eye, Radio, ShieldAlert, Siren, Wrench } from 'lucide-react'
import { fetchAgentTraces } from '../api/client'
import type { AgentTrace } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'
import { EmptyState } from '../components/EmptyState'
import { SkeletonTableRows } from '../components/Skeleton'

const AGENT_META: Record<AgentTrace['subject_type'], { label: string; icon: typeof Siren; tone: string }> = {
  incident: { label: 'SelfHealingAgent', icon: Siren, tone: 'tone-warning' },
  security_alert: { label: 'SecurityAgent', icon: ShieldAlert, tone: 'tone-danger' },
}

function summarize(value: Record<string, unknown>): string {
  const text = JSON.stringify(value)
  return text.length > 90 ? `${text.slice(0, 90)}…` : text
}

export default function ActivityPage() {
  const [traces, setTraces] = useState<AgentTrace[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    fetchAgentTraces()
      .then(setTraces)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(reload, [reload])

  useLiveEvents((event) => {
    if (event.type === 'agent_trace_added') reload()
  })

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>Hoạt động Agent</h1>
          <p>Nhật ký suy luận thời gian thực: từng bước quan sát và hành động của SelfHealingAgent và SecurityAgent.</p>
        </div>
      </div>

      {error && <div className="error-banner">Không thể tải dữ liệu: {error}</div>}

      <div className="table-wrap">
        {!loading && traces.length === 0 ? (
          <EmptyState
            icon={Bot}
            title="Chưa có hoạt động nào"
            subtitle="Nhật ký sẽ xuất hiện ngay khi SelfHealingAgent hoặc SecurityAgent bắt đầu xử lý."
          />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Agent</th>
                <th>Đối tượng</th>
                <th>Pha</th>
                <th>Tool</th>
                <th>Kết quả</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonTableRows rows={6} cols={6} />
              ) : (
                traces.map((trace) => {
                  const meta = AGENT_META[trace.subject_type]
                  const AgentIcon = meta.icon
                  const PhaseIcon = trace.read_only ? Eye : Wrench
                  return (
                    <tr key={trace.id}>
                      <td className="cell-muted">{new Date(trace.timestamp).toLocaleString('vi-VN')}</td>
                      <td>
                        <span className={`badge ${meta.tone}`}>
                          <AgentIcon size={12} />
                          {meta.label}
                        </span>
                      </td>
                      <td className="chip">{trace.subject_id.slice(0, 8)}</td>
                      <td>
                        <span className={`badge ${trace.read_only ? 'tone-info' : 'tone-primary'}`}>
                          <PhaseIcon size={12} />
                          {trace.read_only ? 'Quan sát' : 'Hành động'}
                        </span>
                      </td>
                      <td className="cell-mono">{trace.tool}</td>
                      <td className="cell-muted">{summarize(trace.result)}</td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="section-title">
        <Radio size={16} />
        Realtime qua /ws/events (agent_trace_added)
      </div>
    </div>
  )
}
