import { useEffect, useState } from 'react'
import { fetchTopology } from '../api/client'
import type { Topology } from '../api/types'

export default function TopologyPage() {
  const [topology, setTopology] = useState<Topology | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTopology().then(setTopology).catch((err) => setError(String(err)))
  }, [])

  return (
    <div className="page">
      <h1>Sơ đồ mạng (Topology)</h1>
      {error && <p className="error">Không thể tải dữ liệu: {error}</p>}
      <div className="topology-grid">
        {topology?.devices.map((device) => (
          <div key={device.id} className={`device-node role-${device.role}`}>
            <strong>{device.name}</strong>
            <div className="device-meta">
              {device.node_type} · {device.management_address ?? 'chưa có IP quản lý'}
            </div>
            <ul className="interface-list">
              {device.interfaces.map((iface) => (
                <li key={iface.id} className={`iface-status-${iface.status}`}>
                  {iface.name}: {iface.status} {iface.ip_address ? `(${iface.ip_address})` : ''}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {topology && topology.devices.length === 0 && <p>Chưa có thiết bị nào được đăng ký.</p>}
      </div>

      <h2>Liên kết</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Cổng A</th>
            <th>Cổng B</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {topology?.links.map((link) => (
            <tr key={link.id}>
              <td>{link.port_a_id}</td>
              <td>{link.port_b_id}</td>
              <td>
                <span className={`badge status-${link.status}`}>{link.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
