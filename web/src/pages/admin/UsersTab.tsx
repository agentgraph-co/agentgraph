import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import type { EntityItem } from './types'

export default function UsersTab() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [userSearchInput, setUserSearchInput] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [userTypeFilter, setUserTypeFilter] = useState<string>('')
  const [suspendTarget, setSuspendTarget] = useState<string | null>(null)
  const [suspendDays, setSuspendDays] = useState(7)

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setUserSearch(userSearchInput.trim())
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [userSearchInput])

  const { data: entities } = useQuery<{ entities: EntityItem[]; total: number }>({
    queryKey: ['admin-entities', userSearch, userTypeFilter],
    queryFn: async () => {
      const params: Record<string, string> = { limit: '50' }
      if (userSearch) params.q = userSearch
      if (userTypeFilter) params.type = userTypeFilter
      const { data } = await api.get('/admin/entities', { params })
      return data
    },
    staleTime: 2 * 60_000,
  })

  const deactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/deactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: () => {
      addToast('Failed to deactivate user', 'error')
    },
  })

  const reactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/reactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: () => {
      addToast('Failed to reactivate user', 'error')
    },
  })

  const suspendMutation = useMutation({
    mutationFn: async ({ entityId, days }: { entityId: string; days: number }) => {
      await api.patch(`/admin/entities/${entityId}/suspend`, null, { params: { days } })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setSuspendTarget(null)
    },
    onError: () => {
      addToast('Failed to suspend user', 'error')
    },
  })

  const promoteMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/promote`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      addToast('Entity promoted to admin', 'success')
    },
    onError: () => { addToast('Failed to promote entity', 'error') },
  })

  const demoteMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/demote`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      addToast('Admin rights removed', 'success')
    },
    onError: () => { addToast('Failed to demote entity', 'error') },
  })

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <input
          type="search"
          value={userSearchInput}
          onChange={(e) => setUserSearchInput(e.target.value)}
          placeholder="Search by name or email..."
          aria-label="Search users"
          className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
        />
        <select
          value={userTypeFilter}
          onChange={(e) => setUserTypeFilter(e.target.value)}
          aria-label="Filter by entity type"
          className="bg-surface border border-border rounded-md px-3 py-2 text-sm text-text"
        >
          <option value="">All types</option>
          <option value="human">Humans</option>
          <option value="agent">Agents</option>
        </select>
      </div>

      {entities && (
        <div className="text-xs text-text-muted mb-2">{entities.total} total</div>
      )}

      <div className="space-y-2">
        {entities?.entities.map((entity) => (
          <div
            key={entity.id}
            className="bg-surface border border-border rounded-lg p-3 flex items-center justify-between"
          >
            <div className="flex items-center gap-2 min-w-0">
              <Link
                to={`/profile/${entity.id}`}
                className="font-medium text-sm hover:text-primary-light transition-colors truncate"
              >
                {entity.display_name}
              </Link>
              <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                entity.type === 'agent' ? 'bg-blue-400/20 text-blue-400' : 'bg-success/20 text-success'
              }`}>
                {entity.type}
              </span>
              {entity.is_admin && (
                <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-warning/20 text-warning">
                  admin
                </span>
              )}
              {!entity.is_active && (
                <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-danger/20 text-danger">
                  inactive
                </span>
              )}
              <span className="text-xs text-text-muted font-mono truncate hidden md:inline">
                {entity.email}
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[10px] text-text-muted hidden md:inline">
                {timeAgo(entity.created_at)}
              </span>
              {entity.is_active ? (
                <div className="flex items-center gap-1.5">
                  {suspendTarget === entity.id ? (
                    <div className="flex items-center gap-1">
                      <select
                        value={suspendDays}
                        onChange={(e) => setSuspendDays(Number(e.target.value))}
                        aria-label="Suspension duration in days"
                        className="bg-background border border-border rounded px-1 py-0.5 text-[10px] text-text"
                      >
                        {[1, 3, 7, 14, 30, 90, 365].map((d) => (
                          <option key={d} value={d}>{d}d</option>
                        ))}
                      </select>
                      <button
                        onClick={() => suspendMutation.mutate({ entityId: entity.id, days: suspendDays })}
                        disabled={suspendMutation.isPending}
                        className="text-[10px] text-danger hover:underline cursor-pointer disabled:opacity-50"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setSuspendTarget(null)}
                        className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => setSuspendTarget(entity.id)}
                        disabled={entity.id === user?.id}
                        className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                      >
                        Suspend
                      </button>
                      <button
                        onClick={() => deactivateMutation.mutate(entity.id)}
                        disabled={deactivateMutation.isPending || entity.id === user?.id}
                        className="text-xs text-text-muted hover:text-danger transition-colors cursor-pointer disabled:opacity-30"
                      >
                        Deactivate
                      </button>
                      {!entity.is_admin && entity.type === 'human' && (
                        <button
                          onClick={() => promoteMutation.mutate(entity.id)}
                          disabled={promoteMutation.isPending}
                          className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                        >
                          Promote
                        </button>
                      )}
                      {entity.is_admin && entity.id !== user?.id && (
                        <button
                          onClick={() => demoteMutation.mutate(entity.id)}
                          disabled={demoteMutation.isPending}
                          className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                        >
                          Demote
                        </button>
                      )}
                    </>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => reactivateMutation.mutate(entity.id)}
                  disabled={reactivateMutation.isPending}
                  className="text-xs text-text-muted hover:text-success transition-colors cursor-pointer disabled:opacity-30"
                >
                  Reactivate
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
