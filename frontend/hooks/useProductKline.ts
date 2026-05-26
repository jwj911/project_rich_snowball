'use client'

import { useEffect, useMemo, useState } from 'react'
import { FutContract, KlineData, api } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'
import { KlinePeriod, KlineSource, loadKlineBySource } from '@/lib/kline'

interface UseProductKlineResult {
  klineData: KlineData[]
  contracts: FutContract[]
  selectedContractId: number | null
  selectedContract: FutContract | null
  selectedKlinePeriod: KlinePeriod
  displayedKlinePeriod: KlinePeriod
  selectedKlineSource: KlineSource
  displayedKlineSource: KlineSource
  klineNotice: string | null
  isKlineLoading: boolean
  isContractsLoading: boolean
  setSelectedContractId: (contractId: number | null) => void
  setSelectedKlinePeriod: (period: KlinePeriod) => void
  setSelectedKlineSource: (source: KlineSource) => void
}

export function useProductKline(
  symbol: string | undefined,
  enabled: boolean,
  varietyId?: number | null,
): UseProductKlineResult {
  const [klineData, setKlineData] = useState<KlineData[]>([])
  const [contracts, setContracts] = useState<FutContract[]>([])
  const [selectedContractId, setSelectedContractId] = useState<number | null>(null)
  const [selectedKlinePeriod, setSelectedKlinePeriod] = useState<KlinePeriod>('1d')
  const [displayedKlinePeriod, setDisplayedKlinePeriod] = useState<KlinePeriod>('1d')
  const [selectedKlineSource, setSelectedKlineSource] = useState<KlineSource>('continuous')
  const [displayedKlineSource, setDisplayedKlineSource] = useState<KlineSource>('continuous')
  const [klineNotice, setKlineNotice] = useState<string | null>(null)
  const [isKlineLoading, setIsKlineLoading] = useState(false)
  const [isContractsLoading, setIsContractsLoading] = useState(false)

  const selectedContract = useMemo(
    () => contracts.find((contract) => contract.id === selectedContractId) ?? null,
    [contracts, selectedContractId],
  )

  useEffect(() => {
    if (!enabled || !varietyId) {
      setContracts([])
      setSelectedContractId(null)
      return
    }

    let cancelled = false
    const abortController = new AbortController()
    setIsContractsLoading(true)

    api.getContracts(varietyId, { limit: 200 }, { signal: abortController.signal })
      .then((rows) => {
        if (cancelled) return
        setContracts(rows)
        setSelectedContractId((current) => {
          if (current && rows.some((contract) => contract.id === current)) return current
          return rows[0]?.id ?? null
        })
      })
      .catch((err) => {
        if (cancelled || abortController.signal.aborted) return
        captureMessage(
          `合约列表加载失败: varietyId=${varietyId}, ${err instanceof Error ? err.message : '未知错误'}`,
          'error',
        )
        setContracts([])
        setSelectedContractId(null)
      })
      .finally(() => {
        if (!cancelled) setIsContractsLoading(false)
      })

    return () => {
      cancelled = true
      abortController.abort()
    }
  }, [enabled, varietyId])

  useEffect(() => {
    if (!symbol || !enabled) return
    if (selectedKlineSource === 'single' && !selectedContractId) {
      setKlineData([])
      setDisplayedKlinePeriod(selectedKlinePeriod)
      setDisplayedKlineSource(selectedKlineSource)
      setKlineNotice(isContractsLoading ? '正在加载合约列表...' : '当前品种暂无可选合约。')
      return
    }

    let cancelled = false
    const abortController = new AbortController()
    setIsKlineLoading(true)
    setKlineNotice(null)

    loadKlineBySource(symbol, selectedKlineSource, selectedKlinePeriod, {
      contractId: selectedContractId,
      contractCode: selectedContract?.ts_code ?? selectedContract?.symbol ?? null,
      signal: abortController.signal,
    })
      .then((kline) => {
        if (cancelled) return
        setKlineData(kline.rows)
        setDisplayedKlinePeriod(kline.period)
        setDisplayedKlineSource(selectedKlineSource)
        setKlineNotice(kline.notice)
      })
      .catch((err) => {
        if (cancelled || abortController.signal.aborted) return
        setKlineData([])
        setDisplayedKlinePeriod(selectedKlinePeriod)
        setDisplayedKlineSource(selectedKlineSource)
        setKlineNotice(err instanceof Error ? err.message : 'K 线数据加载失败')
      })
      .finally(() => {
        if (!cancelled) {
          setIsKlineLoading(false)
        }
      })

    return () => {
      cancelled = true
      abortController.abort()
    }
  }, [
    enabled,
    isContractsLoading,
    selectedContract,
    selectedContractId,
    selectedKlinePeriod,
    selectedKlineSource,
    symbol,
  ])

  return {
    klineData,
    contracts,
    selectedContractId,
    selectedContract,
    selectedKlinePeriod,
    displayedKlinePeriod,
    selectedKlineSource,
    displayedKlineSource,
    klineNotice,
    isKlineLoading,
    isContractsLoading,
    setSelectedContractId,
    setSelectedKlinePeriod,
    setSelectedKlineSource,
  }
}
