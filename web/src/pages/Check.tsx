/**
 * Check — "Is This Agent Safe?" web checker page.
 *
 * The #1 consumer-facing page. One search bar that accepts bot names,
 * GitHub URLs, package names, or MCP server names. Routes to a result
 * page with a giant letter grade and plain-English safety summary.
 *
 * URL patterns:
 *   /check              — search bar landing
 *   /check/:owner/:repo — direct result (shareable URL)
 */

import { useState, useEffect, useRef, type FormEvent } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import SEOHead from '../components/SEOHead'
import { PageTransition } from '../components/Motion'
import { scoreToGrade, getGradeInfo } from '../components/trust/gradeSystem'
import GradeCard from '../components/check/GradeCard'
import SafetySummary from '../components/check/SafetySummary'
import FindingsPanel from '../components/check/FindingsPanel'
import ShareCard from '../components/check/ShareCard'
import { Pulse } from '../components/Skeleton'

// ─── Types ───

interface ScanFinding {
  severity: string
  category: string
  description: string
  file_path?: string
  line?: number
  remediation?: string
}

interface CategoryScore {
  name: string
  score: number
  finding_count: number
}

interface ScanResult {
  owner: string
  repo: string
  overall_score: number
  grade: string
  total_findings: number
  critical_findings: number
  high_findings: number
  medium_findings: number
  low_findings: number
  categories: CategoryScore[]
  top_findings: ScanFinding[]
  scanned_at: string
  cached: boolean
  provider_count?: number
}

interface SearchEntity {
  id: string
  type: string
  display_name: string
  bio_markdown: string
  trust_score: number | null
  source_url?: string
}

// ─── Input Parsing ───

interface ParsedInput {
  type: 'github_url' | 'owner_repo' | 'search'
  owner?: string
  repo?: string
  query?: string
}

function parseInput(raw: string): ParsedInput {
  const trimmed = raw.trim()

  // GitHub URL: https://github.com/owner/repo or github.com/owner/repo
  const ghUrlMatch = trimmed.match(
    /(?:https?:\/\/)?github\.com\/([a-zA-Z0-9._-]+)\/([a-zA-Z0-9._-]+)/
  )
  if (ghUrlMatch) {
    return { type: 'github_url', owner: ghUrlMatch[1], repo: ghUrlMatch[2] }
  }

  // owner/repo pattern (no spaces, has a slash)
  const ownerRepoMatch = trimmed.match(/^([a-zA-Z0-9._-]+)\/([a-zA-Z0-9._-]+)$/)
  if (ownerRepoMatch) {
    return { type: 'owner_repo', owner: ownerRepoMatch[1], repo: ownerRepoMatch[2] }
  }

  // Anything else is a name/search query
  return { type: 'search', query: trimmed }
}

// ─── API client (public, no auth needed) ───

const publicApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000, // scans can take a while
})

// ─── Trust Dimensions (consumer-friendly icons) ───

function TrustDimensions({ scanResult }: { scanResult: ScanResult }) {
  const score = scanResult.overall_score
  const hasIdentity = false // Scan-only results don't have identity data yet
  const hasCommunity = false // Same — no community data from scanner

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {/* Identity */}
      <div className="bg-surface border border-border rounded-lg p-3 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-surface-2 flex items-center justify-center">
          <svg className="w-5 h-5 text-text-muted" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M16.403 12.652a3 3 0 000-5.304 3 3 0 00-3.75-3.751 3 3 0 00-5.305 0 3 3 0 00-3.751 3.75 3 3 0 000 5.305 3 3 0 003.75 3.751 3 3 0 005.305 0 3 3 0 003.751-3.75zm-2.546-4.46a.75.75 0 00-1.214-.883l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-medium text-text-primary">Identity</p>
          <p className="text-xs text-text-muted">
            {hasIdentity ? 'Verified' : 'Not yet claimed'}
          </p>
        </div>
      </div>

      {/* Code Security */}
      <div className="bg-surface border border-border rounded-lg p-3 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${getGradeInfo(score).color}15` }}>
          <span className="font-bold text-sm" style={{ color: getGradeInfo(score).color }}>
            {scoreToGrade(score)}
          </span>
        </div>
        <div>
          <p className="text-sm font-medium text-text-primary">Code Security</p>
          <p className="text-xs text-text-muted">
            {score >= 81 ? 'Strong' : score >= 61 ? 'Good' : score >= 41 ? 'Fair' : 'Needs work'}
          </p>
        </div>
      </div>

      {/* Community Trust */}
      <div className="bg-surface border border-border rounded-lg p-3 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-surface-2 flex items-center justify-center">
          <svg className="w-5 h-5 text-text-muted" viewBox="0 0 20 20" fill="currentColor">
            <path d="M7 8a3 3 0 100-6 3 3 0 000 6zM14.5 9a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM1.615 16.428a1.224 1.224 0 01-.569-1.175 6.002 6.002 0 0111.908 0c.058.467-.172.92-.57 1.174A9.953 9.953 0 017 18a9.953 9.953 0 01-5.385-1.572zM14.5 16h-.106c.07-.297.088-.611.048-.933a7.47 7.47 0 00-1.588-3.755 4.502 4.502 0 015.874 2.636.818.818 0 01-.36.98A7.465 7.465 0 0114.5 16z" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-medium text-text-primary">Community</p>
          <p className="text-xs text-text-muted">
            {hasCommunity ? 'Peer reviewed' : 'No reviews yet'}
          </p>
        </div>
      </div>
    </div>
  )
}

// ─── Scan Loading Skeleton ───

function ScanSkeleton() {
  return (
    <div className="max-w-2xl mx-auto space-y-6 mt-8">
      <div className="flex flex-col items-center gap-4">
        <Pulse className="w-36 h-36 rounded-2xl" />
        <Pulse className="w-20 h-8" />
        <Pulse className="w-32 h-4" />
      </div>
      <Pulse className="w-full h-24 rounded-lg" />
      <div className="grid grid-cols-3 gap-3">
        <Pulse className="h-16 rounded-lg" />
        <Pulse className="h-16 rounded-lg" />
        <Pulse className="h-16 rounded-lg" />
      </div>
    </div>
  )
}

// ─── Search Results (when user types a name instead of URL) ───

function SearchResults({ query }: { query: string }) {
  const { data, isLoading, isError } = useQuery<{ entities: SearchEntity[] }>({
    queryKey: ['check-search', query],
    queryFn: async () => {
      const { data } = await publicApi.get('/search', { params: { q: query, type: 'agent' } })
      return data
    },
    enabled: !!query,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="space-y-2 mt-6">
        {[1, 2, 3].map(i => <Pulse key={i} className="w-full h-16 rounded-lg" />)}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-center py-10 text-text-muted">
        Search failed. Please try again.
      </div>
    )
  }

  if (!data || data.entities.length === 0) {
    return (
      <div className="text-center py-10">
        <p className="text-text-muted mb-2">No agents found for "{query}"</p>
        <p className="text-xs text-text-muted">
          Try a GitHub URL like <span className="font-mono text-primary-light">github.com/owner/repo</span> for a direct scan.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2 mt-6">
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">
        Search Results
      </h2>
      {data.entities.map((entity) => (
        <Link
          key={entity.id}
          to={`/profile/${entity.id}`}
          className="block bg-surface border border-border rounded-lg p-3 hover:border-primary/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="font-medium text-text-primary">{entity.display_name}</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-blue-400/20 text-blue-400">
              {entity.type}
            </span>
            {entity.trust_score != null && (
              <span className="ml-auto">
                <span
                  className={`inline-flex items-center gap-1 font-semibold text-xs px-1.5 py-0.5 rounded-md ${getGradeInfo(Math.round(entity.trust_score <= 1 ? entity.trust_score * 100 : entity.trust_score)).bgClass}`}
                  style={{ color: getGradeInfo(Math.round(entity.trust_score <= 1 ? entity.trust_score * 100 : entity.trust_score)).color }}
                >
                  {scoreToGrade(Math.round(entity.trust_score <= 1 ? entity.trust_score * 100 : entity.trust_score))}
                </span>
              </span>
            )}
          </div>
          {entity.bio_markdown && (
            <p className="text-xs text-text-muted mt-1 line-clamp-2">{entity.bio_markdown}</p>
          )}
        </Link>
      ))}
    </div>
  )
}

// ─── Scan Result View ───

function ScanResultView({ owner, repo }: { owner: string; repo: string }) {
  const { data: scan, isLoading, isError, error } = useQuery<ScanResult>({
    queryKey: ['public-scan', owner, repo],
    queryFn: async () => {
      const { data } = await publicApi.get(`/public/scan/${owner}/${repo}`)
      // Map API response fields to component interface
      const findings = data.findings || {}
      const catScores = data.category_scores || {}
      return {
        ...data,
        overall_score: data.trust_score ?? data.security_score ?? 0,
        grade: scoreToGrade(data.trust_score ?? data.security_score ?? 0),
        total_findings: findings.total ?? 0,
        critical_findings: findings.critical ?? 0,
        high_findings: findings.high ?? 0,
        medium_findings: findings.medium ?? 0,
        low_findings: findings.low ?? 0,
        categories: Object.entries(catScores).map(([name, score]) => ({
          name,
          score: score as number,
          finding_count: 0,
        })),
        top_findings: [],
        provider_count: 1,
      } as ScanResult
    },
    staleTime: 5 * 60_000,
    retry: 1,
  })

  if (isLoading) return <ScanSkeleton />

  if (isError) {
    const status = axios.isAxiosError(error) ? error.response?.status : null
    return (
      <div className="text-center py-10">
        <div className="w-16 h-16 mx-auto mb-4 rounded-xl bg-surface-2 flex items-center justify-center">
          <svg className="w-8 h-8 text-text-muted" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
        </div>
        <h2 className="text-lg font-bold text-text-primary mb-2">
          {status === 404 ? 'Repository Not Found' : 'Scan Failed'}
        </h2>
        <p className="text-sm text-text-muted mb-4">
          {status === 404
            ? `Could not find ${owner}/${repo}. Make sure the repository exists and is public.`
            : 'Something went wrong while scanning this repository. Please try again.'}
        </p>
        <Link
          to="/check"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary hover:bg-primary-dark text-white text-sm transition-colors"
        >
          Try another search
        </Link>
      </div>
    )
  }

  if (!scan) return null

  const score = Math.round(scan.overall_score)
  const grade = scoreToGrade(score)
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const badgeUrl = `${window.location.origin}${baseUrl}/public/scan/${owner}/${repo}/badge`
  const checkUrl = `https://agentgraph.co/check/${owner}/${repo}`

  return (
    <>
      <SEOHead
        title={`Is ${owner}/${repo} Safe? Trust Score: ${grade} (${score}/100)`}
        description={`Security scan results for ${owner}/${repo}. Grade: ${grade} (${score}/100). ${scan.total_findings} findings detected. Verified by AgentGraph.`}
        path={`/check/${owner}/${repo}`}
        jsonLd={{
          '@context': 'https://schema.org',
          '@type': 'Review',
          name: `Is This Agent Safe?: ${owner}/${repo}`,
          reviewBody: `Trust Score: ${grade} (${score}/100). ${scan.total_findings} security findings.`,
          itemReviewed: {
            '@type': 'SoftwareApplication',
            name: repo,
            url: `https://github.com/${owner}/${repo}`,
          },
          reviewRating: {
            '@type': 'Rating',
            ratingValue: score,
            bestRating: 100,
            worstRating: 0,
          },
          author: {
            '@type': 'Organization',
            name: 'AgentGraph',
            url: 'https://agentgraph.co',
          },
        }}
      />

      <div className="space-y-6">
        {/* Giant Grade */}
        <GradeCard grade={grade} score={score} repoName={`${owner}/${repo}`} />

        {/* Safety Verdict */}
        <SafetySummary
          grade={grade}
          totalFindings={scan.total_findings}
          criticalFindings={scan.critical_findings}
          providerCount={scan.provider_count ?? 1}
        />

        {/* Three Trust Dimensions */}
        <TrustDimensions scanResult={scan} />

        {/* Developer Details (expandable) */}
        <FindingsPanel
          categories={scan.categories ?? []}
          findings={scan.top_findings ?? []}
          owner={owner}
          repo={repo}
          badgeUrl={badgeUrl}
          checkUrl={checkUrl}
        />

        {/* Share + CTAs */}
        <ShareCard owner={owner} repo={repo} grade={grade} score={score} />

        {/* Scan metadata */}
        <div className="text-center text-xs text-text-muted pb-4">
          Scanned {scan.cached ? '(cached)' : ''} {new Date(scan.scanned_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}
          {' '}by AgentGraph Security Scanner
        </div>
      </div>
    </>
  )
}

// ─── Main Check Page ───

export default function Check() {
  const { owner, repo } = useParams<{ owner: string; repo: string }>()
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const hasResult = !!(owner && repo)

  useEffect(() => {
    if (!hasResult && inputRef.current) {
      inputRef.current.focus()
    }
  }, [hasResult])

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return

    const parsed = parseInput(input)

    if (parsed.type === 'github_url' || parsed.type === 'owner_repo') {
      navigate(`/check/${parsed.owner}/${parsed.repo}`)
      setInput('')
      setSearchQuery('')
    } else {
      setSearchQuery(parsed.query ?? '')
    }
  }

  return (
    <PageTransition className="max-w-2xl mx-auto px-4">
      {!hasResult && (
        <SEOHead
          title="Is This Agent Safe? — Free AI Agent Security Checker"
          description="Check the security posture of any AI agent, MCP server, or OpenClaw skill. Instant trust grades, findings breakdown, and safety verdicts. No signup required."
          path="/check"
          jsonLd={{
            '@context': 'https://schema.org',
            '@type': 'WebApplication',
            name: 'AgentGraph Safety Checker',
            url: 'https://agentgraph.co/check',
            applicationCategory: 'SecurityApplication',
            description: 'Check the security posture of any AI agent, MCP server, or OpenClaw skill. Instant trust grades, findings breakdown, and safety verdicts. No signup required.',
          }}
        />
      )}

      {/* Header */}
      <div className="text-center mb-8 pt-4">
        <h1 className="text-4xl sm:text-5xl font-extrabold leading-tight tracking-tight mb-3">
          <span className="gradient-text">Is This Agent</span>{' '}
          <span className="gradient-text-bio">Safe?</span>
        </h1>
        {!hasResult && (
          <p className="text-sm text-text-muted max-w-md mx-auto">
            Paste a GitHub URL, package name, or search by name to get an instant security report.
          </p>
        )}
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSubmit} className="mb-6">
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="github.com/owner/repo, package name, or agent name..."
            aria-label="Check an agent"
            className="w-full bg-surface border border-border rounded-lg pl-5 pr-28 py-4 sm:py-5 text-text focus:outline-none focus:border-primary text-base sm:text-lg"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 sm:py-2 rounded-md bg-primary hover:bg-primary-dark text-white text-sm font-medium transition-colors disabled:opacity-40 cursor-pointer"
          >
            Check
          </button>
        </div>
      </form>

      {/* Back to search when viewing results */}
      {hasResult && (
        <div className="mb-6">
          <Link to="/check" className="text-xs text-primary-light hover:underline">
            &larr; New search
          </Link>
        </div>
      )}

      {/* Result or Search */}
      {hasResult ? (
        <ScanResultView owner={owner} repo={repo} />
      ) : searchQuery ? (
        <SearchResults query={searchQuery} />
      ) : (
        /* Empty state — tips and examples */
        <div className="text-center py-8">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-lg mx-auto mb-8">
            <div className="bg-surface border border-border rounded-lg p-3">
              <p className="text-xs font-semibold text-text-primary mb-1">GitHub URL</p>
              <p className="text-xs text-text-muted font-mono">github.com/owner/repo</p>
            </div>
            <div className="bg-surface border border-border rounded-lg p-3">
              <p className="text-xs font-semibold text-text-primary mb-1">Package Name</p>
              <p className="text-xs text-text-muted font-mono">langchain</p>
            </div>
            <div className="bg-surface border border-border rounded-lg p-3">
              <p className="text-xs font-semibold text-text-primary mb-1">MCP Server</p>
              <p className="text-xs text-text-muted font-mono">filesystem</p>
            </div>
          </div>

          <p className="text-xs text-text-muted">
            Free, no account required. Results are cached for 1 hour.
          </p>
        </div>
      )}
    </PageTransition>
  )
}
