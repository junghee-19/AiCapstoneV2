/**
 * 합격/불합격 도넛 차트 컴포넌트
 *
 * Recharts의 PieChart를 사용하여 PASS/FAIL 비율을 도넛 형태로 시각화한다.
 * 중앙에 불량률 수치를 직접 표시하여 한눈에 파악 가능하도록 설계했다.
 */

import {
  PieChart, Pie, Cell,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useStats } from '@/hooks/useInspectionData'
import type { PieDataPoint } from '@/types/inspection'

/* 합격/불합격 색상 */
const PASS_COLOR = '#22c55e'  // green-500
const FAIL_COLOR = '#ef4444'  // red-500

// ── 커스텀 중앙 레이블 ────────────────────────────────────────────────────────

/**
 * 도넛 차트 중앙에 불량률을 표시하는 SVG 커스텀 레이블.
 * Recharts의 label prop으로 주입된다.
 */
function CenterLabel({
  cx, cy, failRate,
}: {
  cx: number; cy: number; failRate: number
}) {
  return (
    <g>
      {/* 불량률 수치 */}
      <text
        x={cx} y={cy - 8}
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-white font-bold text-2xl"
        style={{ fontSize: '1.5rem', fontWeight: 700, fill: '#fff' }}
      >
        {failRate.toFixed(1)}%
      </text>
      {/* 레이블 */}
      <text
        x={cx} y={cy + 18}
        textAnchor="middle"
        style={{ fontSize: '0.75rem', fill: '#9ca3af' }}
      >
        불량률
      </text>
    </g>
  )
}

// ── 커스텀 툴팁 ───────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload }: { active?: boolean; payload?: { name: string; value: number }[] }) {
  if (!active || !payload?.length) return null
  const { name, value } = payload[0]
  return (
    <div className="rounded-lg border border-white/10 bg-[#10141b] px-3 py-2 text-xs shadow-xl">
      <span className="text-slate-300">{name}: </span>
      <span className="text-white font-bold">{value.toLocaleString()}건</span>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

export default function PassFailChart() {
  const { data: stats, isLoading } = useStats()

  /* 로딩 스켈레톤 */
  if (isLoading || !stats) {
    return (
      <div className="flex h-80 items-center justify-center rounded-[20px] border border-white/5 bg-[#171b22] p-6 animate-pulse">
        <div className="h-52 w-52 rounded-full bg-white/10" />
      </div>
    )
  }

  /* Recharts 데이터 배열 구성 */
  const pieData: PieDataPoint[] = [
    { name: 'PASS (합격)', value: stats.passCount, fill: PASS_COLOR },
    { name: 'FAIL (불합격)', value: stats.failCount, fill: FAIL_COLOR },
  ]

  return (
    <div className="h-80 overflow-hidden rounded-[20px] border border-white/5 bg-[#171b22] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.18)]">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Inspection Outcome</h2>
          <p className="mt-1 text-xs text-slate-500">누적 PASS/FAIL 비율</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-lg bg-black/10 px-2 py-1 text-xs text-slate-400">
          <span className="h-2 w-2 rounded-full bg-pass" />
          실시간 누적
        </div>
      </div>

      <ResponsiveContainer width="100%" height={232}>
        <PieChart>
          <Pie
            data={pieData}
            cx="50%"
            cy="46%"
            /* innerRadius > 0 → 도넛(Donut) 형태 */
            innerRadius={60}
            outerRadius={80}
            paddingAngle={3}
            dataKey="value"
            /* 중앙 레이블: 커스텀 SVG 컴포넌트 */
            label={({ cx, cy }) => (
              <CenterLabel cx={cx} cy={cy} failRate={stats.failRate} />
            )}
            labelLine={false}
          >
            {pieData.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} stroke="transparent" />
            ))}
          </Pie>

          {/* 마우스 호버 툴팁 */}
          <Tooltip content={<CustomTooltip />} />

          <Legend
            verticalAlign="bottom"
            iconType="circle"
            wrapperStyle={{ paddingTop: '6px' }}
            formatter={(value) => (
              <span style={{ color: '#cbd5e1', fontSize: '0.75rem' }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
