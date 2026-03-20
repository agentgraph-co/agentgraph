import { useState, useEffect, lazy, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { InlineSkeleton } from '../components/Skeleton'
import type { Tab, PlatformStats } from './admin/types'

const OverviewTab = lazy(() => import('./admin/OverviewTab'))
const UsersTab = lazy(() => import('./admin/UsersTab'))
const ModerationTab = lazy(() => import('./admin/ModerationTab'))
const AppealsTab = lazy(() => import('./admin/AppealsTab'))
const AuditTab = lazy(() => import('./admin/AuditTab'))
const GrowthTab = lazy(() => import('./admin/GrowthTab'))
const ConversionTab = lazy(() => import('./admin/ConversionTab'))
const AttributionTab = lazy(() => import('./admin/AttributionTab'))
const WaitlistTab = lazy(() => import('./admin/WaitlistTab'))
const TrustTab = lazy(() => import('./admin/TrustTab'))
const SafetyTab = lazy(() => import('./admin/SafetyTab'))
const InfraTab = lazy(() => import('./admin/InfraTab'))
const IssuesTab = lazy(() => import('./admin/IssuesTab'))
const ClaimsTab = lazy(() => import('./admin/ClaimsTab'))
const MarketingTab = lazy(() => import('./admin/MarketingTab'))

export default function Admin() {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => { document.title = 'Admin - AgentGraph' }, [])

  // Fetch stats at the top level so the moderation badge on the tab bar works
  const { data: stats } = useQuery<PlatformStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const { data } = await api.get('/admin/stats')
      return data
    },
    staleTime: 2 * 60_000,
  })

  if (!user?.is_admin) {
    return (
      <div className="text-danger text-center mt-10">
        Admin access required
      </div>
    )
  }

  const tabs: { value: Tab; label: string }[] = [
    { value: 'overview', label: 'Overview' },
    { value: 'users', label: 'Users' },
    { value: 'moderation', label: 'Moderation' },
    { value: 'appeals', label: 'Appeals' },
    { value: 'audit', label: 'Audit Log' },
    { value: 'growth', label: 'Growth' },
    { value: 'conversion', label: 'Conversion' },
    { value: 'attribution', label: 'Attribution' },
    { value: 'waitlist', label: 'Waitlist' },
    { value: 'trust', label: 'Trust' },
    { value: 'safety', label: 'Safety' },
    { value: 'infra', label: 'Infra' },
    { value: 'issues', label: 'Issues' },
    { value: 'claims', label: 'Claims' },
    { value: 'marketing', label: 'Marketing' },
  ]

  const tabContent: Record<Tab, React.ReactNode> = {
    overview: <OverviewTab />,
    users: <UsersTab />,
    moderation: <ModerationTab />,
    appeals: <AppealsTab />,
    audit: <AuditTab />,
    growth: <GrowthTab />,
    conversion: <ConversionTab />,
    attribution: <AttributionTab />,
    waitlist: <WaitlistTab />,
    trust: <TrustTab />,
    safety: <SafetyTab />,
    infra: <InfraTab />,
    issues: <IssuesTab />,
    claims: <ClaimsTab />,
    marketing: <MarketingTab />,
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Admin Dashboard</h1>

      <div className="flex flex-wrap gap-1 mb-6 border-b border-border" role="tablist" aria-label="Admin sections">
        {tabs.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`px-4 py-2 text-sm transition-colors cursor-pointer border-b-2 -mb-px ${
              tab === t.value
                ? 'border-primary text-primary-light'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {t.label}
            {t.value === 'moderation' && stats && stats.pending_moderation_flags > 0 && (
              <span className="ml-1.5 text-[10px] bg-danger text-white px-1.5 py-0.5 rounded-full">
                {stats.pending_moderation_flags}
              </span>
            )}
          </button>
        ))}
      </div>

      <Suspense fallback={<div className="py-10"><InlineSkeleton /></div>}>
        {tabContent[tab]}
      </Suspense>
    </div>
  )
}
