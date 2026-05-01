'use client'

import React, { useState, useMemo, useEffect, useRef } from 'react'

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

const generateMockKline = (basePrice: number, count: number = 60): KlineData[] => {
    let price = basePrice
    const now = Date.now()
    const data: KlineData[] = []
    for (let i = count - 1; i >= 0; i--) {
        const change = (Math.random() - 0.5) * basePrice * 0.02
        const open = price
        const close = price + change
        const high = Math.max(open, close) + Math.random() * basePrice * 0.01
        const low = Math.min(open, close) - Math.random() * basePrice * 0.01
        const volume = Math.floor(Math.random() * 100000) + 50000
        data.push({
            time: new Date(now - i * 3600 * 1000).toLocaleString(),
            open,
            high,
            low,
            close,
            volume
        })
        price = close
    }
    return data
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
    
    const data = useMemo<KlineData[]>(() => externalData.length > 0 ? externalData : generateMockKline(450, 80), [externalData])
    const [hoverIndex, setHoverIndex] = useState<number | null>(null)
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
        const prices = data.flatMap(d => [d.high, d.low])
        let minP = Math.min(...prices)
        let maxP = Math.max(...prices)
        
        const range = maxP - minP
        minP -= range * 0.05
        maxP += range * 0.05
        
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
                            const rect = chartRef.current?.getBoundingClientRect()
                            if (rect) {
                                const x = e.clientX - rect.left - yAxisWidth
                                const idx = Math.floor(x / (candleWidth + candleGap))
                                if (idx >= 0 && idx < data.length) setHoverIndex(idx)
                            }
                        }}
                        onMouseLeave={() => setHoverIndex(null)}
                        onContextMenu={(e) => {
                            e.preventDefault()
                            if (hoverIndex !== null) {
                                const price = data[hoverIndex]?.close
                                if (price && onAddResistance && onAddSupport) {
                                    if (confirm(`在 ${price.toFixed(2)} 添加支撑位(S)或阻力位(R)?\n确定=阻力位，取消=支撑位`)) {
                                        onAddResistance(price)
                                    } else {
                                        onAddSupport(price)
                                    }
                                }
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
                            const bodyColor = isUp ? "rgba(239,68,68,0.2)" : "rgba(34,197,94,0.2)"
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
                            const maxVol = Math.max(...data.map(d => d.volume))
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
                </div>
            </div>
        </div>
    )
}
