'use client'

import React, { useState, useMemo, useEffect, useRef } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import { LineChart } from 'lucide-react'

interface KlineData {
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

interface KlineChartProps {
    data: KlineData[]
    symbol: string
    supportLevels?: number[]
    resistanceLevels?: number[]
    onAddSupport?: (price: number) => void
    onAddResistance?: (price: number) => void
    onRemoveSupport?: (price: number) => void
    onRemoveResistance?: (price: number) => void
}

interface AnnotationMenu {
    x: number
    y: number
    price: number
}

export default function KlineChart({ 
    data: externalData, 
    symbol, 
    supportLevels = [],
    resistanceLevels = [],
    onAddSupport,
    onAddResistance,
    onRemoveSupport,
    onRemoveResistance
}: KlineChartProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<SVGSVGElement>(null)
    
    const data = useMemo<KlineData[]>(() => {
        return externalData.filter((item) => {
            return [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite)
                && item.high >= item.low
                && item.high >= Math.max(item.open, item.close)
                && item.low <= Math.min(item.open, item.close)
        })
    }, [externalData])
    const [hoverIndex, setHoverIndex] = useState<number | null>(null)
    const [annotationMenu, setAnnotationMenu] = useState<AnnotationMenu | null>(null)
    const [width, setWidth] = useState(800)
    
    useEffect(() => {
        if (containerRef.current) {
            const update = () => setWidth(containerRef.current?.clientWidth || 800)
            update()
            window.addEventListener('resize', update)
            return () => window.removeEventListener('resize', update)
        }
    }, [])
    
    const { priceRange, minPrice, maxPrice, candleWidth, candleGap } = useMemo(() => {
        if (data.length === 0) {
            return {
                priceRange: 1,
                minPrice: 0,
                maxPrice: 1,
                candleWidth: 8,
                candleGap: 2
            }
        }

        const prices = data.flatMap(d => [d.high, d.low])
        let minP = Math.min(...prices)
        let maxP = Math.max(...prices)
        
        const rawRange = maxP - minP
        const padding = rawRange > 0 ? rawRange * 0.05 : Math.max(Math.abs(maxP) * 0.01, 1)
        minP -= padding
        maxP += padding
        
        const w = Math.max(8, Math.floor((width - 80) / data.length * 0.7))
        const g = Math.max(1, Math.floor((width - 80) / data.length * 0.3))
        
        return {
            priceRange: maxP - minP,
            minPrice: minP,
            maxPrice: maxP,
            candleWidth: w,
            candleGap: g
        }
    }, [data, width])
    
    const height = 450
    const volumeHeight = 80
    const yAxisWidth = 60
    
    const scalePrice = (p: number) => height - ((p - minPrice) / priceRange) * height
    const scaleX = (i: number) => yAxisWidth + i * (candleWidth + candleGap)
    const getIndexFromClientX = (clientX: number) => {
        const rect = chartRef.current?.getBoundingClientRect()
        if (!rect) return null

        const x = clientX - rect.left - yAxisWidth
        const idx = Math.floor(x / (candleWidth + candleGap))
        return idx >= 0 && idx < data.length ? idx : null
    }

    const closeAnnotationMenu = () => setAnnotationMenu(null)

    const addSupportFromMenu = () => {
        if (annotationMenu && onAddSupport) {
            onAddSupport(annotationMenu.price)
        }
        closeAnnotationMenu()
    }

    const addResistanceFromMenu = () => {
        if (annotationMenu && onAddResistance) {
            onAddResistance(annotationMenu.price)
        }
        closeAnnotationMenu()
    }

    if (data.length === 0) {
        return (
            <div ref={containerRef} className="w-full rounded-lg border border-[#2a2e39] bg-[#131722] p-4">
                <EmptyState
                    icon={LineChart}
                    title="暂无 K 线数据"
                    description="当前品种还没有可展示的 K 线数据，等待数据同步后会自动展示。"
                    className="border-[#2a2e39] bg-[#1e222d]"
                />
            </div>
        )
    }

    return (
        <div ref={containerRef} className="w-full bg-[#131722] rounded-lg border border-[#2a2e39] overflow-hidden select-none">
            <div className="relative" style={{ height: height + volumeHeight + 30 }}>
                <div className="absolute inset-0 top-0">
                    <div className="flex justify-between px-3 py-2 text-xs text-gray-400 border-b border-[#2a2e39]">
                        <span className="text-white font-semibold">{symbol}</span>
                        <span>最新: <span className={data[data.length - 1]?.close > data[0]?.open ? "text-red-400" : "text-green-400"}>{data[data.length - 1]?.close.toFixed(2)}</span></span>
                        <span>开: {data[0]?.open.toFixed(2)}</span>
                        <span>高: {Math.max(...data.map(d => d.high)).toFixed(2)}</span>
                        <span>低: {Math.min(...data.map(d => d.low)).toFixed(2)}</span>
                    </div>
                    
                    <svg 
                        ref={chartRef}
                        className="w-full cursor-crosshair" 
                        viewBox={`0 0 ${width} ${height + volumeHeight}`}
                        onMouseMove={(e) => {
                            const idx = getIndexFromClientX(e.clientX)
                            if (idx !== null) {
                                setHoverIndex(idx)
                            }
                        }}
                        onMouseLeave={() => setHoverIndex(null)}
                        onContextMenu={(e) => {
                            e.preventDefault()
                            const idx = getIndexFromClientX(e.clientX) ?? hoverIndex
                            const price = idx !== null ? data[idx]?.close : null
                            const rect = containerRef.current?.getBoundingClientRect()

                            if (price && rect && onAddResistance && onAddSupport) {
                                setAnnotationMenu({
                                    x: Math.min(Math.max(e.clientX - rect.left, 12), Math.max(width - 172, 12)),
                                    y: Math.min(Math.max(e.clientY - rect.top, 48), height + volumeHeight - 96),
                                    price,
                                })
                            }
                        }}
                    >
                        {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
                            const y = 30 + ratio * height
                            const price = maxPrice - ratio * priceRange
                            return (
                                <React.Fragment key={i}>
                                    <line x1={yAxisWidth} x2={width} y1={y} y2={y} stroke="#2a2e39" strokeDasharray="4,4" />
                                    <text x={10} y={y + 4} fill="#787b86" fontSize="10" fontFamily="'JetBrains Mono', monospace">{price.toFixed(2)}</text>
                                </React.Fragment>
                            )
                        })}
                        
                        {supportLevels.map((level, i) => (
                            <g key={`s-${i}`}>
                                <line x1={yAxisWidth} x2={width} y1={scalePrice(level)} y2={scalePrice(level)} stroke="#22c55e" strokeWidth="1" strokeDasharray="4,2" />
                                <rect x={width - 100} y={scalePrice(level)-10} width="80" height="20" fill="#22c55e" rx="4" className="cursor-pointer opacity-80 hover:opacity-100" 
                                      onClick={() => onRemoveSupport && onRemoveSupport(level)} />
                                <text x={width - 60} y={scalePrice(level)+4} textAnchor="middle" fill="white" fontSize="11" fontWeight="bold" fontFamily="'JetBrains Mono', monospace">
                                    {level.toFixed(2)}
                                </text>
                            </g>
                        ))}
                        
                        {resistanceLevels.map((level, i) => (
                            <g key={`r-${i}`}>
                                <line x1={yAxisWidth} x2={width} y1={scalePrice(level)} y2={scalePrice(level)} stroke="#ef4444" strokeWidth="1" strokeDasharray="4,2" />
                                <rect x={width - 100} y={scalePrice(level)-10} width="80" height="20" fill="#ef4444" rx="4" className="cursor-pointer opacity-80 hover:opacity-100" 
                                      onClick={() => onRemoveResistance && onRemoveResistance(level)} />
                                <text x={width - 60} y={scalePrice(level)+4} textAnchor="middle" fill="white" fontSize="11" fontWeight="bold" fontFamily="'JetBrains Mono', monospace">
                                    {level.toFixed(2)}
                                </text>
                            </g>
                        ))}
                        
                        {data.map((candle, i) => {
                            const isUp = candle.close >= candle.open
                            const color = isUp ? "#ef4444" : "#22c55e"
                            const yLow = scalePrice(candle.low)
                            const yHigh = scalePrice(candle.high)
                            const yOpen = scalePrice(candle.open)
                            const yClose = scalePrice(candle.close)
                            const x = scaleX(i)
                            const centerX = x + candleWidth / 2
                            return (
                                <g key={i}>
                                    <line x1={centerX} x2={centerX} y1={yLow} y2={yHigh} stroke={color} strokeWidth="1" />
                                    <rect x={x} y={Math.min(yOpen, yClose)} width={candleWidth} height={Math.max(1, Math.abs(yClose - yOpen))} fill={isUp ? "transparent" : color} stroke={color} rx="1" />
                                </g>
                            )
                        })}
                        
                        {hoverIndex !== null && (
                            <>
                                <line x1={scaleX(hoverIndex)} x2={scaleX(hoverIndex)} y1="30" y2={height} stroke="#787b86" strokeWidth="1" strokeDasharray="3,3" />
                                <line x1={yAxisWidth} x2={width} y1={scalePrice(data[hoverIndex]?.close)} y2={scalePrice(data[hoverIndex]?.close)} stroke="#787b86" strokeWidth="1" strokeDasharray="3,3" />
                            </>
                        )}
                        
                        {hoverIndex !== null && (
                            <text x={width - 10} y={scalePrice(data[hoverIndex].close) + 4} fill="white" fontSize="12" textAnchor="end" fontFamily="'JetBrains Mono', monospace">
                                {data[hoverIndex].close.toFixed(2)}
                            </text>
                        )}

                        <line x1={yAxisWidth} x2={width} y1={height} y2={height} stroke="#2a2e39" />
                        
                        {data.map((candle, i) => {
                            const isUp = candle.close >= candle.open
                            const color = isUp ? "#ef4444" : "#22c55e"
                            const x = scaleX(i)
                            const maxVol = Math.max(1, ...data.map(d => d.volume))
                            const h = (candle.volume / maxVol) * (volumeHeight - 20)
                            return (
                                <rect key={`v-${i}`} x={x} y={height + volumeHeight - h} width={candleWidth} height={h} fill={color} opacity="0.4" rx="2" />
                            )
                        })}
                    </svg>

                    {hoverIndex !== null && data[hoverIndex] && (
                        <div className="absolute top-10 right-4 bg-[#1e222d] border border-[#2a2e39] rounded-lg shadow-lg p-3 text-xs z-10">
                            <div className="grid grid-cols-2 gap-2">
                                <div className="text-gray-400">时间</div>
                                <div className="text-white">{data[hoverIndex].time}</div>
                                <div className="text-gray-400">开盘</div>
                                <div className="text-white font-mono">{data[hoverIndex].open.toFixed(2)}</div>
                                <div className="text-gray-400">最高</div>
                                <div className="text-red-400 font-mono">{data[hoverIndex].high.toFixed(2)}</div>
                                <div className="text-gray-400">最低</div>
                                <div className="text-green-400 font-mono">{data[hoverIndex].low.toFixed(2)}</div>
                                <div className="text-gray-400">收盘</div>
                                <div className="text-white font-mono">{data[hoverIndex].close.toFixed(2)}</div>
                                <div className="text-gray-400">成交量</div>
                                <div className="text-white font-mono">{data[hoverIndex].volume.toLocaleString()}</div>
                            </div>
                        </div>
                    )}

                    {annotationMenu && (
                        <div
                            className="absolute z-20 w-40 rounded-lg border border-[#2a2e39] bg-[#1e222d] p-2 text-xs shadow-xl"
                            style={{ left: annotationMenu.x, top: annotationMenu.y }}
                        >
                            <div className="mb-2 border-b border-[#2a2e39] pb-2 font-mono text-slate-200">
                                {annotationMenu.price.toFixed(2)}
                            </div>
                            <button
                                type="button"
                                onClick={addSupportFromMenu}
                                className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-green-300 transition hover:bg-green-400/10"
                            >
                                添加支撑位
                                <span className="h-2 w-2 rounded-full bg-green-400" />
                            </button>
                            <button
                                type="button"
                                onClick={addResistanceFromMenu}
                                className="mt-1 flex w-full items-center justify-between rounded px-2 py-2 text-left text-red-300 transition hover:bg-red-400/10"
                            >
                                添加阻力位
                                <span className="h-2 w-2 rounded-full bg-red-400" />
                            </button>
                            <button
                                type="button"
                                onClick={closeAnnotationMenu}
                                className="mt-1 w-full rounded px-2 py-2 text-left text-slate-400 transition hover:bg-slate-700/40 hover:text-slate-200"
                            >
                                取消
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
