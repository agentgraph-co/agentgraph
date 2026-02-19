import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Layout from './components/Layout'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Feed from './pages/Feed'
import Profile from './pages/Profile'
import Search from './pages/Search'
import PostDetail from './pages/PostDetail'
import Graph from './pages/Graph'
import Marketplace from './pages/Marketplace'
import Notifications from './pages/Notifications'
import Messages from './pages/Messages'
import Settings from './pages/Settings'
import Submolts from './pages/Submolts'
import SubmoltDetail from './pages/SubmoltDetail'
import Agents from './pages/Agents'
import CreateListing from './pages/CreateListing'
import ListingDetail from './pages/ListingDetail'
import { ToastProvider } from './components/Toasts'
import { LiveUpdates } from './components/LiveUpdates'
import ErrorBoundary from './components/ErrorBoundary'
import NotFound from './pages/NotFound'
import { ThemeProvider } from './hooks/useTheme'
import Bookmarks from './pages/Bookmarks'
import Admin from './pages/Admin'
import Webhooks from './pages/Webhooks'
import VerifyEmail from './pages/VerifyEmail'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import TransactionHistory from './pages/TransactionHistory'
import MyListings from './pages/MyListings'
import Leaderboard from './pages/Leaderboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <div className="text-text-muted text-center mt-10">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/feed" element={<ProtectedRoute><Feed /></ProtectedRoute>} />
        <Route path="/post/:postId" element={<ProtectedRoute><PostDetail /></ProtectedRoute>} />
        <Route path="/profile/:entityId" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route path="/search" element={<ProtectedRoute><Search /></ProtectedRoute>} />
        <Route path="/graph" element={<ProtectedRoute><Graph /></ProtectedRoute>} />
        <Route path="/marketplace" element={<ProtectedRoute><Marketplace /></ProtectedRoute>} />
        <Route path="/marketplace/create" element={<ProtectedRoute><CreateListing /></ProtectedRoute>} />
        <Route path="/marketplace/:listingId" element={<ProtectedRoute><ListingDetail /></ProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
        <Route path="/messages" element={<ProtectedRoute><Messages /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/communities" element={<ProtectedRoute><Submolts /></ProtectedRoute>} />
        <Route path="/m/:name" element={<ProtectedRoute><SubmoltDetail /></ProtectedRoute>} />
        <Route path="/agents" element={<ProtectedRoute><Agents /></ProtectedRoute>} />
        <Route path="/bookmarks" element={<ProtectedRoute><Bookmarks /></ProtectedRoute>} />
        <Route path="/transactions" element={<ProtectedRoute><TransactionHistory /></ProtectedRoute>} />
        <Route path="/my-listings" element={<ProtectedRoute><MyListings /></ProtectedRoute>} />
        <Route path="/leaderboard" element={<ProtectedRoute><Leaderboard /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute><Admin /></ProtectedRoute>} />
        <Route path="/webhooks" element={<ProtectedRoute><Webhooks /></ProtectedRoute>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <ToastProvider>
              <ErrorBoundary>
                <LiveUpdates />
                <AppRoutes />
              </ErrorBoundary>
            </ToastProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
