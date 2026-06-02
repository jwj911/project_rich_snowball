'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'

const STORAGE_KEY = 'futures_preferences'

export interface Preferences {
  theme: 'dark' | 'light' | 'system'
  pollingIntervalSeconds: number
  notificationsEnabled: boolean
  language: string
}

const DEFAULT_PREFERENCES: Preferences = {
  theme: 'dark',
  pollingIntervalSeconds: 30,
  notificationsEnabled: true,
  language: 'zh-CN',
}

function loadFromStorage(): Preferences | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return {
      theme: parsed.theme ?? DEFAULT_PREFERENCES.theme,
      pollingIntervalSeconds: parsed.pollingIntervalSeconds ?? DEFAULT_PREFERENCES.pollingIntervalSeconds,
      notificationsEnabled: parsed.notificationsEnabled ?? DEFAULT_PREFERENCES.notificationsEnabled,
      language: parsed.language ?? DEFAULT_PREFERENCES.language,
    }
  } catch {
    return null
  }
}

function saveToStorage(prefs: Preferences) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // ignore
  }
}

export function usePreferences() {
  const [preferences, setPreferences] = useState<Preferences>(() => {
    return loadFromStorage() ?? DEFAULT_PREFERENCES
  })

  const loadFromApi = useCallback(async () => {
    try {
      const settings = await api.getUserSettings()
      const prefs: Preferences = {
        theme: (settings.theme as Preferences['theme']) ?? DEFAULT_PREFERENCES.theme,
        pollingIntervalSeconds: settings.polling_interval_seconds ?? DEFAULT_PREFERENCES.pollingIntervalSeconds,
        notificationsEnabled: settings.notifications_enabled ?? DEFAULT_PREFERENCES.notificationsEnabled,
        language: settings.language ?? DEFAULT_PREFERENCES.language,
      }
      setPreferences(prefs)
      saveToStorage(prefs)
    } catch {
      // API 失败时保持现有值（可能来自 localStorage）
    }
  }, [])

  const updatePreferences = useCallback((updates: Partial<Preferences>) => {
    setPreferences((prev) => {
      const next = { ...prev, ...updates }
      saveToStorage(next)
      // 触发自定义事件，通知其他监听方（如 DynamicToaster）
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY }))
      }
      return next
    })
  }, [])

  // 首次挂载时从 API 同步
  useEffect(() => {
    loadFromApi()
  }, [loadFromApi])

  // 监听其他标签页的 storage 变化
  useEffect(() => {
    const handle = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        const stored = loadFromStorage()
        if (stored) setPreferences(stored)
      }
    }
    window.addEventListener('storage', handle)
    return () => window.removeEventListener('storage', handle)
  }, [])

  return {
    preferences,
    updatePreferences,
    refresh: loadFromApi,
  }
}

/** 纯工具函数：从 localStorage 读取偏好（不触发 hook） */
export function getPreferencesFromStorage(): Preferences {
  return loadFromStorage() ?? DEFAULT_PREFERENCES
}
