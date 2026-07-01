import { useEffect, useState } from 'react'
import { approveIncident, fetchIncidentActions, fetchIncidents } from '../api/client'
import type { ActionLog, Incident } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'

const RELEVANT_EVENTS = new Set(['incident_created', 'incident_updated'])

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selected, setSelected] = useState<Incident | null>(null)
  const [actions, setActions] = useState<ActionLog[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    fetchIncidents()
      .then((list) => {
        setIncidents(list)
        setSelected((prev) => (prev ? list.find((i) => i.id === prev.id) ?? prev : prev))
      })
      .catch((err) => setError(String(err)))

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
    <div className="page split">
      <div className="split-main">
        <h1>Dòng thời gian sự cố</h1>
        {error && <p className="error">Không thể tải dữ liệu: {error}</p>}
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
            {incidents.map((incident) => (
              <tr key={incident.id} onClick={() => openDetail(incident)} className="clickable-row">
                <td>{new Date(incident.timestamp).toLocaleString('vi-VN')}</td>
                <td>{incident.description}</td>
                <td>
                  <span className={`badge status-${incident.status}`}>{incident.status}</span>
                </td>
                <td>
                  {incident.status === 'awaiting_approval' && (
                    <>
                      <button onClick={(e) => { e.stopPropagation(); handleApproval(incident, true) }}>
                        Phê duyệt
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); handleApproval(incident, false) }}>
                        Từ chối
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="split-side">
        <h2>Chi tiết hành động</h2>
        {!selected && <p>Chọn một sự cố để xem nhật ký hành động của agent.</p>}
        {selected && (
          <>
            <p><strong>{selected.description}</strong></p>
            <p>Nguyên nhân: {selected.root_cause ?? 'đang chẩn đoán'}</p>
            <ul className="action-log-list">
              {actions.map((action) => (
                <li key={action.id}>
                  <div className="action-log-tool">{action.tool}</div>
                  <div className="action-log-time">{new Date(action.timestamp).toLocaleString('vi-VN')}</div>
                </li>
              ))}
              {actions.length === 0 && <li>Chưa có hành động nào được ghi nhận.</li>}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
