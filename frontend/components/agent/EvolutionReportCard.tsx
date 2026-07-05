'use client'

import { useState } from 'react'

interface EvolutionReportCardProps {
  answer: string
  data?: Record<string, unknown> | null
}

/**
 * 渲染策略进化 Agent 的 Markdown 报告。
 *
 * 提供快速指标概览和可折叠的完整报告文本。
 */
export default function EvolutionReportCard({ answer, data }: EvolutionReportCardProps) {
  const [expanded, setExpanded] = useState(false)

  const bestFitness = typeof data?.best_fitness === 'number' ? data.best_fitness : null
  const factorsUsed = typeof data?.factors_used === 'number' ? data.factors_used : null
  const regime = typeof data?.regime === 'string' ? data.regime : null
  const symbol = typeof data?.symbol === 'string' ? data.symbol : null

  // 从 answer markdown 中提取关键行
  const lines = answer.split('\n').filter(Boolean)
  const keyLines = lines.filter(
    (l) =>
      l.includes('最优适应度') ||
      l.includes('年化收益') ||
      l.includes('Sharpe') ||
      l.includes('最大回撤') ||
      l.includes('胜率') ||
      l.includes('盈亏比') ||
      l.includes('IS/OOS 一致性') ||
      l.includes('进化代数') ||
      l.includes('种群'),
  )

  return (
    <div className="my-3 rounded-lg border border-slate-800 bg-surface p-4">
      {/* 摘要条 */}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        {symbol && (
          <span className="rounded bg-amber-900/50 px-2 py-0.5 font-mono text-amber-400">
            {symbol}
          </span>
        )}
        {regime && (
          <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-400">
            市场: {regime}
          </span>
        )}
        {bestFitness !== null && (
          <span className="rounded bg-emerald-900/50 px-2 py-0.5 text-emerald-400">
            适应度: {bestFitness.toFixed(1)}
          </span>
        )}
        {factorsUsed !== null && (
          <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-400">
            {factorsUsed} 因子
          </span>
        )}
      </div>

      {/* 关键指标 */}
      {keyLines.length > 0 && (
        <div className="mb-3 space-y-0.5 text-sm text-slate-300">
          {keyLines.slice(0, 6).map((line, i) => (
            <div key={i} className="flex items-baseline gap-2">
              <span className="text-amber-500">•</span>
              <span>{line.replace(/^[-#*\s]+/, '').trim()}</span>
            </div>
          ))}
        </div>
      )}

      {/* 可折叠完整报告 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-amber-500 hover:text-amber-400 transition"
      >
        {expanded ? '收起完整报告 ▲' : '展开完整报告 ▼'}
      </button>

      {expanded && (
        <div className="mt-3 max-h-96 overflow-y-auto rounded-md bg-slate-950 p-4 text-xs leading-relaxed text-slate-300 font-mono whitespace-pre-wrap border border-slate-800">
          {answer}
        </div>
      )}
    </div>
  )
}
