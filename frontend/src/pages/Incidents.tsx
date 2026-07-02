import { useEffect, useState } from 'react'
import { CheckCircle2, History, Siren, Wrench, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { approveIncident, fetchIncidentActions, fetchIncidents } from '../api/client'
import type { ActionLog, Incident } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import { SkeletonTableRows } from '../components/Skeleton'

const RELEVANT_EVENTS = new Set(['incident_created', 'incident_updated'])

const TOOL_ICON: Record<string, LucideIcon> = {
  block_ip: Siren,
  isolate_node: Siren,
  rollback: History,
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selected, setSelected] = useState<Incident | null>(null)
  const [actions, setActions] = useState<ActionLog[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () =>
    fetchIncidents()
      .then((list) => {
        setIncidents(list)
        setSelected((prev) => (prev ? list.find((i) => i.id === prev.id) ?? prev : prev))
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))

  useEffect(() => {
    load()
  }, [])

  const openDetail = async (incident: Incident) => {
    setSelected(incident)
    const logs = await fetchIncidentActions(incident.id)
    setActions(logs)
  }

  const handleApproval = async (incident: Incident, approved: boolean) => {
    await approveIncident(incident.id, approved)
    await load()
    if (selected?.id === incident.id) {
      await openDetail(incident)
    }
  }

  useLiveEvents(async (event) => {
    if (!RELEVANT_EVENTS.has(event.type)) return
    await load()
    if (selected) {
      const logs = await fetchIncidentActions(selected.id)
      setActions(logs)
    }
  })

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>Dòng thời gian sự cố</h1>
          <p>Toàn bộ sự cố agent phát hiện và các bước tự khắc phục đã thực hiện.</p>
        </div>
      </div>

      {error && <div className="error-banner">Không thể tải dữ liệu: {error}</div>}

      <div className="split">
        <div className="table-wrap">
          {!loading && incidents.length === 0 ? (
            <EmptyState icon={Siren} title="Chưa có sự cố nào" subtitle="Sự cố sẽ tự động xuất hiện khi agent phát hiện bất thường." />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Thời gian</th>
                  <th>Mô tả</th>
                  <th>Trạng thái</th>
                  <th>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {loading && <SkeletonTableRows rows={5} cols={4} />}
                {!loading && incidents.map((incident) => (
                  <tr
                    key={incident.id}
                    onClick={() => openDetail(incident)}
                    className={`clickable-row${selected?.id === incident.id ? ' selected-row' : ''}`}
                  >
                    <td className="cell-muted">{new Date(incident.timestamp).toLocaleString('vi-VN')}</td>
                    <td>{incident.description}</td>
                    <td>
                      <StatusBadge domain="incident" value={incident.status} />
                    </td>
                    <td>
                      {incident.status === 'awaiting_approval' && (
                        <div className="btn-row">
                          <button
                            className="btn btn-sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleApproval(incident, true)
                            }}
                          >
                            <CheckCircle2 size={13} />
                            Duyệt
                          </button>
                          <button
                            className="btn btn-sm btn-danger"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleApproval(incident, false)
                            }}
                          >
                            <XCircle size={13} />
                            Từ chối
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="split-side">
          <h2>Chi tiết hành động</h2>
          {!selected && (
            <EmptyState icon={Wrench} title="Chưa chọn sự cố" subtitle="Chọn một sự cố để xem nhật ký hành động của agent." />
          )}
          {selected && (
            <>
              <div className="detail-block">
                <div className="detail-label">Mô tả</div>
                <p>{selected.description}</p>
              </div>
              <div className="detail-block">
                <div className="detail-label">Nguyên nhân gốc</div>
                <p>{selected.root_cause ?? 'Đang chẩn đoán…'}</p>
              </div>
              <div className="detail-label" style={{ marginBottom: 8 }}>
                Nhật ký hành động
              </div>
              <ul className="action-log-list">
                {actions.map((action) => {
                  const Icon = TOOL_ICON[action.tool] ?? Wrench
                  return (
                    <li key={action.id} className="action-log-item">
                      <div className="action-log-icon">
                        <Icon size={13} />
                      </div>
                      <div>
                        <div className="action-log-tool">{action.tool}</div>
                        <div className="action-log-time">{new Date(action.timestamp).toLocaleString('vi-VN')}</div>
                      </div>
                    </li>
                  )
                })}
                {actions.length === 0 && (
                  <li className="cell-muted" style={{ padding: '8px 0' }}>
                    Chưa có hành động nào được ghi nhận.
                  </li>
                )}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
