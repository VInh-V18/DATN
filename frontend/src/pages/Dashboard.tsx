import { useCallback, useEffect, useState } from 'react'
import { fetchIncidents, fetchSecurityAlerts, fetchTopology } from '../api/client'
import type { Incident, SecurityAlert, Topology } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'

const RELEVANT_EVENTS = new Set([
  'incident_created',
  'incident_updated',
  'security_alert_created',
  'security_alert_updated',
])

export default function Dashboard() {
  const [topology, setTopology] = useState<Topology | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [alerts, setAlerts] = useState<SecurityAlert[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    Promise.all([fetchTopology(), fetchIncidents(), fetchSecurityAlerts()])
      .then(([topo, inc, sec]) => {
        setTopology(topo)
        setIncidents(inc)
        setAlerts(sec)
      })
      .catch((err) => setError(String(err)))
  }, [])

  useEffect(reload, [reload])

  useLiveEvents((event) => {
    if (RELEVANT_EVENTS.has(event.type)) reload()
  })

  const openIncidents = incidents.filter((i) => i.status !== 'resolved' && i.status !== 'failed')
  const activeAlerts = alerts.filter((a) => a.status !== 'blocked' && a.status !== 'rejected')

  return (
    <div className="page">
      <h1>Tổng quan hệ thống</h1>
      {error && <p className="error">Không thể tải dữ liệu: {error}</p>}
      <div className="card-grid">
        <div className="card">
          <h2>{topology?.devices.length ?? '—'}</h2>
          <p>Thiết bị trong topology</p>
        </div>
        <div className="card">
          <h2>{openIncidents.length}</h2>
          <p>Sự cố đang xử lý</p>
        </div>
        <div className="card">
          <h2>{activeAlerts.length}</h2>
          <p>Cảnh báo an ninh chưa xử lý</p>
        </div>
        <div className="card">
          <h2>{topology?.links.length ?? '—'}</h2>
          <p>Liên kết mạng</p>
        </div>
      </div>

      <h2>Sự cố gần đây</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Thời gian</th>
            <th>Mô tả</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {incidents.slice(0, 5).map((incident) => (
            <tr key={incident.id}>
              <td>{new Date(incident.timestamp).toLocaleString('vi-VN')}</td>
              <td>{incident.description}</td>
              <td>
                <span className={`badge status-${incident.status}`}>{incident.status}</span>
              </td>
            </tr>
          ))}
          {incidents.length === 0 && (
            <tr>
              <td colSpan={3}>Chưa có sự cố nào.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
