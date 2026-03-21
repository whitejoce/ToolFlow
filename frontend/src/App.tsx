import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './AppShell'
import ToolsPage from './pages/ToolsPage'
import ExecutionsPage from './pages/ExecutionsPage'
import MetricsPage from './pages/MetricsPage'
import SettingsPage from './pages/SettingsPage'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/executions" element={<ExecutionsPage />} />
        <Route path="/metrics" element={<MetricsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/tools" replace />} />
    </Routes>
  )
}

export default App
