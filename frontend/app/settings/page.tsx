'use client'

import { useCallback, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import ErrorState from '@/components/ui/ErrorState'
import Button from '@/components/ui/Button'
import { api, type UserPreference } from '@/lib/api'
import { toast } from 'sonner'
import { Settings, Moon, Timer, Check } from 'lucide-react'
import useSWR from 'swr'
import { usePreferences } from '@/hooks/usePreferences'

const THEME_OPTIONS = [
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'light', label: '浅色', icon: undefined as undefined },
  { value: 'system', label: '跟随系统', icon: undefined as undefined },
] as const

const POLLING_OPTIONS = [5, 10, 30, 60] as const

export default function SettingsPage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()
  const [saving, setSaving] = useState(false)
  const { updatePreferences } = usePreferences()

  const {
    data: settings,
    error,
    mutate,
    isLoading,
  } = useSWR(
    isAuthenticated ? 'user-settings' : null,
    () => api.getUserSettings(),
    { revalidateOnFocus: false },
  )

  const handleSave = useCallback(
    async (updates: Partial<UserPreference>) => {
      if (!settings) return
      setSaving(true)
      try {
        const updated = await api.updateUserSettings({
          theme: updates.theme ?? undefined,
          polling_interval_seconds: updates.polling_interval_seconds ?? undefined,
          notifications_enabled: updates.notifications_enabled ?? undefined,
          language: updates.language ?? undefined,
        })
        await mutate(updated, false)
        // 同步到本地偏好缓存，驱动 UI 生效
        updatePreferences({
          theme: updated.theme as 'dark' | 'light' | 'system' | undefined,
          pollingIntervalSeconds: updated.polling_interval_seconds ?? undefined,
          notificationsEnabled: updated.notifications_enabled ?? undefined,
          language: updated.language ?? undefined,
        })
        toast.success('设置已保存')
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '保存失败')
      } finally {
        setSaving(false)
      }
    },
    [settings, mutate, updatePreferences],
  )

  return (
    <AppShell>
      {authLoading ? (
        <StatePanel>正在确认登录状态...</StatePanel>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="mx-auto max-w-2xl space-y-6">
          {/* Header */}
          <section className="rounded-lg border border-slate-800 bg-surface p-5">
            <div className="flex items-center gap-3">
              <Settings size={22} className="text-red-400" />
              <div>
                <h1 className="text-xl font-bold text-white">个人设置</h1>
                <p className="mt-1 text-sm text-slate-400">
                  {user ? `${user.username} 的偏好配置` : '管理你的个人偏好'}
                </p>
              </div>
            </div>
          </section>

          {error ? (
            <ErrorState message={error instanceof Error ? error.message : '加载失败'} onRetry={() => mutate()} />
          ) : isLoading ? (
            <SettingsSkeleton />
          ) : settings ? (
            <>
              {/* 外观 */}
              <SettingCard title="外观" icon={Moon}>
                <div className="grid grid-cols-3 gap-3">
                  {THEME_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => handleSave({ theme: opt.value })}
                      disabled={saving}
                      className={`relative flex flex-col items-center gap-2 rounded-lg border px-4 py-4 text-sm transition ${
                        settings.theme === opt.value
                          ? 'border-red-500/50 bg-red-500/10 text-white'
                          : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                      }`}
                    >
                      {settings.theme === opt.value && (
                        <span className="absolute right-2 top-2">
                          <Check size={14} className="text-red-400" />
                        </span>
                      )}
                      {opt.icon && <opt.icon size={18} />}
                      <span>{opt.label}</span>
                    </button>
                  ))}
                </div>
              </SettingCard>

              {/* 行情刷新 */}
              <SettingCard title="行情刷新间隔" icon={Timer}>
                <div className="flex flex-wrap gap-2">
                  {POLLING_OPTIONS.map((sec) => (
                    <button
                      key={sec}
                      type="button"
                      onClick={() => handleSave({ polling_interval_seconds: sec })}
                      disabled={saving}
                      className={`rounded-lg border px-4 py-2 text-sm transition ${
                        settings.polling_interval_seconds === sec
                          ? 'border-red-500/50 bg-red-500/10 text-white'
                          : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                      }`}
                    >
                      {sec} 秒
                    </button>
                  ))}
                </div>
              </SettingCard>
            </>
          ) : null}
        </div>
      )}
    </AppShell>
  )
}

function SettingCard({
  title,
  icon: Icon,
  children,
}: {
  title: string
  icon: React.ElementType
  children: React.ReactNode
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-5">
      <div className="mb-4 flex items-center gap-2">
        <Icon size={16} className="text-slate-500" />
        <h2 className="text-sm font-semibold text-slate-300">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-red-600' : 'bg-slate-700'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  )
}

function StatePanel({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-8 text-center text-slate-400">
      {children}
    </div>
  )
}

function SettingsSkeleton() {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-32 animate-pulse rounded-lg border border-slate-800 bg-surface p-5">
          <div className="mb-4 h-4 w-24 rounded bg-slate-800" />
          <div className="flex gap-3">
            <div className="h-10 w-20 rounded bg-slate-800" />
            <div className="h-10 w-20 rounded bg-slate-800" />
            <div className="h-10 w-20 rounded bg-slate-800" />
          </div>
        </div>
      ))}
    </>
  )
}
