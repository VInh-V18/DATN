import { useCallback, useEffect, useState } from 'react'
import { Cpu, GitBranch, Monitor, Network, Router, Server, Skull, Waypoints } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { fetchTopology } from '../api/client'
import type { Topology } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'

const ROLE_ICON: Record<string, LucideIcon> = {
  router: Router,
  switch: Waypoints,
  host: Monitor,
  iot: Cpu,
  server: Server,
  attacker: Skull,
}

export default function TopologyPage() {
  const [topology, setTopology] = useState<Topology | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    fetchTopology()
      .then(setTopology)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(reload, [reload])

  useLiveEvents((event) => {
    if (event.type === 'topology_updated') reload()
  })

  const portLabel = (interfaceId: string): string => {
    for (const device of topology?.devices ?? []) {
      const iface = device.interfaces.find((i) => i.id === interfaceId)
      if (iface) return `${device.name} / ${iface.name}`
    }
    return interfaceId
  }

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>Sơ đồ mạng (Topology)</h1>
          <p>Thiết bị, cổng và liên kết được đồng bộ trực tiếp từ GNS3 và thiết bị thật.</p>
        </div>
      </div>

      {error && <div className="error-banner">Không thể tải dữ liệu: {error}</div>}

      {!loading && topology?.devices.length === 0 ? (
        <div className="table-wrap">
          <EmptyState
            icon={Network}
            title="Chưa có thiết bị nào được đăng ký"
            subtitle="Chạy scripts/gns3_lab.py seed-db để đồng bộ topology từ GNS3."
          />
        </div>
      ) : (
        <div className="topology-grid">
          {topology?.devices.map((device) => {
            const Icon = ROLE_ICON[device.role] ?? Server
            return (
              <div key={device.id} className={`device-node role-${device.role}`}>
                <div className="device-node-head">
                  <div className="device-node-icon">
                    <Icon size={17} />
                  </div>
                  <div>
                    <div className="device-node-name">{device.name}</div>
                    <div className="device-node-role">{device.role}</div>
                  </div>
                </div>
                <div className="device-meta">
                  {device.node_type} · {device.management_address ?? 'chưa có IP quản lý'}
                </div>
                <ul className="interface-list">
                  {device.interfaces.map((iface) => (
                    <li key={iface.id} className="interface-row">
                      <span>
                        <span className={`iface-dot ${iface.status}`} />
                        {iface.name}
                      </span>
                      <span>{iface.ip_address ?? iface.status}</span>
                    </li>
                  ))}
                  {device.interfaces.length === 0 && <li className="interface-row">Không có cổng</li>}
                </ul>
              </div>
            )
          })}
        </div>
      )}

      <div className="section-title">
        <GitBranch size={16} />
        Liên kết
      </div>
      <div className="table-wrap">
        {!topology || topology.links.length === 0 ? (
          <EmptyState icon={GitBranch} title="Chưa có liên kết nào" />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Cổng A</th>
                <th>Cổng B</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {topology.links.map((link) => (
                <tr key={link.id}>
                  <td className="chip">{portLabel(link.port_a_id)}</td>
                  <td className="chip">{portLabel(link.port_b_id)}</td>
                  <td>
                    <StatusBadge domain="link" value={link.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
