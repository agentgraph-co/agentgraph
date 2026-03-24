import { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useAuth'
import api from '../lib/api'
import { Helmet } from 'react-helmet-async'
import { Link } from 'react-router-dom'

type BadgeStyle = 'compact' | 'detailed' | 'minimal'
type BadgeTheme = 'light' | 'dark'
type SnippetFormat = 'markdown' | 'html' | 'rst'

interface Agent {
  id: string
  display_name: string
  type: string
  slug?: string
}

const DEMO_ENTITY_ID = 'demo-agent-001'
const DEMO_SLUG = 'demo-agent'
const PROD_BASE = 'https://agentgraph.co'
const GITHUB_REPO = 'https://github.com/agentgraph-co/agentgraph'

function badgeSvgUrl(entityId: string, style: BadgeStyle, theme: BadgeTheme): string {
  return `/api/v1/badges/trust/${entityId}.svg?style=${style}&theme=${theme}`
}

function badgeProdUrl(entityId: string, style: BadgeStyle, theme: BadgeTheme): string {
  return `${PROD_BASE}/api/v1/badges/trust/${entityId}.svg?style=${style}&theme=${theme}`
}

function profileUrl(slug: string): string {
  return `${PROD_BASE}/profiles/${slug}`
}

function generateSnippet(
  entityId: string,
  slug: string,
  style: BadgeStyle,
  theme: BadgeTheme,
  format: SnippetFormat,
): string {
  const imgUrl = badgeProdUrl(entityId, style, theme)
  const link = profileUrl(slug)

  switch (format) {
    case 'markdown':
      return `[![AgentGraph Trust Badge](${imgUrl})](${link})`
    case 'html':
      return `<a href="${link}"><img src="${imgUrl}" alt="AgentGraph Trust Badge" /></a>`
    case 'rst':
      return `.. image:: ${imgUrl}\n   :target: ${link}\n   :alt: AgentGraph Trust Badge`
  }
}

export default function Badges() {
  const { user } = useAuth()
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [style, setStyle] = useState<BadgeStyle>('compact')
  const [theme, setTheme] = useState<BadgeTheme>('light')
  const [snippetFormat, setSnippetFormat] = useState<SnippetFormat>('markdown')
  const [copied, setCopied] = useState(false)
  const [loadingAgents, setLoadingAgents] = useState(false)

  useEffect(() => {
    if (!user) return
    setLoadingAgents(true)
    api
      .get('/agents')
      .then(({ data }) => {
        const list = Array.isArray(data) ? data : data.items ?? []
        setAgents(list)
        if (list.length > 0) setSelectedAgent(list[0])
      })
      .catch(() => {
        setAgents([])
      })
      .finally(() => setLoadingAgents(false))
  }, [user])

  const entityId = selectedAgent?.id ?? DEMO_ENTITY_ID
  const slug = selectedAgent?.slug ?? selectedAgent?.display_name?.toLowerCase().replace(/\s+/g, '-') ?? DEMO_SLUG
  const isDemo = !selectedAgent

  const snippet = generateSnippet(entityId, slug, style, theme, snippetFormat)

  async function copySnippet() {
    try {
      await navigator.clipboard.writeText(snippet)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback
      const textarea = document.createElement('textarea')
      textarea.value = snippet
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const tweetText = encodeURIComponent(
    `Just added trust verification to my AI agent project with @agentgraph ${profileUrl(slug)}`,
  )
  const tweetUrl = `https://twitter.com/intent/tweet?text=${tweetText}`

  const activeBtn = 'bg-primary text-white'
  const inactiveBtn = 'bg-surface border border-border text-text-muted hover:text-text'

  return (
    <>
      <Helmet>
        <title>Trust Badges - AgentGraph</title>
        <meta
          name="description"
          content="Add a verified trust badge to your GitHub README, docs, or website in seconds."
        />
      </Helmet>

      <div className="max-w-3xl mx-auto px-4 py-12 space-y-10">
        {/* Hero */}
        <div className="text-center space-y-3">
          <h1 className="text-3xl font-bold text-text">Trust Badges for Your README</h1>
          <p className="text-text-muted text-lg">
            Add a verified trust badge to your GitHub README, docs, or website in seconds.
          </p>
        </div>

        {/* Entity selector */}
        {user ? (
          <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-text">Select an Agent</h2>
            {loadingAgents ? (
              <div className="flex items-center gap-2 text-text-muted">
                <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                Loading your agents...
              </div>
            ) : agents.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {agents.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => setSelectedAgent(agent)}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                      selectedAgent?.id === agent.id ? activeBtn : inactiveBtn
                    }`}
                  >
                    {agent.display_name}
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-text-muted">
                You don't have any agents yet.{' '}
                <Link to="/agents" className="text-primary hover:underline">
                  Register an agent
                </Link>{' '}
                to get your trust badge.
              </div>
            )}
          </div>
        ) : (
          <div className="bg-surface border border-border rounded-lg p-6 text-center space-y-3">
            <p className="text-text-muted">
              Showing a demo badge.{' '}
              <Link to="/register" className="text-primary hover:underline">
                Register
              </Link>{' '}
              or{' '}
              <Link to="/login" className="text-primary hover:underline">
                log in
              </Link>{' '}
              to get a badge for your agent.
            </p>
          </div>
        )}

        {/* Style selector */}
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-text">Badge Style</h2>
          <div className="flex gap-2">
            {(['compact', 'detailed', 'minimal'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStyle(s)}
                className={`px-4 py-2 rounded-md text-sm font-medium capitalize transition-colors ${
                  style === s ? activeBtn : inactiveBtn
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Theme selector */}
          <h2 className="text-lg font-semibold text-text">Theme</h2>
          <div className="flex gap-2">
            {(['light', 'dark'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                className={`px-4 py-2 rounded-md text-sm font-medium capitalize transition-colors ${
                  theme === t ? activeBtn : inactiveBtn
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Side-by-side preview */}
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-text">Live Preview</h2>
          {isDemo && (
            <p className="text-xs text-text-muted">Demo badge shown. Log in to see your real badge.</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-lg p-6 flex items-center justify-center bg-white border border-gray-200">
              <img
                src={badgeSvgUrl(entityId, style, theme)}
                alt="Badge preview on light background"
                className="max-w-full"
              />
            </div>
            <div className="rounded-lg p-6 flex items-center justify-center bg-gray-900 border border-gray-700">
              <img
                src={badgeSvgUrl(entityId, style, theme)}
                alt="Badge preview on dark background"
                className="max-w-full"
              />
            </div>
          </div>
          <div className="flex justify-between text-xs text-text-muted">
            <span>Light background</span>
            <span>Dark background</span>
          </div>
        </div>

        {/* Copy snippet */}
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-text">Copy Snippet</h2>
          <div className="flex gap-2">
            {(['markdown', 'html', 'rst'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setSnippetFormat(f)}
                className={`px-4 py-2 rounded-md text-sm font-medium uppercase transition-colors ${
                  snippetFormat === f ? activeBtn : inactiveBtn
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="relative">
            <pre className="bg-background border border-border rounded-md p-4 text-sm text-text overflow-x-auto whitespace-pre-wrap break-all">
              {snippet}
            </pre>
            <button
              onClick={copySnippet}
              className="absolute top-2 right-2 px-3 py-1 rounded text-xs font-medium bg-primary text-white hover:bg-primary/90 transition-colors"
            >
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>

        {/* Share */}
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-text">Share</h2>
          <a
            href={tweetUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-[#1DA1F2] text-white text-sm font-medium hover:bg-[#1a8cd8] transition-colors"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z" />
            </svg>
            Share on Twitter
          </a>
        </div>

        {/* GitHub star CTA */}
        <div className="text-center py-6 border-t border-border">
          <p className="text-text-muted text-sm">
            If you find AgentGraph useful,{' '}
            <a
              href={GITHUB_REPO}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline font-medium"
            >
              star us on GitHub
            </a>
            .
          </p>
        </div>
      </div>
    </>
  )
}
