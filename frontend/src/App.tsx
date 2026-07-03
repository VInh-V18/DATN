import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import TopologyPage from './pages/Topology'
import IncidentsPage from './pages/Incidents'
import SecurityPage from './pages/Security'
import ActivityPage from './pages/Activity'
import ChatPage from './pages/Chat'

function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
