import { Navigate, Route, Routes } from 'react-router-dom'
import { DemoDock, Toast } from './components.jsx'
import Hospitals from './pages/Hospitals.jsx'
import ParticipantHome from './pages/ParticipantHome.jsx'
import { Dashboard, Outreach, Record, Tasks, Worklist } from './pages/Programme.jsx'
import Provider from './pages/Provider.jsx'
import { Enrol, Landing, Resume, StaffLogin } from './pages/Public.jsx'
import Survey from './pages/Survey.jsx'
import { useApp } from './state.jsx'

function Guard({ role, children }) {
  const { user } = useApp()
  if (!user) return <Navigate to={role === 'participant' ? '/resume' : '/staff'} replace />
  if (user.role !== role) return <Navigate to="/" replace />
  return children
}

export default function App() {
  const { meta } = useApp()
  return (
    <>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/start" element={<Enrol />} />
        <Route path="/resume" element={<Resume />} />
        <Route path="/staff" element={<StaffLogin />} />
        <Route path="/me" element={<Guard role="participant"><ParticipantHome /></Guard>} />
        <Route path="/me/assessment" element={<Guard role="participant"><Survey /></Guard>} />
        <Route path="/me/hospitals" element={<Guard role="participant"><Hospitals /></Guard>} />
        <Route path="/provider" element={<Guard role="provider"><Provider /></Guard>} />
        <Route path="/programme" element={<Guard role="government"><Dashboard /></Guard>} />
        <Route path="/programme/worklist" element={<Guard role="government"><Worklist /></Guard>} />
        <Route path="/programme/tasks" element={<Guard role="government"><Tasks /></Guard>} />
        <Route path="/programme/outreach" element={<Guard role="government"><Outreach /></Guard>} />
        <Route path="/programme/p/:id" element={<Guard role="government"><Record /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {meta?.demo_mode !== false && <DemoDock />}
      <Toast />
    </>
  )
}
