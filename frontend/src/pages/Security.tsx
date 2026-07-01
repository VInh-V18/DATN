import { useEffect, useState } from 'react'
import { CheckCircle2, ShieldAlert, XCircle } from 'lucide-react'
import { approveSecurityAlert, fetchSecurityAlerts } from '../api/client'
import type { SecurityAlert } from '../api/types'
import { useLiveEvents } from '../hooks/useLiveEvents'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'

const RELEVANT_EVENTS = new Set(['security_alert_created', 'security_alert_updated'])

export default function SecurityPage() {
  const [alerts, setAlerts] = useState<SecurityAlert[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () =>
    fetchSecurityAlerts()
      .then(setAlerts)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))

  useEffect(() => {
    load()
  }, [])

  useLiveEvents((event) => {
    if (RELEVANT_EVENTS.has(event.type)) load()
  })

  const handleApproval = async (alert: SecurityAlert, approved: boolean) => {
    await approveSecurityAlert(alert.id, approved)
    await load()
  }

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>Cảnh báo an ninh &amp; ánh xạ MITRE ATT&amp;CK</h1>
          <p>Phát hiện tấn công theo luật, ánh xạ kỹ thuật ATT&amp;CK và phản ứng tự động có phê duyệt.</p>
        </div>
      </div>

      {error && <div className="error-banner">Không thể tải dữ liệu: {error}</div>}

      <div className="table-wrap">
        {alerts.length === 0 && !loading ? (
          <EmptyState
            icon={ShieldAlert}
            title="Chưa phát hiện cảnh báo an ninh nào"
            subtitle="Cảnh báo sẽ xuất hiện khi phát hiện quét cổng, SYN flood hoặc dò mật khẩu SSH."
          />
        ) : (
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
                  <td className="cell-muted">{new Date(alert.timestamp).toLocaleString('vi-VN')}</td>
                  <td className="cell-mono">{alert.source_ip}</td>
                  <td>{alert.attack_type}</td>
                  <td>
                    {alert.attack_techniques.length > 0 ? (
                      <div className="btn-row" style={{ flexWrap: 'wrap' }}>
                        {alert.attack_techniques.map((t) => (
                          <span key={t} className="chip">
                            {t}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="cell-muted">—</span>
                    )}
                  </td>
                  <td>
                    <StatusBadge domain="severity" value={alert.severity} />
                  </td>
                  <td>
                    <StatusBadge domain="security" value={alert.status} />
                  </td>
                  <td>
                    {alert.status === 'awaiting_approval' && (
                      <div className="btn-row">
                        <button className="btn btn-sm" onClick={() => handleApproval(alert, true)}>
                          <CheckCircle2 size={13} />
                          Duyệt chặn
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => handleApproval(alert, false)}>
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
    </div>
  )
}
