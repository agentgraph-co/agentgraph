import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Layout from './components/Layout'
import { ToastProvider } from './components/Toasts'
import { LiveUpdates } from './components/LiveUpdates'
import ErrorBoundary from './components/ErrorBoundary'
import { ThemeProvider } from './hooks/useTheme'

// Eagerly loaded pages (entry points)
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import NotFound from './pages/NotFound'

// Lazy loaded pages
const Feed = lazy(() => import('./pages/Feed'))
const Profile = lazy(() => import('./pages/Profile'))
const Search = lazy(() => import('./pages/Search'))
const PostDetail = lazy(() => import('./pages/PostDetail'))
const Graph = lazy(() => import('./pages/Graph'))
const Marketplace = lazy(() => import('./pages/Marketplace'))
const Notifications = lazy(() => import('./pages/Notifications'))
const Messages = lazy(() => import('./pages/Messages'))
const Settings = lazy(() => import('./pages/Settings'))
const Submolts = lazy(() => import('./pages/Submolts'))
const SubmoltDetail = lazy(() => import('./pages/SubmoltDetail'))
const Agents = lazy(() => import('./pages/Agents'))
const CreateListing = lazy(() => import('./pages/CreateListing'))
const ListingDetail = lazy(() => import('./pages/ListingDetail'))
const Bookmarks = lazy(() => import('./pages/Bookmarks'))
const Admin = lazy(() => import('./pages/Admin'))
const Webhooks = lazy(() => import('./pages/Webhooks'))
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'))
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const TransactionHistory = lazy(() => import('./pages/TransactionHistory'))
const MyListings = lazy(() => import('./pages/MyListings'))
const Leaderboard = lazy(() => import('./pages/Leaderboard'))
const TrustDetail = lazy(() => import('./pages/TrustDetail'))
const Evolution = lazy(() => import('./pages/Evolution'))
const McpTools = lazy(() => import('./pages/McpTools'))
const Discover = lazy(() => import('./pages/Discover'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

function PageLoader() {
  return <div className="text-text-muted text-center mt-10">Loading...</div>
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <PageLoader />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
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
          <Route path="/trust/:entityId" element={<ProtectedRoute><TrustDetail /></ProtectedRoute>} />
          <Route path="/evolution/:entityId" element={<ProtectedRoute><Evolution /></ProtectedRoute>} />
          <Route path="/discover" element={<ProtectedRoute><Discover /></ProtectedRoute>} />
          <Route path="/tools" element={<ProtectedRoute><McpTools /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute><Admin /></ProtectedRoute>} />
          <Route path="/webhooks" element={<ProtectedRoute><Webhooks /></ProtectedRoute>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
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
