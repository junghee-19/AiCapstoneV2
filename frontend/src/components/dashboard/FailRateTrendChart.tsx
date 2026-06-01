/**
 * 월별/주별 불량률 추이 차트.
 *
 * 데이터는 Spring 백엔드 `/inspections/stats/fail-rate-trend?groupBy=...&periods=...`
 * 가 반환한 결과를 그대로 사용한다. 더미/하드코딩 데이터 없음.
 *
 * - 월별: 최근 6개월 (key="2026-05", label="5월")
 * - 주별: 최근 30주 (key="2026-W18", label="18주차") — 프론트에서 선택된 월의
 *         주만 필터링하고 라벨을 "1주차"~"5주차" (week-of-month) 로 재계산한다.
 *         이유: 백엔드의 ISO 주차(13주차 등) 는 사용자가 직관적으로 이해하기 어려움.
 */

import { useEffect, useMemo, useState } from 'react'
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

// ── ISO 주차 → 달력 변환 헬퍼 ───────────────────────────────────────────────

/**
 * "2026-W18" 형식의 ISO 주차 키 → 그 주의 월요일 Date.
 * ISO 8601: 1주는 1월 4일을 포함하는 주.
 */
function isoWeekKeyToMonday(key: string): Date | null {
  const m = key.match(/^(\d{4})-W(\d{1,2})$/)
  if (!m) return null
  const year = parseInt(m[1], 10)
  const week = parseInt(m[2], 10)
  const jan4 = new Date(year, 0, 4)
  const dayOfWeek = (jan4.getDay() + 6) % 7  // 월요일=0
  const week1Monday = new Date(year, 0, 4 - dayOfWeek)
  return new Date(week1Monday.getTime() + (week - 1) * 7 * 86400000)
}

/** Date → "YYYY-MM" 월 키. 해당 주가 속한 월 식별용. */
function monthKeyFromDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** Date → 그 달의 몇 주차 (1~5). 1일~7일=1, 8~14=2, ... */
function weekOfMonth(d: Date): number {
  return Math.min(5, Math.ceil(d.getDate() / 7))
}

// ── 툴팁 ─────────────────────────────────────────────────────────────────────

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { value: number; payload: { inspectedCount: number } }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  const point = payload[0]
  return (
    <div className="rounded-lg border border-Black-10% bg-white px-3 py-2 text-xs shadow-xl">
      <p className="mb-1.5 text-Black-80%">{label}</p>
      <p className="text-Black-100% font-semibold">오류율 {point.value.toFixed(2)}%</p>
      <p className="mt-1 text-Black-40%">유효 검사 {point.payload.inspectedCount}건</p>
    </div>
  )
}

// ── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export default function FailRateTrendChart() {
  const [groupBy, setGroupBy] = useState<'month' | 'week'>('month')

  /* 현재 연도 1~12월 전부 커버하도록 충분히 받아옴 */
  const { data: monthRaw = [], isLoading: monthLoading } = useFailRateTrend('month', 24)
  /* 주별: 1년 = 약 52주 — 여유 두고 60주 (선택 월에 맞춰 필터) */
  const { data: weekData = [], isLoading: weekLoading } = useFailRateTrend('week', 60)

  /* 현재 연도의 1~12월 풀 리스트 — 데이터 없는 달은 0건으로 패딩 */
  const monthData = useMemo<FailRateTrendPoint[]>(() => {
    const year = new Date().getFullYear()
    const byKey = new Map(monthRaw.map((p) => [p.key, p]))
    const result: FailRateTrendPoint[] = []
    for (let m = 1; m <= 12; m++) {
      const key = `${year}-${String(m).padStart(2, '0')}`
      const fromApi = byKey.get(key)
      result.push(fromApi ?? {
        key,
        label: `${m}월`,
        totalCount: 0,
        inspectedCount: 0,
        passCount: 0,
        failCount: 0,
        skippedCount: 0,
        failRate: 0,
      })
    }
    return result
  }, [monthRaw])

  const [selectedMonthKey, setSelectedMonthKey] = useState<string>('')
  const [selectedWeekKey, setSelectedWeekKey] = useState<string>('')

  /**
   * 모든 주 데이터에 "X월 N주차" 라벨 + 소속 월(monthKey) 메타 부착.
   * 백엔드 ISO 주차 키 ("2026-W18") → 그 주의 월요일이 속한 달 기준으로 변환.
   */
  const weeklyAll = useMemo(() => {
    return weekData
      .map((w) => {
        const monday = isoWeekKeyToMonday(w.key)
        if (!monday) return null
        const monthKey = monthKeyFromDate(monday)
        const wom = weekOfMonth(monday)
        const monthLabel = `${monday.getMonth() + 1}월`
        return {
          ...w,
          monthKey,
          /** 차트 X축 라벨 — 짧게 (예: "1주차") */
          label: `${wom}주차`,
          /** 드롭다운 옵션 라벨 — 월 + 주 (예: "5월 1주차") */
          fullLabel: `${monthLabel} ${wom}주차`,
        }
      })
      .filter((w): w is NonNullable<typeof w> => w !== null)
  }, [weekData])

  /* 데이터 도착 시 — 실제 검사 기록이 있는 가장 최신 월로 초기 선택.
     없으면 현재 달, 그것도 없으면 12월. */
  useEffect(() => {
    if (selectedMonthKey || monthData.length === 0) return
    const withData = [...monthData].reverse().find((p) => p.totalCount > 0)
    if (withData) {
      setSelectedMonthKey(withData.key)
      return
    }
    const currentMonth = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
    setSelectedMonthKey(currentMonth)
  }, [monthData, selectedMonthKey])

  /* 선택 월에 속한 주만 필터 (주별 모드용) */
  const weeklyForSelectedMonth = useMemo(() => {
    return weeklyAll.filter((w) => w.monthKey === selectedMonthKey)
  }, [weeklyAll, selectedMonthKey])

  /* 월 변경 시 그 달의 마지막 주로 자동 선택 (없으면 빈 값) */
  useEffect(() => {
    if (weeklyForSelectedMonth.length === 0) {
      setSelectedWeekKey('')
      return
    }
    const exists = weeklyForSelectedMonth.some((w) => w.key === selectedWeekKey)
    if (!exists) {
      setSelectedWeekKey(weeklyForSelectedMonth[weeklyForSelectedMonth.length - 1].key)
    }
  }, [weeklyForSelectedMonth, selectedWeekKey])

  const selectedWeekObj = weeklyForSelectedMonth.find((w) => w.key === selectedWeekKey)

  const chartData: FailRateTrendPoint[] =
    groupBy === 'month' ? monthData : weeklyForSelectedMonth
  const selectedPoint =
    groupBy === 'month'
      ? monthData.find((p) => p.key === selectedMonthKey)
        ?? monthData[monthData.length - 1]
      : selectedWeekObj ?? weeklyForSelectedMonth[weeklyForSelectedMonth.length - 1]
  const isLoading = groupBy === 'month' ? monthLoading : weekLoading
  const isEmpty = !isLoading && chartData.length === 0

  return (
    <div className="min-h-[28rem] min-w-0 rounded-[20px] border border-Black-10% bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-Black-100%">Quality Trend</h2>
          <p className="mt-1 text-xs text-Black-40%">
            {groupBy === 'month' ? '월별 오류율 추이' : '선택한 달의 주별 오류율 추이'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isLoading && (
            <span className="rounded-lg bg-Black-4% px-2 py-1 text-[11px] text-Black-40%">
              불러오는 중
            </span>
          )}
          <div className="flex items-center gap-1 rounded-lg bg-Black-4% p-1 text-xs">
            <button
              type="button"
              onClick={() => setGroupBy('month')}
              className={groupBy === 'month'
                ? 'rounded-md bg-white px-2.5 py-1.5 font-semibold text-Black-100%'
                : 'rounded-md px-2.5 py-1.5 text-Black-40%'}
            >
              월별
            </button>
            <button
              type="button"
              onClick={() => setGroupBy('week')}
              className={groupBy === 'week'
                ? 'rounded-md bg-white px-2.5 py-1.5 font-semibold text-Black-100%'
                : 'rounded-md px-2.5 py-1.5 text-Black-40%'}
            >
              주별
            </button>
          </div>

          {/* 월 드롭다운 — 양쪽 모드 모두에 표시 */}
          {monthData.length > 0 && (
            <select
              value={selectedMonthKey}
              onChange={(e) => setSelectedMonthKey(e.target.value)}
              className="rounded-lg border border-Black-10% bg-Black-4% px-3 py-2 text-xs text-Black-100% outline-none"
              title="월 선택"
            >
              {monthData.map((point) => (
                <option key={point.key} value={point.key}>
                  {point.label}
                </option>
              ))}
            </select>
          )}

          {/* 주 드롭다운 — 주별 모드일 때만, 선택 월에 속한 주만 표시 */}
          {groupBy === 'week' && weeklyForSelectedMonth.length > 0 && (
            <select
              value={selectedWeekKey}
              onChange={(e) => setSelectedWeekKey(e.target.value)}
              className="rounded-lg border border-Black-10% bg-Black-4% px-3 py-2 text-xs text-Black-100% outline-none"
              title="주 선택"
            >
              {weeklyForSelectedMonth.map((point) => (
                <option key={point.key} value={point.key}>
                  {point.label}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {selectedPoint && (
        <div className="mb-4 grid grid-cols-3 gap-2 rounded-2xl bg-Black-4% p-3 text-xs md:gap-3">
          <div>
            <p className="text-Black-40%">선택 구간</p>
            <p className="mt-1 text-sm font-semibold text-Black-100%">
              {groupBy === 'week' && selectedWeekObj
                ? selectedWeekObj.fullLabel
                : selectedPoint?.label}
            </p>
          </div>
          <div>
            <p className="text-Black-40%">오류율</p>
            <p className="mt-1 text-sm font-semibold leading-tight text-Black-100% break-keep">
              {selectedPoint.failRate.toFixed(2)}%
            </p>
          </div>
          <div>
            <p className="text-Black-40%">유효 검사</p>
            <p className="mt-1 text-sm font-semibold text-Black-100%">{selectedPoint.inspectedCount}건</p>
          </div>
        </div>
      )}

      {isEmpty ? (
        <div className="flex h-[220px] items-center justify-center text-xs text-Black-40%">
          {groupBy === 'week'
            ? '선택한 달에 검사 기록이 없습니다.'
            : '기록이 없어 추이를 표시할 수 없습니다.'}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="0" stroke="rgba(28, 28, 28, 0.1)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: '#1C1C1C', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              dy={6}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: '#1C1C1C', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(value) => `${value}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="failRate"
              stroke="#b899eb"
              strokeWidth={3}
              dot={{ r: 4, fill: '#b899eb', stroke: '#FFFFFF', strokeWidth: 2 }}
              activeDot={{ r: 5, fill: '#9b7dd8' }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
