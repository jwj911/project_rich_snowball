import {
  BarChart3,
  Database,
  Dna,
  FileCode2,
  GitMerge,
  Search,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'

export type AgentTypeKey =
  | 'auto'
  | 'data'
  | 'data_quality'
  | 'tech_analysis'
  | 'risk_management'
  | 'analysis_pipeline'
  | 'backtest'
  | 'factor_mining'
  | 'strategy_compiler'
  | 'parameter_optimizer'
  | 'strategy_evolution'
  | 'trader'

export interface AgentTypeMeta {
  key: AgentTypeKey
  label: string
  shortLabel: string
  description: string
  icon: LucideIcon
  quickPrompts: string[]
}

export const AGENT_TYPES: AgentTypeMeta[] = [
  {
    key: 'auto',
    label: '智能模式',
    shortLabel: '智能',
    description: '自动识别意图并路由到最佳 Agent（推荐首选）',
    icon: Sparkles,
    quickPrompts: [
      '白银目前适合做多还是做空？',
      '帮我分析一下螺纹钢',
      '螺纹钢5日上穿20日均线策略回测一下',
      '评估一下动量因子在黑色系的表现',
    ],
  },
  {
    key: 'data',
    label: '数据助手',
    shortLabel: '数据',
    description: '实时行情、品种信息、K线查询（纯数据查询，不做分析）',
    icon: Database,
    quickPrompts: [
      '白银主力合约最新价格是多少',
      '列出所有有色金属品种',
      '黄金近 20 日 K 线数据',
      '当前市场状态汇总',
    ],
  },
  {
    key: 'data_quality',
    label: '数据质检',
    shortLabel: '质检',
    description: '数据完整性检查、缺口检测与数据质量报告',
    icon: ShieldCheck,
    quickPrompts: [
      '检查白银近30日数据完整性',
      '黄金数据有没有缺口',
      '数据质量报告',
      '最近哪些品种数据异常',
    ],
  },
  {
    key: 'tech_analysis',
    label: '技术分析',
    shortLabel: '技术',
    description: '基于 MACD、RSI、KDJ、布林带等指标做技术面研判',
    icon: TrendingUp,
    quickPrompts: [
      '白银日线技术面分析',
      '黄金技术面如何？适合做多还是做空？',
      '铜的走势技术判断，给个方向',
      '原油期货技术分析',
    ],
  },
  {
    key: 'risk_management',
    label: '风控管理',
    shortLabel: '风控',
    description: '仓位管理、止损止盈计算、回撤控制与风险评估',
    icon: Shield,
    quickPrompts: [
      '白银做多风控方案，我账户10万',
      '黄金做空仓位怎么控制',
      '原油 50000 元做空风控',
      '铜的止损止盈怎么设',
    ],
  },
  {
    key: 'analysis_pipeline',
    label: '完整分析',
    shortLabel: '分析',
    description: '综合数据查询 + 技术研判 + 风控评估的完整分析流水线',
    icon: GitMerge,
    quickPrompts: [
      '对白银做完整分析',
      '综合研判黄金走势，多还是空？',
      '铜的全方位分析报告',
      '原油多维度分析',
    ],
  },
  {
    key: 'backtest',
    label: '策略回测',
    shortLabel: '回测',
    description: '将自然语言策略转为可执行代码，做历史回测与绩效评分',
    icon: BarChart3,
    quickPrompts: [
      '白银 5 日上穿 20 日均线做多策略回测',
      '黄金 10 和 30 日均线策略回测',
      '铜 20 万资金 2 手均线回测',
      '原油做空 5/20 均线回测',
    ],
  },
  {
    key: 'factor_mining',
    label: '因子评估',
    shortLabel: '因子',
    description: '因子 IC、RankIC、分层回测与多空收益分析',
    icon: Search,
    quickPrompts: [
      '评估 "close / ts_delay(close, 5) - 1" 在黑色系的表现',
      '评估 "ts_rank(close, 20)" 在白银的表现',
      '评估螺纹钢动量因子',
      '评估 "ts_corr(close, volume, 10)" 在能源化工的表现',
    ],
  },
  {
    key: 'strategy_compiler',
    label: '策略编译',
    shortLabel: '编译',
    description: '将自然语言交易想法转化为可执行的策略 DSL 代码',
    icon: FileCode2,
    quickPrompts: [
      '把"5日上穿20日做多"编译成策略',
      '编译一个MACD金叉策略',
      '生成均线交叉策略代码',
      '将突破策略转为DSL',
    ],
  },
  {
    key: 'parameter_optimizer',
    label: '参数优化',
    shortLabel: '优化',
    description: '网格搜索、参数调优，帮现有策略找到最佳参数组合',
    icon: SlidersHorizontal,
    quickPrompts: [
      '优化白银均线策略的参数',
      '网格搜索黄金最佳止损止盈',
      '参数优化 MACD 策略',
      '铜策略参数调优',
    ],
  },
  {
    key: 'strategy_evolution',
    label: '策略进化',
    shortLabel: '进化',
    description: '遗传算法自动挖掘交易策略（输入品种名即可，如"进化白银策略"，不要问"做多还是做空"类问题）',
    icon: Dna,
    quickPrompts: [
      '进化一个白银日线策略',
      '对黄金策略进行遗传优化',
      '进化一个铜的多因子策略',
      '发现新的原油交易因子',
    ],
  },
  {
    key: 'trader',
    label: '交易员',
    shortLabel: '交易',
    description: '多周期图表演判 → 输出具体交易计划：方向、点位、止损止盈、仓位（做多做空的唯一选择）',
    icon: Target,
    quickPrompts: [
      '白银目前走势如何？适合做多还是做空？',
      '帮我看看螺纹钢今天的日内波段机会',
      '给出黄金未来两周的趋势交易计划',
      '沪铜现在适合入场吗？止损怎么设？',
    ],
  },
]

export const AGENT_TYPE_MAP: Record<AgentTypeKey, AgentTypeMeta> = Object.fromEntries(
  AGENT_TYPES.map((t) => [t.key, t])
) as Record<AgentTypeKey, AgentTypeMeta>

export const CHAT_MODES: AgentTypeKey[] = AGENT_TYPES.map((t) => t.key)
