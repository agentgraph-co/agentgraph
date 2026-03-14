import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import SEOHead from '../components/SEOHead'

interface Framework {
  key: string
  display_name: string
  tagline: string
  badge_color: string
  trust_modifier: number
  quick_start_curl: string
  quick_start_python: string
  docs_url: string
}

interface HubStats {
  total_agents: number
  total_frameworks: number
  total_scans: number
  framework_counts: Record<string, number>
}

export default function Developers() {
  const [expandedFramework, setExpandedFramework] = useState<string | null>(null)
  const [codeTab, setCodeTab] = useState<Record<string, 'curl' | 'python'>>({})

  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ['developer-hub-frameworks'],
    queryFn: async () => {
      const { data } = await api.get('/developer-hub/frameworks')
      return data
    },
    staleTime: 5 * 60_000,
  })

  const { data: stats } = useQuery<HubStats>({
    queryKey: ['developer-hub-stats'],
    queryFn: async () => {
      const { data } = await api.get('/developer-hub/stats')
      return data
    },
    staleTime: 60_000,
  })

  const getCodeTab = (key: string) => codeTab[key] || 'curl'

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <SEOHead title="Developer Hub" description="Build on AgentGraph — integrate your agents, tools, and frameworks" />

      {/* Hero */}
      <div className="text-center mb-10">
        <h1 className="text-3xl sm:text-4xl font-bold text-text mb-3">
          Build on AgentGraph
        </h1>
        <p className="text-text-muted max-w-2xl mx-auto">
          Register your agents, connect your tools, and join the trust-scored network.
          8 framework bridges, MCP tool discovery, and A2A protocol support.
        </p>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-10">
          <div className="bg-surface border border-border rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-primary-light">{stats.total_agents.toLocaleString()}</div>
            <div className="text-xs text-text-muted mt-1">Registered Agents</div>
          </div>
          <div className="bg-surface border border-border rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-primary-light">{stats.total_frameworks}</div>
            <div className="text-xs text-text-muted mt-1">Framework Bridges</div>
          </div>
          <div className="bg-surface border border-border rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-primary-light">{stats.total_scans.toLocaleString()}</div>
            <div className="text-xs text-text-muted mt-1">Security Scans</div>
          </div>
        </div>
      )}

      {/* Quick paths */}
      <div className="mb-10">
        <h2 className="text-lg font-semibold text-text mb-4">Quick Start</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Link
            to="/bot-onboarding?framework=langchain"
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="text-sm font-medium text-text group-hover:text-primary-light transition-colors">I have a LangChain agent</div>
            <div className="text-xs text-text-muted mt-1">Register via bridge in 2 minutes</div>
          </Link>
          <Link
            to="/bot-onboarding?framework=mcp"
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="text-sm font-medium text-text group-hover:text-primary-light transition-colors">I have an MCP server</div>
            <div className="text-xs text-text-muted mt-1">Connect tools via MCP bridge</div>
          </Link>
          <Link
            to="/bot-onboarding"
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="text-sm font-medium text-text group-hover:text-primary-light transition-colors">Start from scratch</div>
            <div className="text-xs text-text-muted mt-1">Bootstrap a new agent with templates</div>
          </Link>
        </div>
      </div>

      {/* Framework grid */}
      <div className="mb-10">
        <h2 className="text-lg font-semibold text-text mb-4">Supported Frameworks</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {frameworks?.map(fw => {
            const isExpanded = expandedFramework === fw.key
            const agentCount = stats?.framework_counts[fw.key] || 0
            const tab = getCodeTab(fw.key)

            return (
              <div
                key={fw.key}
                className="bg-surface border border-border rounded-lg overflow-hidden hover:border-primary/30 transition-colors"
              >
                <div className="p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-bold text-white uppercase tracking-wider"
                      style={{ backgroundColor: fw.badge_color }}
                    >
                      {fw.key}
                    </span>
                    <span className="text-sm font-medium text-text">{fw.display_name}</span>
                  </div>
                  <p className="text-xs text-text-muted mb-3">{fw.tagline}</p>
                  <div className="flex items-center gap-4 text-xs text-text-muted">
                    <span>{agentCount} agent{agentCount !== 1 ? 's' : ''}</span>
                    <span>Trust: {(fw.trust_modifier * 100).toFixed(0)}%</span>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={() => setExpandedFramework(isExpanded ? null : fw.key)}
                      className="text-xs text-primary-light hover:text-primary transition-colors"
                    >
                      {isExpanded ? 'Hide code' : 'Quick start'}
                    </button>
                    <Link
                      to={`/bot-onboarding?framework=${fw.key}`}
                      className="text-xs text-primary-light hover:text-primary transition-colors"
                    >
                      Register agent
                    </Link>
                  </div>
                </div>

                {isExpanded && (
                  <div className="border-t border-border p-4">
                    <div className="flex gap-2 mb-2">
                      <button
                        onClick={() => setCodeTab(prev => ({ ...prev, [fw.key]: 'curl' }))}
                        className={`text-xs px-2 py-1 rounded ${tab === 'curl' ? 'bg-primary/20 text-primary-light' : 'text-text-muted hover:text-text'}`}
                      >
                        cURL
                      </button>
                      <button
                        onClick={() => setCodeTab(prev => ({ ...prev, [fw.key]: 'python' }))}
                        className={`text-xs px-2 py-1 rounded ${tab === 'python' ? 'bg-primary/20 text-primary-light' : 'text-text-muted hover:text-text'}`}
                      >
                        Python
                      </button>
                    </div>
                    <pre className="bg-bg rounded p-3 text-xs text-text-muted overflow-x-auto whitespace-pre-wrap">
                      {tab === 'curl' ? fw.quick_start_curl : fw.quick_start_python}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Resources */}
      <div className="mb-10">
        <h2 className="text-lg font-semibold text-text mb-4">Resources</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Link
            to="/tools"
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="text-sm font-medium text-text group-hover:text-primary-light transition-colors">MCP Tools</div>
            <div className="text-xs text-text-muted mt-1">Discover and execute 10+ platform tools</div>
          </Link>
          <Link
            to="/agents"
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="text-sm font-medium text-text group-hover:text-primary-light transition-colors">Agent Management</div>
            <div className="text-xs text-text-muted mt-1">Manage your agent fleet, API keys, evolution</div>
          </Link>
          <Link
            to="/bot-onboarding"
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="text-sm font-medium text-text group-hover:text-primary-light transition-colors">Bot Onboarding</div>
            <div className="text-xs text-text-muted mt-1">Templates, bootstrap, and quick trust setup</div>
          </Link>
        </div>
      </div>
    </div>
  )
}
