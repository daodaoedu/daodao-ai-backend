import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { AppShell } from '@/components/layout/AppShell'
import { LoginPage } from '@/pages/LoginPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { QueryLogsPage } from '@/pages/QueryLogsPage'
import { SystemPromptsPage } from '@/pages/SystemPromptsPage'
import { ModelManagementPage } from '@/pages/ModelManagementPage'
import { PlaygroundPage } from '@/pages/PlaygroundPage'
import { UserQuotasPage } from '@/pages/UserQuotasPage'

export function App() {
  const { isAuthenticated } = useAuth()

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell><Navigate to="/dashboard" replace /></AppShell>} path="/" />
        <Route
          path="/dashboard"
          element={<AppShell><DashboardPage /></AppShell>}
        />
        <Route
          path="/query-logs"
          element={<AppShell><QueryLogsPage /></AppShell>}
        />
        <Route
          path="/system-prompts"
          element={<AppShell><SystemPromptsPage /></AppShell>}
        />
        <Route
          path="/models"
          element={<AppShell><ModelManagementPage /></AppShell>}
        />
        <Route
          path="/user-quotas"
          element={<AppShell><UserQuotasPage /></AppShell>}
        />
        <Route
          path="/playground"
          element={<AppShell><PlaygroundPage /></AppShell>}
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
