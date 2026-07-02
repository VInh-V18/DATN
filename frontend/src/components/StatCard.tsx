import type { LucideIcon } from 'lucide-react'
import { SkeletonBar } from './Skeleton'

export function StatCard({
  icon: Icon,
  value,
  label,
  tone = 'primary',
  loading = false,
}: {
  icon: LucideIcon
  value: string | number
  label: string
  tone?: 'primary' | 'warning' | 'danger' | 'success' | 'info'
  loading?: boolean
}) {
  return (
    <div className="stat-card">
      <div style={{ flex: 1, minWidth: 0 }}>
        {loading ? (
          <div style={{ padding: '4px 0' }}>
            <SkeletonBar width={48} height={26} />
          </div>
        ) : (
          <div className="stat-card-value">{value}</div>
        )}
        <div className="stat-card-label">{label}</div>
      </div>
      <div className={`stat-card-icon tone-${tone}`}>
        <Icon size={19} />
      </div>
    </div>
  )
}
