import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { PublicRoute } from './auth/PublicRoute'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { Landing } from './pages/Landing'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { Dashboard } from './pages/Dashboard'
import { Onboarding } from './pages/Onboarding'
import { Profile } from './pages/Profile'
import { Applications } from './pages/Applications'
import { ReviewQueue } from './pages/ReviewQueue'
import { Billing } from './pages/Billing'
import { Settings } from './pages/Settings'
import { NotFound } from './pages/NotFound'

function AppRoutes() {
  return (
    <Routes>
      {/* Public — redirect to dashboard if already logged in */}
      <Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />
      <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />

      {/* Standalone protected (no sidebar layout) */}
      <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />

      {/* Protected — wrapped in sidebar Layout */}
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/applications" element={<Applications />} />
        <Route path="/review" element={<ReviewQueue />} />
        <Route path="/billing" element={<Billing />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      {/* 404 */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
