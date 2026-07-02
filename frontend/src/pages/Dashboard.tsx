import { useCallback, useEffect, useState } from 'react'
import { Cable, ClipboardList, Server, ShieldAlert, Siren } from 'lucide-react'
import { fetchIncidents, fetchSecurityAlerts, fetchTopology } from '../api/client'
import type { Incident, SecurityAlert, Topology } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'
import { StatCard } from '../components/StatCard'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import { SkeletonTableRows } from '../components/Skeleton'

const RELEVANT_EVENTS = new Set([
  'incident_created',
  'incident_updated',
  'security_alert_created',
  'security_alert_updated',
  'topology_updated',
])

export default function Dashboard() {
  const [topology, setTopology] = useState<Topology | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [alerts, setAlerts] = useState<SecurityAlert[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    Promise.all([fetchTopology(), fetchIncidents(), fetchSecurityAlerts()])
      .then(([topo, inc, sec]) => {
        setTopology(topo)
        setIncidents(inc)
        setAlerts(sec)
        setError(null)
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(reload, [reload])

  useLiveEvents((event) => {
    if (RELEVANT_EVENTS.has(event.type)) reload()
  })

  const openIncidents = incidents.filter((i) => i.status !== 'resolved' && i.status !== 'failed')
  const activeAlerts = alerts.filter((a) => a.status !== 'blocked' && a.status !== 'rejected')
  const linksUp = topology?.links.filter((l) => l.status === 'up').length ?? 0

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>Tổng quan hệ thống</h1>
          <p>Trạng thái mạng, sự cố và an ninh theo thời gian thực.</p>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <ShieldAlert size={15} />
          Không thể tải dữ liệu: {error}
        </div>
      )}

      <div className="stat-grid">
        <StatCard icon={Server} tone="primary" loading={loading} value={topology?.devices.length ?? 0} label="Thiết bị trong topology" />
        <StatCard icon={Siren} tone="warning" loading={loading} value={openIncidents.length} label="Sự cố đang xử lý" />
        <StatCard icon={ShieldAlert} tone="danger" loading={loading} value={activeAlerts.length} label="Cảnh báo an ninh chưa xử lý" />
        <StatCard
          icon={Cable}
          tone="success"
          loading={loading}
          value={`${linksUp}/${topology?.links.length ?? 0}`}
          label="Liên kết đang hoạt động"
        />
      </div>

      <div className="section-title">
        <ClipboardList size={16} />
        Sự cố gần đây
      </div>
      <div className="table-wrap">
        {!loading && incidents.length === 0 ? (
          <EmptyState icon={Siren} title="Chưa có sự cố nào" subtitle="Hệ thống sẽ tự động ghi nhận khi phát hiện bất thường." />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Mô tả</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonTableRows rows={4} cols={3} />
              ) : (
                incidents.slice(0, 6).map((incident) => (
                  <tr key={incident.id}>
                    <td className="cell-muted">{new Date(incident.timestamp).toLocaleString('vi-VN')}</td>
                    <td>{incident.description}</td>
                    <td>
                      <StatusBadge domain="incident" value={incident.status} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
