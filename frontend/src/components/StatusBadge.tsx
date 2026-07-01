import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Clock,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  ShieldQuestion,
  XCircle,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

type Tone = 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'neutral'

interface Meta {
  label: string
  tone: Tone
  icon: LucideIcon
}

const INCIDENT_META: Record<string, Meta> = {
  open: { label: 'Mới phát hiện', tone: 'info', icon: AlertTriangle },
  diagnosing: { label: 'Đang chẩn đoán', tone: 'info', icon: Loader2 },
  awaiting_approval: { label: 'Chờ phê duyệt', tone: 'warning', icon: Clock },
  remediating: { label: 'Đang khắc phục', tone: 'primary', icon: Loader2 },
  resolved: { label: 'Đã khắc phục', tone: 'success', icon: CheckCircle2 },
  failed: { label: 'Thất bại', tone: 'danger', icon: XCircle },
  guardrail_blocked: { label: 'Bị chặn (guardrail)', tone: 'danger', icon: ShieldOff },
}

const SECURITY_META: Record<string, Meta> = {
  detected: { label: 'Đã phát hiện', tone: 'info', icon: ShieldQuestion },
  alert_only: { label: 'Chỉ cảnh báo', tone: 'neutral', icon: ShieldQuestion },
  awaiting_approval: { label: 'Chờ phê duyệt', tone: 'warning', icon: Clock },
  blocked: { label: 'Đã chặn', tone: 'success', icon: ShieldCheck },
  rejected: { label: 'Đã từ chối', tone: 'neutral', icon: CircleSlash },
  response_failed: { label: 'Phản ứng thất bại', tone: 'danger', icon: ShieldAlert },
}

const SEVERITY_META: Record<string, Meta> = {
  info: { label: 'info', tone: 'info', icon: ShieldQuestion },
  low: { label: 'thấp', tone: 'info', icon: ShieldQuestion },
  medium: { label: 'trung bình', tone: 'warning', icon: ShieldAlert },
  high: { label: 'cao', tone: 'danger', icon: ShieldAlert },
  critical: { label: 'nghiêm trọng', tone: 'danger', icon: ShieldOff },
}

const LINK_META: Record<string, Meta> = {
  up: { label: 'Up', tone: 'success', icon: CheckCircle2 },
  down: { label: 'Down', tone: 'danger', icon: XCircle },
  flapping: { label: 'Chập chờn', tone: 'warning', icon: AlertTriangle },
}

const DOMAINS = {
  incident: INCIDENT_META,
  security: SECURITY_META,
  severity: SEVERITY_META,
  link: LINK_META,
} as const

export function StatusBadge({
  domain,
  value,
}: {
  domain: keyof typeof DOMAINS
  value: string
}): ReactNode {
  const meta = DOMAINS[domain][value] ?? { label: value, tone: 'neutral' as Tone, icon: ShieldQuestion }
  const Icon = meta.icon
  const spin = value === 'diagnosing' || value === 'remediating'
  return (
    <span className={`badge tone-${meta.tone}`}>
      <Icon size={12} className={spin ? 'spin' : undefined} />
      {meta.label}
    </span>
  )
}
