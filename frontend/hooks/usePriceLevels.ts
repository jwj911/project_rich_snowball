import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { api, PriceLevel } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'

export function usePriceLevels(varietyId: number | null, userId: number | null, symbol: string) {
  const [supportLevels, setSupportLevels] = useState<number[]>([])
  const [resistanceLevels, setResistanceLevels] = useState<number[]>([])
  const [levelsLoaded, setLevelsLoaded] = useState(false)
  const [levelError, setLevelError] = useState<string | null>(null)
  const supportRef = useRef(supportLevels)
  const resistanceRef = useRef(resistanceLevels)
  const queueRef = useRef(Promise.resolve())

  useEffect(() => { supportRef.current = supportLevels }, [supportLevels])
  useEffect(() => { resistanceRef.current = resistanceLevels }, [resistanceLevels])

  const levelsStorageKey = useMemo(() => {
    if (!symbol || !userId) return null
    return `price-levels:v1:${userId}:${symbol}`
  }, [symbol, userId])

  const updateLevelsFromData = useCallback((levels: PriceLevel[]) => {
    const support: number[] = []
    const resistance: number[] = []
    for (const pl of levels) {
      const price = Number(pl.price)
      if (!Number.isFinite(price)) continue
      if (pl.type === 'support') support.push(price)
      else if (pl.type === 'resistance') resistance.push(price)
    }
    setSupportLevels(support.sort((a, b) => a - b))
    setResistanceLevels(resistance.sort((a, b) => b - a))
  }, [])

  const syncToLocalStorage = useCallback((levels: PriceLevel[]) => {
    if (!levelsStorageKey || typeof window === 'undefined') return
    const support = levels
      .filter((l) => l.type === 'support')
      .map((l) => Number(l.price))
      .filter(Number.isFinite)
    const resistance = levels
      .filter((l) => l.type === 'resistance')
      .map((l) => Number(l.price))
      .filter(Number.isFinite)
    window.localStorage.setItem(
      levelsStorageKey,
      JSON.stringify({
        supportLevels: support,
        resistanceLevels: resistance,
        updatedAt: new Date().toISOString(),
      }),
    )
  }, [levelsStorageKey])

  const loadFromLocalStorage = useCallback(() => {
    if (!levelsStorageKey || typeof window === 'undefined') {
      setSupportLevels([])
      setResistanceLevels([])
      return
    }
    try {
      const raw = window.localStorage.getItem(levelsStorageKey)
      if (!raw) {
        setSupportLevels([])
        setResistanceLevels([])
        return
      }
      const parsed = JSON.parse(raw)
      const support = normalizeLevels(parsed.supportLevels)
      const resistance = normalizeLevels(parsed.resistanceLevels)
      setSupportLevels(support.sort((a, b) => a - b))
      setResistanceLevels(resistance.sort((a, b) => b - a))
    } catch {
      setSupportLevels([])
      setResistanceLevels([])
    }
  }, [levelsStorageKey])

  useEffect(() => {
    let cancelled = false
    setLevelsLoaded(false)

    async function loadLevels() {
      if (!varietyId) {
        loadFromLocalStorage()
        if (!cancelled) setLevelsLoaded(true)
        return
      }

      try {
        const levels = await api.getPriceLevels(varietyId)
        if (!cancelled) {
          updateLevelsFromData(levels)
          syncToLocalStorage(levels)
        }

        if (levels.length === 0 && levelsStorageKey && typeof window !== 'undefined') {
          const raw = window.localStorage.getItem(levelsStorageKey)
          if (raw) {
            const parsed = JSON.parse(raw)
            const support = normalizeLevels(parsed.supportLevels)
            const resistance = normalizeLevels(parsed.resistanceLevels)
            for (const price of support) {
              await api.createPriceLevel(varietyId, 'support', price.toFixed(2)).catch((err) => {
                captureMessage(`导入支撑位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'warning')
              })
            }
            for (const price of resistance) {
              await api.createPriceLevel(varietyId, 'resistance', price.toFixed(2)).catch((err) => {
                captureMessage(`导入阻力位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'warning')
              })
            }
            const imported = await api.getPriceLevels(varietyId)
            if (!cancelled) {
              updateLevelsFromData(imported)
              syncToLocalStorage(imported)
            }
          }
        }
      } catch (err) {
        captureMessage(`加载价位标注失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
        if (!cancelled) {
          loadFromLocalStorage()
          setLevelError('云端价位加载失败，已使用本地缓存。')
        }
      } finally {
        if (!cancelled) setLevelsLoaded(true)
      }
    }

    loadLevels()

    return () => {
      cancelled = true
    }
  }, [varietyId, levelsStorageKey, loadFromLocalStorage, updateLevelsFromData, syncToLocalStorage])

  const addSupport = async (price: number) => {
    const promise = queueRef.current.then(async () => {
      const currentSupport = supportRef.current
      const currentResistance = resistanceRef.current
      if (!Number.isFinite(price) || currentSupport.includes(price)) return
      if (varietyId) {
        try {
          await api.createPriceLevel(varietyId, 'support', price.toFixed(2))
          const levels = await api.getPriceLevels(varietyId)
          updateLevelsFromData(levels)
          syncToLocalStorage(levels)
          setLevelError(null)
          return
        } catch (err) {
          captureMessage(`添加支撑位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
          setLevelError(`添加失败：${err instanceof Error ? err.message : '未知错误'}，已临时保存到本地。`)
        }
      }
      setSupportLevels((prev) => {
        const next = [...prev, price].sort((a, b) => a - b)
        // 在 functional update 中同步更新 localStorage，避免并行竞争
        if (levelsStorageKey && typeof window !== 'undefined') {
          window.localStorage.setItem(
            levelsStorageKey,
            JSON.stringify({
              supportLevels: next,
              resistanceLevels: resistanceRef.current,
              updatedAt: new Date().toISOString(),
            }),
          )
        }
        return next
      })
    })
    queueRef.current = promise
    return promise
  }

  const addResistance = async (price: number) => {
    const promise = queueRef.current.then(async () => {
      const currentSupport = supportRef.current
      const currentResistance = resistanceRef.current
      if (!Number.isFinite(price) || currentResistance.includes(price)) return
      if (varietyId) {
        try {
          await api.createPriceLevel(varietyId, 'resistance', price.toFixed(2))
          const levels = await api.getPriceLevels(varietyId)
          updateLevelsFromData(levels)
          syncToLocalStorage(levels)
          setLevelError(null)
          return
        } catch (err) {
          captureMessage(`添加阻力位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
          setLevelError(`添加失败：${err instanceof Error ? err.message : '未知错误'}，已临时保存到本地。`)
        }
      }
      setResistanceLevels((prev) => {
        const next = [...prev, price].sort((a, b) => b - a)
        if (levelsStorageKey && typeof window !== 'undefined') {
          window.localStorage.setItem(
            levelsStorageKey,
            JSON.stringify({
              supportLevels: supportRef.current,
              resistanceLevels: next,
              updatedAt: new Date().toISOString(),
            }),
          )
        }
        return next
      })
    })
    queueRef.current = promise
    return promise
  }

  const removeSupport = async (price: number) => {
    if (varietyId) {
      try {
        const levels = await api.getPriceLevels(varietyId, 'support')
        const pl = levels.find((l) => Math.abs(Number(l.price) - price) < 0.0001)
        if (pl) {
          await api.deletePriceLevel(pl.id)
          captureMessage(`删除支撑位: 品种#${varietyId} @ ${price}`, 'info')
          const refreshed = await api.getPriceLevels(varietyId)
          updateLevelsFromData(refreshed)
          syncToLocalStorage(refreshed)
        }
        setLevelError(null)
        return
      } catch (err) {
        captureMessage(`删除支撑位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
        setLevelError(`删除失败：${err instanceof Error ? err.message : '未知错误'}`)
        return
      }
    }
    setSupportLevels((levels) => levels.filter((level) => level !== price))
  }

  const removeResistance = async (price: number) => {
    if (varietyId) {
      try {
        const levels = await api.getPriceLevels(varietyId, 'resistance')
        const pl = levels.find((l) => Math.abs(Number(l.price) - price) < 0.0001)
        if (pl) {
          await api.deletePriceLevel(pl.id)
          captureMessage(`删除阻力位: 品种#${varietyId} @ ${price}`, 'info')
          const refreshed = await api.getPriceLevels(varietyId)
          updateLevelsFromData(refreshed)
          syncToLocalStorage(refreshed)
        }
        setLevelError(null)
        return
      } catch (err) {
        captureMessage(`删除阻力位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
        setLevelError(`删除失败：${err instanceof Error ? err.message : '未知错误'}`)
        return
      }
    }
    setResistanceLevels((levels) => levels.filter((level) => level !== price))
  }

  return {
    supportLevels,
    resistanceLevels,
    levelsLoaded,
    levelError,
    addSupport,
    addResistance,
    removeSupport,
    removeResistance,
  }
}

function normalizeLevels(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => Number(item)).filter(Number.isFinite)
    : []
}
