'use client'

import { useEffect, useState } from 'react'
import { Toaster } from 'sonner'
import { getPreferencesFromStorage } from '@/hooks/usePreferences'

export default function DynamicToaster() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('dark')

  useEffect(() => {
    const readTheme = () => {
      const prefs = getPreferencesFromStorage()
      const t = prefs.theme
      if (t === 'light' || t === 'dark' || t === 'system') {
        setTheme(t)
      }
    }

    readTheme()

    const handle = (e: StorageEvent) => {
      if (e.key === 'futures_preferences') {
        readTheme()
      }
    }
    window.addEventListener('storage', handle)
    return () => window.removeEventListener('storage', handle)
  }, [])

  // system  fallback 到 dark（当前没有根据系统主题切换的逻辑）
  const resolvedTheme = theme === 'system' ? 'dark' : theme

  return <Toaster position="top-right" theme={resolvedTheme} />
}
