import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useFailRateTrend } from '@/hooks/useInspectionData'
import type { FailRateTrendPoint } from '@/types/inspection'

const MONTHLY_DEMO_DATA: FailRateTrendPoint[] = [
  { key: '2026-01', label: '1월', totalCount: 132, inspectedCount: 124, passCount: 116, failCount: 8, skippedCount: 8, failRate: 6.45 },
  { key: '2026-02', label: '2월', totalCount: 148, inspectedCount: 142, passCount: 132, failCount: 10, skippedCount: 6, failRate: 7.04 },
  { key: '2026-03', label: '3월', totalCount: 167, inspectedCount: 160, passCount: 147, failCount: 13, skippedCount: 7, failRate: 8.13 },
  { key: '2026-04', label: '4월', totalCount: 154, inspectedCount: 150, passCount: 144, failCount: 6, skippedCount: 4, failRate: 4.0 },
  { key: '2026-05', label: '5월', totalCount: 171, inspectedCount: 165, passCount: 152, failCount: 13, skippedCount: 6, failRate: 7.88 },
  { key: '2026-06', label: '6월', totalCount: 182, inspectedCount: 176, passCount: 169, failCount: 7, skippedCount: 6, failRate: 3.98 },
]

const WEEKLY_DEMO_DATA_BY_MONTH: Record<string, FailRateTrendPoint[]> = {
  '2026-01': [
    { key: '2026-01-w1', label: '1주차', totalCount: 31, inspectedCount: 29, passCount: 27, failCount: 2, skippedCount: 2, failRate: 6.9 },
    { key: '2026-01-w2', label: '2주차', totalCount: 33, inspectedCount: 31, passCount: 29, failCount: 2, skippedCount: 2, failRate: 6.45 },
    { key: '2026-01-w3', label: '3주차', totalCount: 35, inspectedCount: 32, passCount: 29, failCount: 3, skippedCount: 3, failRate: 9.38 },
    { key: '2026-01-w4', label: '4주차', totalCount: 33, inspectedCount: 32, passCount: 31, failCount: 1, skippedCount: 1, failRate: 3.13 },
  ],
  '2026-02': [
    { key: '2026-02-w1', label: '1주차', totalCount: 36, inspectedCount: 34, passCount: 32, failCount: 2, skippedCount: 2, failRate: 5.88 },
    { key: '2026-02-w2', label: '2주차', totalCount: 38, inspectedCount: 36, passCount: 33, failCount: 3, skippedCount: 2, failRate: 8.33 },
    { key: '2026-02-w3', label: '3주차', totalCount: 35, inspectedCount: 34, passCount: 31, failCount: 3, skippedCount: 1, failRate: 8.82 },
    { key: '2026-02-w4', label: '4주차', totalCount: 39, inspectedCount: 38, passCount: 36, failCount: 2, skippedCount: 1, failRate: 5.26 },
  ],
  '2026-03': [
    { key: '2026-03-w1', label: '1주차', totalCount: 32, inspectedCount: 30, passCount: 28, failCount: 2, skippedCount: 2, failRate: 6.67 },
    { key: '2026-03-w2', label: '2주차', totalCount: 34, inspectedCount: 33, passCount: 30, failCount: 3, skippedCount: 1, failRate: 9.09 },
    { key: '2026-03-w3', label: '3주차', totalCount: 36, inspectedCount: 35, passCount: 32, failCount: 3, skippedCount: 1, failRate: 8.57 },
    { key: '2026-03-w4', label: '4주차', totalCount: 33, inspectedCount: 31, passCount: 29, failCount: 2, skippedCount: 2, failRate: 6.45 },
    { key: '2026-03-w5', label: '5주차', totalCount: 32, inspectedCount: 31, passCount: 28, failCount: 3, skippedCount: 1, failRate: 9.68 },
  ],
  '2026-04': [
    { key: '2026-04-w1', label: '1주차', totalCount: 37, inspectedCount: 36, passCount: 34, failCount: 2, skippedCount: 1, failRate: 5.56 },
    { key: '2026-04-w2', label: '2주차', totalCount: 39, inspectedCount: 38, passCount: 37, failCount: 1, skippedCount: 1, failRate: 2.63 },
    { key: '2026-04-w3', label: '3주차', totalCount: 40, inspectedCount: 39, passCount: 38, failCount: 1, skippedCount: 1, failRate: 2.56 },
    { key: '2026-04-w4', label: '4주차', totalCount: 38, inspectedCount: 37, passCount: 35, failCount: 2, skippedCount: 1, failRate: 5.41 },
  ],
  '2026-05': [
    { key: '2026-05-w1', label: '1주차', totalCount: 33, inspectedCount: 31, passCount: 29, failCount: 2, skippedCount: 2, failRate: 6.45 },
    { key: '2026-05-w2', label: '2주차', totalCount: 35, inspectedCount: 34, passCount: 32, failCount: 2, skippedCount: 1, failRate: 5.88 },
    { key: '2026-05-w3', label: '3주차', totalCount: 34, inspectedCount: 33, passCount: 30, failCount: 3, skippedCount: 1, failRate: 9.09 },
    { key: '2026-05-w4', label: '4주차', totalCount: 36, inspectedCount: 34, passCount: 31, failCount: 3, skippedCount: 2, failRate: 8.82 },
    { key: '2026-05-w5', label: '5주차', totalCount: 33, inspectedCount: 33, passCount: 30, failCount: 3, skippedCount: 0, failRate: 9.09 },
  ],
  '2026-06': [
    { key: '2026-06-w1', label: '1주차', totalCount: 35, inspectedCount: 34, passCount: 33, failCount: 1, skippedCount: 1, failRate: 2.94 },
    { key: '2026-06-w2', label: '2주차', totalCount: 36, inspectedCount: 35, passCount: 34, failCount: 1, skippedCount: 1, failRate: 2.86 },
    { key: '2026-06-w3', label: '3주차', totalCount: 37, inspectedCount: 36, passCount: 34, failCount: 2, skippedCount: 1, failRate: 5.56 },
    { key: '2026-06-w4', label: '4주차', totalCount: 38, inspectedCount: 37, passCount: 35, failCount: 2, skippedCount: 1, failRate: 5.41 },
    { key: '2026-06-w5', label: '5주차', totalCount: 36, inspectedCount: 34, passCount: 33, failCount: 1, skippedCount: 2, failRate: 2.94 },
  ],
}

function monthKeyFromPoint(point: FailRateTrendPoint): string {
  if (/^\d{4}-\d{2}$/.test(point.key)) {
    return point.key
  }
  const matched = point.key.match(/^(\d{4}-\d{2})-w\d+$/)
  return matched?.[1] ?? point.key
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { value: number; payload: { inspectedCount: number; skippedCount: number } }[]
  label?: string
}) {
  if (!active || !payload?.length) return null

  const point = payload[0]
  return (
    <div className="rounded-lg border border-white/10 bg-[#10141b] px-3 py-2 text-xs shadow-xl">
      <p className="mb-1.5 text-slate-300">{label}</p>
      <p className="text-white font-semibold">오류율 {point.value.toFixed(2)}%</p>
      <p className="mt-1 text-slate-400">유효 검사 {point.payload.inspectedCount}건</p>
      <p className="text-slate-500">생략 {point.payload.skippedCount}건</p>
    </div>
  )
}

export default function FailRateTrendChart() {
  const [groupBy, setGroupBy] = useState<'month' | 'week'>('month')
  const { data: monthData = [], isLoading: monthLoading } = useFailRateTrend('month', 6)
  const usingDemoMonthData = monthData.length === 0
  const monthChartData = usingDemoMonthData ? MONTHLY_DEMO_DATA : monthData
  const [selectedMonthKey, setSelectedMonthKey] = useState<string>('')
  const selectedMonth = monthChartData.find((point) => point.key === selectedMonthKey) ?? monthChartData[monthChartData.length - 1]

  const { data: weekData = [], isLoading: weekLoading } = useFailRateTrend('week', 10)
  const usingDemoWeekData = weekData.length === 0
  const weeklySource = usingDemoWeekData
    ? (selectedMonth ? (WEEKLY_DEMO_DATA_BY_MONTH[selectedMonth.key] ?? []) : [])
    : weekData.filter((point) => monthKeyFromPoint(point) === selectedMonth?.key)

  const [selectedWeekKey, setSelectedWeekKey] = useState<string>('')
  const selectedWeek = weeklySource.find((point) => point.key === selectedWeekKey) ?? weeklySource[weeklySource.length - 1]
  const chartData = groupBy === 'month' ? monthChartData : weeklySource
  const selectedPoint = groupBy === 'month' ? selectedMonth : selectedWeek
  const isLoading = groupBy === 'month' ? monthLoading : weekLoading

  return (
    <div className="min-h-[28rem] min-w-0 rounded-[20px] border border-white/5 bg-[#171b22] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.18)] sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Quality Trend</h2>
          <p className="mt-1 text-xs text-slate-500">
            월별/주별 오류율 추이
            {(groupBy === 'month' ? usingDemoMonthData : usingDemoWeekData) ? ' · 더미 미리보기' : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isLoading && (
            <span className="rounded-lg bg-black/10 px-2 py-1 text-[11px] text-slate-500">
              불러오는 중
            </span>
          )}
          <div className="flex items-center gap-1 rounded-lg bg-black/10 p-1 text-xs">
            <button
              type="button"
              onClick={() => {
                setGroupBy('month')
              }}
              className={groupBy === 'month'
                ? 'rounded-md bg-white px-2.5 py-1.5 font-semibold text-slate-950'
                : 'rounded-md px-2.5 py-1.5 text-slate-400'}
            >
              월별
            </button>
            <button
              type="button"
              onClick={() => {
                setGroupBy('week')
              }}
              className={groupBy === 'week'
                ? 'rounded-md bg-white px-2.5 py-1.5 font-semibold text-slate-950'
                : 'rounded-md px-2.5 py-1.5 text-slate-400'}
            >
              주별
            </button>
          </div>
          <select
            value={selectedMonth?.key ?? ''}
            onChange={(e) => {
              setSelectedMonthKey(e.target.value)
              setSelectedWeekKey('')
            }}
            className="rounded-lg border border-white/10 bg-black/10 px-3 py-2 text-xs text-slate-200 outline-none"
          >
            {monthChartData.map((point) => (
              <option key={point.key} value={point.key}>
                {point.label}
              </option>
            ))}
          </select>
          {groupBy === 'week' && (
            <select
              value={selectedWeek?.key ?? ''}
              onChange={(e) => setSelectedWeekKey(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/10 px-3 py-2 text-xs text-slate-200 outline-none"
            >
              {weeklySource.map((point) => (
                <option key={point.key} value={point.key}>
                  {point.label}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {selectedPoint && (
        <div className="mb-4 grid grid-cols-2 gap-2 rounded-2xl bg-black/10 p-3 text-xs md:grid-cols-4 md:gap-3">
          <div>
            <p className="text-slate-500">선택 구간</p>
            <p className="mt-1 text-sm font-semibold text-white">{selectedPoint.label}</p>
          </div>
          <div>
            <p className="text-slate-500">오류율</p>
            <p className="mt-1 text-sm font-semibold leading-tight text-orange-300 break-keep">
              {selectedPoint.failRate.toFixed(2)}%
            </p>
          </div>
          <div>
            <p className="text-slate-500">유효 검사</p>
            <p className="mt-1 text-sm font-semibold text-white">{selectedPoint.inspectedCount}건</p>
          </div>
          <div>
            <p className="text-slate-500">생략</p>
            <p className="mt-1 text-sm font-semibold text-slate-300">{selectedPoint.skippedCount}건</p>
          </div>
        </div>
      )}

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="0" stroke="rgba(148, 163, 184, 0.16)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: '#7c8799', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            dy={6}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: '#7c8799', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={48}
            tickFormatter={(value) => `${value}%`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="failRate"
            stroke="#f97316"
            strokeWidth={3}
            dot={{ r: 4, fill: '#f97316', stroke: '#171b22', strokeWidth: 2 }}
            activeDot={{ r: 5, fill: '#fb923c' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
