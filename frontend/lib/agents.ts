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
    description: '自动识别意图并路由到最佳 Agent',
    icon: Sparkles,
    quickPrompts: [
      '帮我分析一下螺纹钢',
      '黄金目前适合做多还是做空',
      '螺纹钢5日上穿20日均线策略回测一下',
      '评估一下动量因子',
    ],
  },
  {
    key: 'data',
    label: '数据助手',
    shortLabel: '数据',
    description: '实时行情、品种信息、K 线查询',
    icon: Database,
    quickPrompts: [
      '螺纹钢最新价格是多少',
      '列出所有有色金属品种',
      '黄金近 20 日 K 线数据',
      '当前市场状态如何',
    ],
  },
  {
    key: 'data_quality',
    label: '数据质检',
    shortLabel: '质检',
    description: '数据完整性检查、缺口检测与质量报告',
    icon: ShieldCheck,
    quickPrompts: [
      '检查螺纹钢近30日数据完整性',
      '黄金数据有没有缺口',
      '数据质量报告',
      '最近哪些品种数据异常',
    ],
  },
  {
    key: 'tech_analysis',
    label: '技术分析',
    shortLabel: '技术',
    description: 'MACD、RSI、KDJ、布林带等经典指标综合研判',
    icon: TrendingUp,
    quickPrompts: [
      '分析螺纹钢日线技术面',
      '黄金技术面如何？',
      '铜的走势技术判断',
      '原油期货技术分析',
    ],
  },
  {
    key: 'risk_management',
    label: '风控管理',
    shortLabel: '风控',
    description: '仓位管理、止损止盈、回撤控制与风险评估',
    icon: Shield,
    quickPrompts: [
      '螺纹钢做多风控方案',
      '黄金做空仓位怎么控制',
      '原油 5000 元做空风控',
      '铜的止损止盈怎么设',
    ],
  },
  {
    key: 'analysis_pipeline',
    label: '完整分析',
    shortLabel: '分析',
    description: '综合数据查询、技术研判与风控评估的完整流水线',
    icon: GitMerge,
    quickPrompts: [
      '对螺纹钢做完整分析',
      '综合研判黄金走势',
      '铜的全方位分析报告',
      '原油多维度分析',
    ],
  },
  {
    key: 'backtest',
    label: '策略回测',
    shortLabel: '回测',
    description: '自然语言策略解析、历史回测与绩效评分',
    icon: BarChart3,
    quickPrompts: [
      '螺纹钢 5 日上穿 20 日均线回测',
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
      '评估 "ts_rank(close, 20)" 在有色的表现',
      '评估螺纹钢动量因子',
      '评估 "ts_corr(close, volume, 10)" 在能源化工的表现',
    ],
  },
  {
    key: 'strategy_compiler',
    label: '策略编译',
    shortLabel: '编译',
    description: '将自然语言交易想法转化为可执行的策略 DSL',
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
    description: '网格搜索、参数调优与策略性能优化',
    icon: SlidersHorizontal,
    quickPrompts: [
      '优化螺纹钢均线策略参数',
      '网格搜索黄金最佳止损止盈',
      '参数优化 MACD 策略',
      '铜策略参数调优',
    ],
  },
  {
    key: 'strategy_evolution',
    label: '策略进化',
    shortLabel: '进化',
    description: '市场状态识别、因子发现与遗传算法策略进化',
    icon: Dna,
    quickPrompts: [
      '进化一个螺纹钢策略',
      '对黄金策略进行遗传优化',
      '策略进化 铜',
      '发现新的原油交易因子',
    ],
  },
  {
    key: 'trader',
    label: '交易员',
    shortLabel: '交易',
    description: '多周期图表研判，输出具体交易计划与风控方案',
    icon: Target,
    quickPrompts: [
      '帮我看看 RB2501 今天的日内波段机会',
      'CU2501 现在适合剥头皮吗？',
      '给出 P2501 未来两周的趋势交易计划',
      '帮我制定一个豆粕的交易系统',
    ],
  },
]

export const AGENT_TYPE_MAP: Record<AgentTypeKey, AgentTypeMeta> = Object.fromEntries(
  AGENT_TYPES.map((t) => [t.key, t])
) as Record<AgentTypeKey, AgentTypeMeta>

export const CHAT_MODES: AgentTypeKey[] = AGENT_TYPES.map((t) => t.key)
