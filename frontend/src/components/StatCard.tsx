import type { LucideIcon } from 'lucide-react'

export function StatCard({
  icon: Icon,
  value,
  label,
  tone = 'primary',
}: {
  icon: LucideIcon
  value: string | number
  label: string
  tone?: 'primary' | 'warning' | 'danger' | 'success' | 'info'
}) {
  return (
    <div className="stat-card">
      <div>
        <div className="stat-card-value">{value}</div>
        <div className="stat-card-label">{label}</div>
      </div>
      <div className={`stat-card-icon tone-${tone}`}>
        <Icon size={19} />
      </div>
    </div>
  )
}
