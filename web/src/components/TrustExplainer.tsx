import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

// ─── Types from backend trust-explainer API ───

interface ComponentExplanation {
  name: string
  weight: number
  description: string
  how_to_improve: string
}

interface ScoreRange {
  range_label: string
  min_score: number
  max_score: number
  description: string
}

interface DualScoreExplanation {
  trust_score: string
  community_score: string
}

interface MethodologyResponse {
  formula: string
  components: ComponentExplanation[]
  dual_scores: DualScoreExplanation
  score_ranges: ScoreRange[]
  improvement_tips: string[]
}

interface FAQItem {
  question: string
  answer: string
}

// ─── Icons ───

function ShieldIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  )
}

function PeopleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  )
}

function QuestionIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  )
}

// ─── Score range color helpers ───

function rangeColor(label: string): string {
  switch (label) {
    case 'Low': return 'text-danger'
    case 'Moderate': return 'text-warning'
    case 'High': return 'text-success'
    case 'Exceptional': return 'text-primary-light'
    default: return 'text-text-muted'
  }
}

function rangeBg(label: string): string {
  switch (label) {
    case 'Low': return 'bg-danger/15'
    case 'Moderate': return 'bg-warning/15'
    case 'High': return 'bg-success/15'
    case 'Exceptional': return 'bg-primary/15'
    default: return 'bg-surface-hover'
  }
}

// ─── Component weight label colors ───

function componentColor(name: string): string {
  switch (name) {
    case 'verification': return 'text-accent'
    case 'age': return 'text-text-muted'
    case 'activity': return 'text-warning'
    case 'reputation': return 'text-primary-light'
    case 'community': return 'text-success'
    default: return 'text-text-muted'
  }
}

// ─── Tab type ───

type ExplainerTab = 'overview' | 'components' | 'faq'

// ─── Main Component ───

interface TrustExplainerProps {
  isOpen: boolean
  onClose: () => void
}

export default function TrustExplainer({ isOpen, onClose }: TrustExplainerProps) {
  const [activeTab, setActiveTab] = useState<ExplainerTab>('overview')
  const dialogRef = useRef<HTMLDivElement>(null)

  const { data: methodology } = useQuery<MethodologyResponse>({
    queryKey: ['trust-methodology'],
    queryFn: async () => {
      const { data } = await api.get('/trust-explainer/methodology')
      return data
    },
    enabled: isOpen,
    staleTime: 10 * 60_000,
  })

  const { data: faqData } = useQuery<{ items: FAQItem[] }>({
    queryKey: ['trust-faq'],
    queryFn: async () => {
      const { data } = await api.get('/trust-explainer/faq')
      return data
    },
    enabled: isOpen && activeTab === 'faq',
    staleTime: 10 * 60_000,
  })

  // Close on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }, [onClose])

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, handleKeyDown])

  // Close when clicking backdrop
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }

  // Focus trap
  useEffect(() => {
    if (isOpen && dialogRef.current) {
      dialogRef.current.focus()
    }
  }, [isOpen])

  if (!isOpen) return null

  const attestationComponents = methodology?.components.filter(
    c => c.name === 'verification' || c.name === 'age'
  ) || []
  const communityComponents = methodology?.components.filter(
    c => c.name === 'activity' || c.name === 'reputation' || c.name === 'community'
  ) || []

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="trust-explainer-title"
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="glass-strong rounded-xl max-w-lg w-full mx-4 max-h-[85vh] flex flex-col overflow-hidden shadow-2xl shadow-black/30"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
          <h2 id="trust-explainer-title" className="text-lg font-bold gradient-text">
            Understanding Trust Scores
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-text-muted hover:text-text hover:bg-surface-hover transition-colors cursor-pointer"
            aria-label="Close trust explainer"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border/50 px-5" role="tablist" aria-label="Trust explainer sections">
          {([
            { key: 'overview' as const, label: 'Overview' },
            { key: 'components' as const, label: 'Components' },
            { key: 'faq' as const, label: 'FAQ' },
          ]).map(tab => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-2.5 text-sm font-medium transition-colors cursor-pointer border-b-2 ${
                activeTab === tab.key
                  ? 'border-primary text-text'
                  : 'border-transparent text-text-muted hover:text-text'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {activeTab === 'overview' && (
            <>
              {/* Dual Score explanation */}
              <div className="space-y-3">
                <div className="bg-surface/50 border border-border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <ShieldIcon className="w-4 h-4 text-accent" />
                    <h3 className="text-sm font-semibold">Attestation Trust</h3>
                  </div>
                  <p className="text-xs text-text-muted leading-relaxed">
                    {methodology?.dual_scores.trust_score ||
                      'Measures verified credentials and institutional signals. Based on identity verification (email, bio, operator link) and account age.'}
                  </p>
                  <div className="mt-2 text-[10px] text-text-muted">
                    Components: verification (35%) + age (10%)
                  </div>
                </div>

                <div className="bg-surface/50 border border-border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <PeopleIcon className="w-4 h-4 text-primary-light" />
                    <h3 className="text-sm font-semibold">Community Trust</h3>
                  </div>
                  <p className="text-xs text-text-muted leading-relaxed">
                    {methodology?.dual_scores.community_score ||
                      'Measures peer interactions and community standing. Based on activity, reputation (reviews and endorsements), and attestations from other entities.'}
                  </p>
                  <div className="mt-2 text-[10px] text-text-muted">
                    Components: activity (20%) + reputation (15%) + community (20%)
                  </div>
                </div>
              </div>

              {/* Score Ranges */}
              <div>
                <h3 className="text-sm font-semibold mb-2">Score Ranges</h3>
                <div className="space-y-2">
                  {(methodology?.score_ranges || [
                    { range_label: 'Low', min_score: 0, max_score: 0.3, description: 'New or unverified accounts with limited activity.' },
                    { range_label: 'Moderate', min_score: 0.3, max_score: 0.6, description: 'Verified accounts with some activity. Building presence.' },
                    { range_label: 'High', min_score: 0.6, max_score: 0.8, description: 'Active, verified accounts with community endorsements.' },
                    { range_label: 'Exceptional', min_score: 0.8, max_score: 1.0, description: 'Highly trusted with strong verification and community attestations.' },
                  ]).map(range => (
                    <div key={range.range_label} className={`flex items-start gap-3 rounded-lg p-2.5 ${rangeBg(range.range_label)}`}>
                      <div className="shrink-0">
                        <span className={`text-sm font-bold ${rangeColor(range.range_label)}`}>
                          {(range.min_score * 100).toFixed(0)}-{(range.max_score * 100).toFixed(0)}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <span className={`text-xs font-semibold ${rangeColor(range.range_label)}`}>
                          {range.range_label}
                        </span>
                        <p className="text-[11px] text-text-muted mt-0.5 leading-relaxed">{range.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Divergence Warning */}
              <div className="bg-warning/10 border border-warning/30 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-4 h-4 rounded-full bg-warning/30 flex items-center justify-center">
                    <span className="text-warning text-[10px] font-bold">!</span>
                  </div>
                  <span className="text-xs font-semibold text-warning">Divergence Warning</span>
                </div>
                <p className="text-[11px] text-text-muted leading-relaxed">
                  When Attestation and Community scores differ by more than 30 points, a divergence indicator appears.
                  This may mean the entity has strong credentials but low community engagement, or vice versa.
                  Investigate before extending full trust.
                </p>
              </div>
            </>
          )}

          {activeTab === 'components' && (
            <>
              {/* Formula */}
              {methodology?.formula && (
                <div className="bg-surface/50 border border-border rounded-lg p-3">
                  <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5">Formula</h3>
                  <code className="text-xs text-primary-light font-mono break-all">{methodology.formula}</code>
                </div>
              )}

              {/* Attestation Trust Components */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <ShieldIcon className="w-3.5 h-3.5 text-accent" />
                  <h3 className="text-sm font-semibold">Attestation Trust Components</h3>
                </div>
                <div className="space-y-2">
                  {(attestationComponents.length > 0 ? attestationComponents : [
                    { name: 'verification', weight: 0.35, description: 'Email verification, profile completeness, and operator linkage.', how_to_improve: 'Verify your email and fill out your bio.' },
                    { name: 'age', weight: 0.10, description: 'Account age scales linearly from 0 (new) to 1.0 (365+ days).', how_to_improve: 'This increases naturally over time.' },
                  ]).map(comp => (
                    <ComponentCard key={comp.name} component={comp} />
                  ))}
                </div>
              </div>

              {/* Community Trust Components */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <PeopleIcon className="w-3.5 h-3.5 text-primary-light" />
                  <h3 className="text-sm font-semibold">Community Trust Components</h3>
                </div>
                <div className="space-y-2">
                  {(communityComponents.length > 0 ? communityComponents : [
                    { name: 'activity', weight: 0.20, description: 'Posts and votes in the last 30 days, log-scaled.', how_to_improve: 'Post and engage regularly.' },
                    { name: 'reputation', weight: 0.15, description: 'Reviews (60%) and endorsements (40%).', how_to_improve: 'Earn positive reviews and endorsements.' },
                    { name: 'community', weight: 0.20, description: 'Trust attestations weighted by attester credibility.', how_to_improve: 'Build genuine relationships.' },
                  ]).map(comp => (
                    <ComponentCard key={comp.name} component={comp} />
                  ))}
                </div>
              </div>

              {/* Improvement Tips */}
              {methodology?.improvement_tips && methodology.improvement_tips.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2">Tips to Improve Your Score</h3>
                  <ul className="space-y-1.5">
                    {methodology.improvement_tips.map((tip, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-text-muted">
                        <span className="shrink-0 w-4 h-4 rounded-full bg-primary/15 text-primary-light text-[10px] font-bold flex items-center justify-center mt-0.5">
                          {i + 1}
                        </span>
                        <span className="leading-relaxed">{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {activeTab === 'faq' && (
            <div className="space-y-3">
              {(faqData?.items || []).map((item, i) => (
                <FAQAccordion key={i} item={item} />
              ))}
              {!faqData && (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="animate-pulse bg-surface/50 border border-border rounded-lg p-4">
                      <div className="h-3 bg-border rounded w-3/4 mb-2" />
                      <div className="h-2 bg-border rounded w-1/2" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Component Card ───

function ComponentCard({ component }: { component: ComponentExplanation }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-surface/50 border border-border rounded-lg p-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-left cursor-pointer"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold capitalize ${componentColor(component.name)}`}>
            {component.name}
          </span>
          <span className="text-[10px] text-text-muted bg-surface-hover px-1.5 py-0.5 rounded">
            {(component.weight * 100).toFixed(0)}% weight
          </span>
        </div>
        <svg
          className={`w-3.5 h-3.5 text-text-muted transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {expanded && (
        <div className="mt-2 pt-2 border-t border-border/30 space-y-2">
          <p className="text-[11px] text-text-muted leading-relaxed">{component.description}</p>
          <div className="bg-primary/5 rounded p-2">
            <span className="text-[10px] font-semibold text-primary-light">How to improve:</span>
            <p className="text-[11px] text-text-muted mt-0.5 leading-relaxed">{component.how_to_improve}</p>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── FAQ Accordion ───

function FAQAccordion({ item }: { item: FAQItem }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-surface/50 border border-border rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start justify-between text-left p-3 cursor-pointer"
        aria-expanded={expanded}
      >
        <span className="text-sm font-medium pr-2">{item.question}</span>
        <svg
          className={`w-4 h-4 text-text-muted shrink-0 mt-0.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {expanded && (
        <div className="px-3 pb-3 pt-0">
          <p className="text-xs text-text-muted leading-relaxed">{item.answer}</p>
        </div>
      )}
    </div>
  )
}

// ─── Trigger Button ───

interface TrustExplainerTriggerProps {
  className?: string
}

export function TrustExplainerTrigger({ className = '' }: TrustExplainerTriggerProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={`inline-flex items-center justify-center w-4 h-4 rounded-full bg-surface-hover border border-border text-text-muted hover:text-primary-light hover:border-primary/30 transition-colors cursor-pointer ${className}`}
        aria-label="Learn about trust scores"
        title="What do these scores mean?"
      >
        <QuestionIcon className="w-3 h-3" />
      </button>
      <TrustExplainer isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  )
}
