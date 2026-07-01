import { LayoutDashboard, MessageCircle, Network, ShieldAlert, Siren } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useConnectionStatus } from '../hooks/useLiveEvents'

const links = [
  { to: '/', label: 'Tổng quan', icon: LayoutDashboard },
  { to: '/topology', label: 'Topology', icon: Network },
  { to: '/incidents', label: 'Sự cố', icon: Siren },
  { to: '/security', label: 'An ninh', icon: ShieldAlert },
  { to: '/chat', label: 'Copilot', icon: MessageCircle },
]

export default function Sidebar() {
  const connected = useConnectionStatus()

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">
          <Network size={18} />
        </div>
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-title">AI Agent GNS3</span>
          <span className="sidebar-brand-subtitle">Vận hành &amp; an ninh mạng</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => (isActive ? 'sidebar-link active' : 'sidebar-link')}
          >
            <Icon size={17} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className={`ws-dot${connected ? ' online' : ''}`} />
        {connected ? 'Realtime đang hoạt động' : 'Mất kết nối realtime'}
      </div>
    </aside>
  )
}
