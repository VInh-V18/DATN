import { useEffect, useState } from 'react'
import { approveSecurityAlert, fetchSecurityAlerts } from '../api/client'
import type { SecurityAlert } from '../api/types'

export default function SecurityPage() {
  const [alerts, setAlerts] = useState<SecurityAlert[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = () => fetchSecurityAlerts().then(setAlerts).catch((err) => setError(String(err)))

  useEffect(() => {
    load()
  }, [])

  const handleApproval = async (alert: SecurityAlert, approved: boolean) => {
    await approveSecurityAlert(alert.id, approved)
    await load()
  }

  return (
    <div className="page">
      <h1>Cảnh báo an ninh &amp; ánh xạ MITRE ATT&amp;CK</h1>
      {error && <p className="error">Không thể tải dữ liệu: {error}</p>}
      <table className="data-table">
        <thead>
          <tr>
            <th>Thời gian</th>
            <th>IP nguồn</th>
            <th>Loại tấn công</th>
            <th>Kỹ thuật ATT&amp;CK</th>
            <th>Mức độ</th>
            <th>Trạng thái</th>
            <th>Hành động</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td>{new Date(alert.timestamp).toLocaleString('vi-VN')}</td>
              <td>{alert.source_ip}</td>
              <td>{alert.attack_type}</td>
              <td>{alert.attack_techniques.join(', ') || '—'}</td>
              <td>
                <span className={`badge severity-${alert.severity}`}>{alert.severity}</span>
              </td>
              <td>
                <span className={`badge status-${alert.status}`}>{alert.status}</span>
              </td>
              <td>
                {alert.status === 'awaiting_approval' && (
                  <>
                    <button onClick={() => handleApproval(alert, true)}>Phê duyệt chặn</button>
                    <button onClick={() => handleApproval(alert, false)}>Từ chối</button>
                  </>
                )}
              </td>
            </tr>
          ))}
          {alerts.length === 0 && (
            <tr>
              <td colSpan={7}>Chưa phát hiện cảnh báo an ninh nào.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
