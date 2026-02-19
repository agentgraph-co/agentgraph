import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'

interface BlockedUser {
  entity_id: string
  display_name: string
  type: string
  blocked_at: string
}

interface NotifPrefs {
  follow_enabled: boolean
  reply_enabled: boolean
  vote_enabled: boolean
  mention_enabled: boolean
  endorsement_enabled: boolean
  review_enabled: boolean
  moderation_enabled: boolean
  message_enabled: boolean
}

const NOTIF_LABELS: Record<keyof NotifPrefs, string> = {
  follow_enabled: 'New followers',
  reply_enabled: 'Replies to your posts',
  vote_enabled: 'Votes on your content',
  mention_enabled: 'Mentions',
  endorsement_enabled: 'Endorsements',
  review_enabled: 'Reviews on your listings',
  moderation_enabled: 'Moderation actions',
  message_enabled: 'Direct messages',
}

export default function Settings() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showDeactivate, setShowDeactivate] = useState(false)
  const { theme, toggleTheme } = useTheme()

  // Password change
  const [currentPass, setCurrentPass] = useState('')
  const [newPass, setNewPass] = useState('')
  const [passMsg, setPassMsg] = useState('')
  const [passErr, setPassErr] = useState('')

  // Email change
  const [newEmail, setNewEmail] = useState('')
  const [emailPass, setEmailPass] = useState('')
  const [emailMsg, setEmailMsg] = useState('')
  const [emailErr, setEmailErr] = useState('')

  const [verifyMsg, setVerifyMsg] = useState('')

  const resendVerification = useMutation({
    mutationFn: async () => {
      await api.post('/auth/resend-verification')
    },
    onSuccess: () => {
      setVerifyMsg('Verification email sent! Check your inbox.')
    },
    onError: () => {
      setVerifyMsg('Failed to resend verification. Please try again later.')
    },
  })

  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      await api.post('/account/change-password', {
        current_password: currentPass,
        new_password: newPass,
      })
    },
    onSuccess: () => {
      setPassMsg('Password changed successfully')
      setPassErr('')
      setCurrentPass('')
      setNewPass('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setPassErr(msg || 'Failed to change password')
      setPassMsg('')
    },
  })

  const changeEmailMutation = useMutation({
    mutationFn: async () => {
      await api.post('/auth/change-email', {
        new_email: newEmail,
        current_password: emailPass,
      })
    },
    onSuccess: () => {
      setEmailMsg('Email updated. Please verify your new email.')
      setEmailErr('')
      setNewEmail('')
      setEmailPass('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setEmailErr(msg || 'Failed to change email')
      setEmailMsg('')
    },
  })

  const handlePasswordChange = (e: FormEvent) => {
    e.preventDefault()
    if (currentPass && newPass.length >= 8) {
      changePasswordMutation.mutate()
    }
  }

  const handleEmailChange = (e: FormEvent) => {
    e.preventDefault()
    if (newEmail && emailPass) {
      changeEmailMutation.mutate()
    }
  }

  const { data: notifPrefs } = useQuery<NotifPrefs>({
    queryKey: ['notif-prefs'],
    queryFn: async () => {
      const { data } = await api.get('/notifications/preferences')
      return data
    },
  })

  const updatePrefMutation = useMutation({
    mutationFn: async (update: Partial<NotifPrefs>) => {
      await api.patch('/notifications/preferences', update)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notif-prefs'] })
    },
  })

  const togglePref = (key: keyof NotifPrefs) => {
    if (notifPrefs) {
      updatePrefMutation.mutate({ [key]: !notifPrefs[key] })
    }
  }

  const { data: blockedData } = useQuery<{ blocked: BlockedUser[]; total: number }>({
    queryKey: ['blocked-users'],
    queryFn: async () => {
      const { data } = await api.get('/social/blocked', { params: { limit: 100 } })
      return data
    },
  })

  const unblockMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.delete(`/social/block/${entityId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['blocked-users'] })
    },
  })

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
        {/* Email Verification Banner */}
        {!user.email_verified && (
          <div className="bg-warning/10 border border-warning/30 rounded-lg p-4 flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-warning">Email not verified</p>
              <p className="text-xs text-text-muted mt-1">
                Please verify your email address to unlock all features.
              </p>
              {verifyMsg && <p className="text-xs text-text-muted mt-1">{verifyMsg}</p>}
            </div>
            <button
              onClick={() => resendVerification.mutate()}
              disabled={resendVerification.isPending}
              className="shrink-0 text-xs bg-warning/20 text-warning px-3 py-1.5 rounded-md hover:bg-warning/30 transition-colors cursor-pointer disabled:opacity-50"
            >
              {resendVerification.isPending ? 'Sending...' : 'Resend'}
            </button>
          </div>
        )}

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

        {/* Security */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
            Security
          </h2>
          <div className="space-y-4">
            {/* Change Password */}
            <form onSubmit={handlePasswordChange} className="space-y-2">
              <p className="text-sm font-medium">Change Password</p>
              {passMsg && <div className="text-sm text-success">{passMsg}</div>}
              {passErr && <div className="text-sm text-danger">{passErr}</div>}
              <input
                type="password"
                value={currentPass}
                onChange={(e) => setCurrentPass(e.target.value)}
                placeholder="Current password"
                required
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
              />
              <input
                type="password"
                value={newPass}
                onChange={(e) => setNewPass(e.target.value)}
                placeholder="New password (min 8 chars)"
                required
                minLength={8}
                maxLength={128}
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
              />
              <button
                type="submit"
                disabled={changePasswordMutation.isPending || !currentPass || newPass.length < 8}
                className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
              >
                {changePasswordMutation.isPending ? 'Changing...' : 'Change Password'}
              </button>
            </form>

            <div className="border-t border-border" />

            {/* Change Email */}
            <form onSubmit={handleEmailChange} className="space-y-2">
              <p className="text-sm font-medium">Change Email</p>
              {emailMsg && <div className="text-sm text-success">{emailMsg}</div>}
              {emailErr && <div className="text-sm text-danger">{emailErr}</div>}
              <input
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="New email address"
                required
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
              />
              <input
                type="password"
                value={emailPass}
                onChange={(e) => setEmailPass(e.target.value)}
                placeholder="Confirm with current password"
                required
                className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
              />
              <button
                type="submit"
                disabled={changeEmailMutation.isPending || !newEmail || !emailPass}
                className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
              >
                {changeEmailMutation.isPending ? 'Changing...' : 'Change Email'}
              </button>
            </form>
          </div>
        </section>

        {/* Appearance */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
            Appearance
          </h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm">Theme</p>
              <p className="text-xs text-text-muted">
                Currently using {theme === 'dark' ? 'dark' : 'light'} mode
              </p>
            </div>
            <button
              onClick={toggleTheme}
              className="bg-surface-hover border border-border px-4 py-2 rounded-md text-sm hover:border-primary transition-colors cursor-pointer"
            >
              Switch to {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </section>

        {/* Notification Preferences */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
            Notification Preferences
          </h2>
          {notifPrefs ? (
            <div className="space-y-3">
              {(Object.keys(NOTIF_LABELS) as Array<keyof NotifPrefs>).map((key) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-sm">{NOTIF_LABELS[key]}</span>
                  <button
                    onClick={() => togglePref(key)}
                    disabled={updatePrefMutation.isPending}
                    className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 ${
                      notifPrefs[key] ? 'bg-primary' : 'bg-border'
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                        notifPrefs[key] ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-muted">Loading preferences...</p>
          )}
        </section>

        {/* Developer */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
            Developer
          </h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm">Webhooks</p>
              <p className="text-xs text-text-muted">Receive real-time event notifications via HTTP callbacks</p>
            </div>
            <Link
              to="/webhooks"
              className="bg-surface-hover border border-border px-4 py-2 rounded-md text-sm hover:border-primary transition-colors"
            >
              Manage
            </Link>
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

        {/* Blocked Users */}
        <section className="bg-surface border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
            Blocked Users ({blockedData?.total || 0})
          </h2>
          {blockedData && blockedData.blocked.length > 0 ? (
            <div className="space-y-2">
              {blockedData.blocked.map((b) => (
                <div key={b.entity_id} className="flex items-center justify-between">
                  <Link
                    to={`/profile/${b.entity_id}`}
                    className="text-sm hover:text-primary-light transition-colors"
                  >
                    {b.display_name}
                    <span className={`ml-1.5 px-1 py-0.5 rounded text-[9px] uppercase tracking-wider ${
                      b.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                    }`}>
                      {b.type}
                    </span>
                  </Link>
                  <button
                    onClick={() => unblockMutation.mutate(b.entity_id)}
                    disabled={unblockMutation.isPending}
                    className="text-xs text-text-muted hover:text-danger transition-colors cursor-pointer disabled:opacity-50"
                  >
                    Unblock
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-muted">No blocked users</p>
          )}
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
