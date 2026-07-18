import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { api, PriceLevel, PriceLevelScope } from '@/lib/api'
import { formatPricePayload } from '@/lib/format'
import { captureMessage } from '@/lib/sentry-lite'

export interface UsePriceLevelsOptions {
  varietyId: number | null
  userId: number | null
  symbol: string
  source?: 'continuous' | 'main' | 'single'
  contractId?: number | null
  pricePrecision?: number
}

function getScopeFromSource(source: 'continuous' | 'main' | 'single'): PriceLevelScope {
  if (source === 'single') return 'contract'
  return source
}

export function usePriceLevels({
  varietyId,
  userId,
  symbol,
  source = 'continuous',
  contractId = null,
  pricePrecision = 2,
}: UsePriceLevelsOptions) {
  const [supportLevels, setSupportLevels] = useState<number[]>([])
  const [resistanceLevels, setResistanceLevels] = useState<number[]>([])
  const [levelsLoaded, setLevelsLoaded] = useState(false)
  const [levelError, setLevelError] = useState<string | null>(null)
  const supportRef = useRef(supportLevels)
  const resistanceRef = useRef(resistanceLevels)
  const queueRef = useRef(Promise.resolve())
  const mutationVersionRef = useRef(0)

  useEffect(() => { supportRef.current = supportLevels }, [supportLevels])
  useEffect(() => { resistanceRef.current = resistanceLevels }, [resistanceLevels])

  const scope = getScopeFromSource(source)

  const levelsStorageKey = useMemo(() => {
    if (!symbol || !userId) return null
    return `price-levels:v2:${userId}:${symbol}:${scope}:${contractId ?? 'all'}`
  }, [symbol, userId, scope, contractId])

  // v1 fallback key for migration
  const v1StorageKey = useMemo(() => {
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
      const loadVersion = mutationVersionRef.current
      if (!varietyId) {
        loadFromLocalStorage()
        if (!cancelled) setLevelsLoaded(true)
        return
      }

      try {
        const levels = await api.getPriceLevels(varietyId, undefined, scope, contractId)
        if (!cancelled && loadVersion === mutationVersionRef.current) {
          updateLevelsFromData(levels)
          syncToLocalStorage(levels)
        }

        // v1 migration: if no levels found and current scope is continuous, try importing v1 data
        if (levels.length === 0 && scope === 'continuous' && levelsStorageKey && typeof window !== 'undefined') {
          const v1Raw = v1StorageKey ? window.localStorage.getItem(v1StorageKey) : null
          if (v1Raw) {
            const parsed = JSON.parse(v1Raw)
            const support = normalizeLevels(parsed.supportLevels)
            const resistance = normalizeLevels(parsed.resistanceLevels)
            for (const price of support) {
              await api.createPriceLevel(varietyId, 'support', formatPricePayload(price, pricePrecision), 'continuous').catch((err) => {
                captureMessage(`导入支撑位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'warning')
              })
            }
            for (const price of resistance) {
              await api.createPriceLevel(varietyId, 'resistance', formatPricePayload(price, pricePrecision), 'continuous').catch((err) => {
                captureMessage(`导入阻力位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'warning')
              })
            }
            const imported = await api.getPriceLevels(varietyId, undefined, scope, contractId)
            if (!cancelled && loadVersion === mutationVersionRef.current) {
              updateLevelsFromData(imported)
              syncToLocalStorage(imported)
            }
          }
        }
      } catch (err) {
        captureMessage(`加载价位标注失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
        if (!cancelled && loadVersion === mutationVersionRef.current) {
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
  }, [varietyId, scope, contractId, levelsStorageKey, v1StorageKey, loadFromLocalStorage, updateLevelsFromData, syncToLocalStorage])

  const addSupport = async (price: number) => {
    const promise = queueRef.current.then(async () => {
      const currentSupport = supportRef.current
      const currentResistance = resistanceRef.current
      if (!Number.isFinite(price) || currentSupport.includes(price)) return
      const mutationVersion = ++mutationVersionRef.current
      if (varietyId) {
        try {
          const created = await api.createPriceLevel(
            varietyId,
            'support',
            formatPricePayload(price, pricePrecision),
            scope,
            contractId,
          )
          const levels = await api.getPriceLevels(varietyId, undefined, scope, contractId)
          if (mutationVersion === mutationVersionRef.current) {
            const mergedLevels = levels.some((level) => level.id === created.id) ? levels : [...levels, created]
            updateLevelsFromData(mergedLevels)
            syncToLocalStorage(mergedLevels)
          }
          setLevelError(null)
          return
        } catch (err) {
          captureMessage(`添加支撑位失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
          setLevelError(`添加失败：${err instanceof Error ? err.message : '未知错误'}，已临时保存到本地。`)
        }
      }
      setSupportLevels((prev) => {
        const next = [...prev, price].sort((a, b) => a - b)
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
      const mutationVersion = ++mutationVersionRef.current
      if (varietyId) {
        try {
          const created = await api.createPriceLevel(
            varietyId,
            'resistance',
            formatPricePayload(price, pricePrecision),
            scope,
            contractId,
          )
          const levels = await api.getPriceLevels(varietyId, undefined, scope, contractId)
          if (mutationVersion === mutationVersionRef.current) {
            const mergedLevels = levels.some((level) => level.id === created.id) ? levels : [...levels, created]
            updateLevelsFromData(mergedLevels)
            syncToLocalStorage(mergedLevels)
          }
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
    const promise = queueRef.current.then(async () => {
      const mutationVersion = ++mutationVersionRef.current
      if (varietyId) {
        try {
          const levels = await api.getPriceLevels(varietyId, 'support', scope, contractId)
          const pl = levels.find((l) => Math.abs(Number(l.price) - price) < 0.0001)
          if (pl) {
            await api.deletePriceLevel(pl.id)
            captureMessage(`删除支撑位: 品种#${varietyId} @ ${price}`, 'info')
            const refreshed = await api.getPriceLevels(varietyId, undefined, scope, contractId)
            if (mutationVersion === mutationVersionRef.current) {
              updateLevelsFromData(refreshed)
              syncToLocalStorage(refreshed)
            }
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
    })
    queueRef.current = promise
    return promise
  }

  const removeResistance = async (price: number) => {
    const promise = queueRef.current.then(async () => {
      const mutationVersion = ++mutationVersionRef.current
      if (varietyId) {
        try {
          const levels = await api.getPriceLevels(varietyId, 'resistance', scope, contractId)
          const pl = levels.find((l) => Math.abs(Number(l.price) - price) < 0.0001)
          if (pl) {
            await api.deletePriceLevel(pl.id)
            captureMessage(`删除阻力位: 品种#${varietyId} @ ${price}`, 'info')
            const refreshed = await api.getPriceLevels(varietyId, undefined, scope, contractId)
            if (mutationVersion === mutationVersionRef.current) {
              updateLevelsFromData(refreshed)
              syncToLocalStorage(refreshed)
            }
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
    })
    queueRef.current = promise
    return promise
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
