import { Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar'
import Dashboard from './pages/Dashboard'
import TopologyPage from './pages/Topology'
import IncidentsPage from './pages/Incidents'
import SecurityPage from './pages/Security'
import ChatPage from './pages/Chat'

function App() {
  return (
    <div className="app-shell">
      <NavBar />
      <main className="app-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
