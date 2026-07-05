'use client'

import { FileText, TrendingUp, AlertTriangle, BarChart3 } from 'lucide-react'
import type { StrategyCompilerData, StrategyDSL } from './backtest-types'

export default function StrategyResultCard({ result }: { result: Record<string, unknown> | null | undefined }) {
  const data = result as StrategyCompilerData | null
  if (!data || !data.dsl) return null

  const dsl = data.dsl

  // Map raw symbol codes to human-readable names
  const symbolNameMap: Record<string, string> = {
    rb: '螺纹钢',
    rb50: '螺纹钢(50)',
    rbX2: '螺纹钢(2倍)',
    hc: '热卷',
    i: '铁矿石',
    j: '焦炭',
    jm: '焦煤',
    fg: '玻璃',
    sa: '纯碱',
    ma: '甲醇',
    ta: 'PTA',
    pp: '聚丙烯',
    l: '塑料',
    v: 'PVC',
    ru: '橡胶',
    sp: '纸浆',
    fu: '燃料油',
    bu: '沥青',
    sc: '原油',
    au: '黄金',
    ag: '白银',
    cu: '铜',
    al: '铝',
    zn: '锌',
    ni: '镍',
    si: '工业硅',
    lc: '碳酸锂',
    sr: '白糖',
    cf: '棉花',
    oi: '菜油',
    p: '棕榈油',
    y: '豆油',
    m: '豆粕',
    a: '黄豆一号',
    rm: '菜粕',
    c: '玉米',
    cs: '玉米淀粉',
    jd: '鸡蛋',
    lh: '生猪',
    ap: '苹果',
    eg: '乙二醇',
    eb: '苯乙烯',
    pg: '液化气',
    ur: '尿素',
  }

  function mapSymbol(raw: string): string {
    return symbolNameMap[raw] || raw
  }

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/50 p-3">
      <div className="mb-2 flex items-center gap-2">
        <TrendingUp size={14} className="text-amber-400" />
        <span className="text-sm font-medium text-white">策略编译结果</span>
      </div>

      <div className="space-y-2 text-sm text-slate-300">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">名称</span>
          <span className="font-medium text-white">{dsl.name}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">品种</span>
          <span className="text-white">{dsl.universe.map(mapSymbol).join(', ')}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">方向</span>
          <span className={dsl.direction === 'long' ? 'text-red-400' : 'text-green-400'}>
            {dsl.direction === 'long' ? '做多' : '做空'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">周期</span>
          <span className="text-white">{dsl.timeframe === '1d' ? '日线' : dsl.timeframe === '1h' ? '小时线' : dsl.timeframe === '15m' ? '15分钟' : dsl.timeframe}</span>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <ConditionBlock title="入场条件" conditions={dsl.entry.conditions} />
        <ConditionBlock title="出场条件" conditions={dsl.exit.conditions} />
        <RiskBlock risk={dsl.risk} />
      </div>

      {/* 查看 JSON 按钮已移除 — 用户不需要看到内部数据结构 */}

    </div>
  )
}

function ConditionBlock({ title, conditions }: { title: string; conditions: Array<{ indicator: string; operator: string; indicator2?: string; value?: number }> }) {
  if (!conditions || conditions.length === 0) return null

  const operatorMap: Record<string, string> = {
    cross_above: '上穿',
    cross_below: '下穿',
    above: '突破',
    below: '跌破',
    greater_than: '大于',
    less_than: '小于',
    equal: '等于',
    between: '介于',
  }

  // Human-readable indicator labels
  const indicatorMap: Record<string, string> = {
    sma: '均线',
    ema: '指数均线',
    rsi: 'RSI',
    macd_dif: 'MACD快线',
    macd_dea: 'MACD慢线',
    macd: 'MACD',
    macd_bar: 'MACD柱',
    boll_upper: '布林上轨',
    boll_mid: '布林中轨',
    boll_lower: '布林下轨',
    atr: 'ATR',
    kdj_k: 'KDJ-K',
    kdj_d: 'KDJ-D',
    kdj_j: 'KDJ-J',
    cci: 'CCI',
    close: '收盘价',
    volume: '成交量',
  }

  function fmtInd(raw: string): string {
    if (indicatorMap[raw]) return indicatorMap[raw]
    const s = raw.match(/^sma(\d+)$/)
    if (s) return `${s[1]}日均线`
    const e = raw.match(/^ema(\d+)$/)
    if (e) return `${e[1]}日指数均线`
    const r = raw.match(/^rsi(\d+)$/)
    if (r) return `RSI(${r[1]})`
    const c = raw.match(/^cci(\d+)$/)
    if (c) return `CCI(${c[1]})`
    return raw
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-amber-400">
        <FileText size={10} />
        {title}
      </div>
      <div className="space-y-1">
        {conditions.map((cond, i) => (
          <div key={i} className="text-xs text-slate-300">
            <span className="font-medium text-white">{fmtInd(cond.indicator)}</span>
            {' '}
            <span className="text-slate-400">{operatorMap[cond.operator] || cond.operator}</span>
            {' '}
            {cond.indicator2 ? (
              <span className="font-medium text-white">{fmtInd(cond.indicator2)}</span>
            ) : cond.value !== undefined ? (
              <span className="font-medium text-white">{cond.value}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function RiskBlock({ risk }: { risk: StrategyDSL['risk'] }) {
  const typeMap: Record<string, string> = {
    fixed: '固定',
    pct: '百分比',
    atr: 'ATR',
    trailing: '移动',
  }

  function fmtRisk(t: string, v: number): string {
    const label = typeMap[t] || t
    if (t === 'pct') return `${label} (${v}%)`
    return `${label} (${v})`
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-red-400">
        <AlertTriangle size={10} />
        风控参数
      </div>
      <div className="space-y-1 text-xs text-slate-300">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">仓位</span>
          <span>{fmtRisk(risk.position_size.type, risk.position_size.value)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">止损</span>
          <span>{fmtRisk(risk.stop_loss.type, risk.stop_loss.value)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">止盈</span>
          <span>{fmtRisk(risk.take_profit.type, risk.take_profit.value)}</span>
        </div>
      </div>
    </div>
  )
}
