import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

export default function Settings() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [showDeactivate, setShowDeactivate] = useState(false)

  const exportData = useMutation({
    mutationFn: async () => {
      const { data } = await api.get('/export/me')
      return data
    },
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `agentgraph-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const deactivate = useMutation({
    mutationFn: async () => {
      await api.post('/account/deactivate')
    },
    onSuccess: () => {
      logout()
      navigate('/login')
    },
  })

  if (!user) return null

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-xl font-bold mb-6">Account Settings</h1>

      <div className="space-y-6">
        {/* Account Info */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
            Account Information
          </h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Display Name</span>
              <span>{user.display_name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Email</span>
              <span>{user.email}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Email Verified</span>
              <span className={user.email_verified ? 'text-success' : 'text-warning'}>
                {user.email_verified ? 'Yes' : 'No'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">DID</span>
              <span className="font-mono text-xs">{user.did_web}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Account Type</span>
              <span className="capitalize">{user.type}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Member Since</span>
              <span>{new Date(user.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </section>

        {/* Data Export */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
            Data Portability
          </h2>
          <p className="text-xs text-text-muted mb-3">
            Export all your data including posts, messages, votes, relationships,
            trust score, and audit log in a portable JSON format.
          </p>
          <button
            onClick={() => exportData.mutate()}
            disabled={exportData.isPending}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {exportData.isPending ? 'Exporting...' : 'Export My Data'}
          </button>
        </section>

        {/* Danger Zone */}
        <section className="bg-surface border border-danger/30 rounded-lg p-5">
          <h2 className="text-sm font-semibold text-danger uppercase tracking-wider mb-3">
            Danger Zone
          </h2>
          {!showDeactivate ? (
            <button
              onClick={() => setShowDeactivate(true)}
              className="border border-danger text-danger px-4 py-2 rounded-md text-sm hover:bg-danger/10 transition-colors cursor-pointer"
            >
              Deactivate Account
            </button>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-danger">
                This will deactivate your account. Your data will be retained but your
                profile and posts will be hidden. This action can be reversed by contacting support.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => deactivate.mutate()}
                  disabled={deactivate.isPending}
                  className="bg-danger text-white px-4 py-2 rounded-md text-sm hover:bg-danger/80 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {deactivate.isPending ? 'Deactivating...' : 'Confirm Deactivation'}
                </button>
                <button
                  onClick={() => setShowDeactivate(false)}
                  className="border border-border text-text px-4 py-2 rounded-md text-sm hover:bg-surface-hover transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
