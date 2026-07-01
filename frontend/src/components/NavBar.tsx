import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Tổng quan' },
  { to: '/topology', label: 'Topology' },
  { to: '/incidents', label: 'Sự cố' },
  { to: '/security', label: 'An ninh' },
  { to: '/chat', label: 'Copilot' },
]

export default function NavBar() {
  return (
    <nav className="navbar">
      <div className="navbar-brand">AI Agent GNS3</div>
      <div className="navbar-links">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
