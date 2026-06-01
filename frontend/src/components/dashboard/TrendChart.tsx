/**
 * 시간대별 검사 추이 차트 컴포넌트
 *
 * Recharts의 BarChart를 사용하여 최근 24시간 동안의 시간대별
 * PASS/FAIL 건수를 스택(누적) 막대 그래프로 시각화한다.
 *
 * 데이터는 useTrendData() 훅이 전체 이력에서 시간 단위로 집계하여 제공한다.
 */

import {
  BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useTrendData } from '@/hooks/useInspectionData'

/* 색상 상수 */
/* 파스텔 톤 — 라이트 테마 가독성 */
const PASS_COLOR = '#86EFAC'  // pastel green
const FAIL_COLOR = '#FCA5A5'  // pastel red

// ── 커스텀 툴팁 ───────────────────────────────────────────────────────────────

function CustomTooltip({
  active, payload, label,
}: {
  active?: boolean
  payload?: { name: string; value: number; fill: string }[]
  label?: string
}) {
  if (!active || !payload?.length) return null

  const total = payload.reduce((sum, p) => sum + (p.value ?? 0), 0)

  return (
    <div className="rounded-lg border border-Black-10% bg-white px-3 py-2 text-xs shadow-xl">
      <p className="mb-1.5 text-Black-40%">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full inline-block"
            style={{ backgroundColor: p.fill }}
          />
          <span className="text-Black-80%">{p.name}:</span>
          <span className="text-Black-100% font-bold">{p.value}건</span>
        </div>
      ))}
      <div className="mt-1.5 border-t border-Black-10% pt-1.5 text-Black-40%">
        합계: <span className="text-Black-100%">{total}건</span>
      </div>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

export default function TrendChart() {
  const { data: trendData, isLoading } = useTrendData()

  /* 로딩 스켈레톤 */
  if (isLoading) {
    return (
      <div className="h-80 rounded-[20px] border border-Black-10% bg-white p-6 animate-pulse">
        <div className="mb-4 h-5 w-36 rounded bg-white/10" />
        <div className="h-[248px] rounded-2xl bg-Black-10%" />
      </div>
    )
  }

  /* 데이터 없음 안내 */
  if (!trendData.length) {
    return (
      <div className="flex h-80 items-center justify-center rounded-[20px] border border-Black-10% bg-white p-6">
        <p className="text-sm text-Black-40%">최근 24시간 검사 데이터가 없습니다.</p>
      </div>
    )
  }

  return (
    <div className="h-80 min-w-0 overflow-hidden rounded-[20px] border border-Black-10% bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap items-center gap-4 rounded-lg bg-Black-4% px-1 py-1">
          <button
            type="button"
            className="rounded-xl bg-white px-3 py-1.5 text-sm font-semibold text-Black-100% shadow-sm"
          >
            Inspection Trend
          </button>
          <span className="px-1 text-sm text-Black-40%">PASS</span>
          <span className="px-1 text-sm text-Black-40%">FAIL</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={248}>
        <BarChart
          data={trendData}
          margin={{ top: 8, right: 8, left: -24, bottom: 0 }}
          barCategoryGap="28%"
          barSize={16}
        >
          <CartesianGrid
            strokeDasharray="0"
            stroke="rgba(28, 28, 28, 0.1)"
            vertical={false}
          />
          <XAxis
            dataKey="label"
            tick={{ fill: '#1C1C1C', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            dy={8}
          />
          <YAxis
            tick={{ fill: '#1C1C1C', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
            width={42}
          />
          <Tooltip
            content={<CustomTooltip />}
            cursor={{ fill: 'rgba(28,28,28,0.04)' }}
          />
          <Legend
            verticalAlign="top"
            align="right"
            height={0}
            formatter={(value) => (
              <span style={{ color: '#1C1C1C', fontSize: '0.75rem' }}>{value}</span>
            )}
          />
          <Bar dataKey="pass" name="PASS" stackId="stack" fill={PASS_COLOR} radius={[8, 8, 0, 0]} />
          <Bar dataKey="fail" name="FAIL" stackId="stack" fill={FAIL_COLOR} radius={[8, 8, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
