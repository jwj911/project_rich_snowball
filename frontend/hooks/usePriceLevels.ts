import { useState, useEffect, useCallback, useMemo } from 'react'
import { api, PriceLevel } from '@/lib/api'

export function usePriceLevels(varietyId: number | null, userId: number | null, productId: number) {
  const [supportLevels, setSupportLevels] = useState<number[]>([])
  const [resistanceLevels, setResistanceLevels] = useState<number[]>([])
  const [levelsLoaded, setLevelsLoaded] = useState(false)

  const levelsStorageKey = useMemo(() => {
    if (!Number.isFinite(productId) || !userId) return null
    return `price-levels:v1:${userId}:${productId}`
  }, [productId, userId])

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
                console.error('导入支撑位失败:', err)
              })
            }
            for (const price of resistance) {
              await api.createPriceLevel(varietyId, 'resistance', price.toFixed(2)).catch((err) => {
                console.error('导入阻力位失败:', err)
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
        console.error('加载价位标注失败:', err)
        if (!cancelled) loadFromLocalStorage()
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
    if (!Number.isFinite(price) || supportLevels.includes(price)) return
    if (varietyId) {
      try {
        await api.createPriceLevel(varietyId, 'support', price.toFixed(2))
        const levels = await api.getPriceLevels(varietyId)
        updateLevelsFromData(levels)
        syncToLocalStorage(levels)
        return
      } catch (err) {
        console.error('添加支撑位失败:', err)
        return
      }
    }
    setSupportLevels((levels) => [...levels, price].sort((a, b) => a - b))
  }

  const addResistance = async (price: number) => {
    if (!Number.isFinite(price) || resistanceLevels.includes(price)) return
    if (varietyId) {
      try {
        await api.createPriceLevel(varietyId, 'resistance', price.toFixed(2))
        const levels = await api.getPriceLevels(varietyId)
        updateLevelsFromData(levels)
        syncToLocalStorage(levels)
        return
      } catch (err) {
        console.error('添加阻力位失败:', err)
        return
      }
    }
    setResistanceLevels((levels) => [...levels, price].sort((a, b) => b - a))
  }

  const removeSupport = async (price: number) => {
    if (varietyId) {
      try {
        const levels = await api.getPriceLevels(varietyId, 'support')
        const pl = levels.find((l) => Math.abs(Number(l.price) - price) < 0.0001)
        if (pl) {
          await api.deletePriceLevel(pl.id)
          const refreshed = await api.getPriceLevels(varietyId)
          updateLevelsFromData(refreshed)
          syncToLocalStorage(refreshed)
        }
        return
      } catch (err) {
        console.error('删除支撑位失败:', err)
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
          const refreshed = await api.getPriceLevels(varietyId)
          updateLevelsFromData(refreshed)
          syncToLocalStorage(refreshed)
        }
        return
      } catch (err) {
        console.error('删除阻力位失败:', err)
        return
      }
    }
    setResistanceLevels((levels) => levels.filter((level) => level !== price))
  }

  return {
    supportLevels,
    resistanceLevels,
    levelsLoaded,
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
