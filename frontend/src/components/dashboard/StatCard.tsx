/**
 * 통계 요약 카드 (SnowUI 라이트 테마).
 *
 * SnowUI 스타일: 파스텔 배경 카드 (Color-1/Color-2/Color-3/Color-4),
 * 큰 숫자 강조, 우측 상단 아이콘.
 */

import type { LucideIcon } from 'lucide-react'
import { CheckCircle, XCircle, Activity, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import { useStats } from '@/hooks/useInspectionData'

interface StatCardProps {
  title:    string
  value:    string | number
  icon:     LucideIcon
  /** 카드 배경 색상 토큰 */
  bg:       'Color-1' | 'Color-2' | 'Color-3' | 'Color-4'
  caption?: string
}

const BG_CLASS: Record<StatCardProps['bg'], string> = {
  'Color-1': 'bg-[#E5ECF6]',
  'Color-2': 'bg-[#E3F5FF]',
  'Color-3': 'bg-[#FFF4E5]',
  'Color-4': 'bg-[#F0F9E8]',
}

function StatCard({ title, value, icon: Icon, bg, caption }: StatCardProps) {
  return (
    <div className={clsx('rounded-2xl p-6 flex flex-col', BG_CLASS[bg])}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-Black-100% leading-5 font-semibold">{title}</span>
        <div className="w-9 h-9 rounded-lg bg-white/60 flex items-center justify-center">
          <Icon size={18} className="text-Black-100%" />
        </div>
      </div>
      <p className="mt-1 text-2xl font-semibold text-Black-100% tracking-tight leading-tight">
        {value}
      </p>
      {caption && (
        <p className="mt-2 text-xs text-Black-80% leading-4">{caption}</p>
      )}
    </div>
  )
}

function StatCardSkeleton() {
  return (
    <div className="bg-Black-4% rounded-2xl p-6 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-4 w-20 bg-Black-10% rounded" />
        <div className="w-9 h-9 bg-Black-10% rounded-lg" />
      </div>
      <div className="h-8 w-24 bg-Black-10% rounded mt-1" />
      <div className="h-3 w-32 bg-Black-10% rounded mt-3" />
    </div>
  )
}

export default function StatCardGroup() {
  const { data: stats, isLoading, isError } = useStats()

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
        {Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)}
      </div>
    )
  }

  if (isError || !stats) {
    return (
      <div className="col-span-4 text-center py-8 text-Black-40% text-sm">
        통계 데이터를 불러올 수 없습니다. 서버 연결을 확인하세요.
      </div>
    )
  }

  const inspectedCount = stats.inspectedCount ?? (stats.passCount + stats.failCount)

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
      <StatCard
        title="전체 검사"
        value={stats.totalCount.toLocaleString()}
        icon={Activity}
        bg="Color-2"
        caption={`유효 검사 ${inspectedCount.toLocaleString()}건`}
      />
      <StatCard
        title="합격 (PASS)"
        value={stats.passCount.toLocaleString()}
        icon={CheckCircle}
        bg="Color-4"
        caption={`유효 검사 대비 ${(100 - stats.failRate).toFixed(1)}%`}
      />
      <StatCard
        title="불합격 (FAIL)"
        value={stats.failCount.toLocaleString()}
        icon={XCircle}
        bg="Color-3"
        caption={`유효 검사 대비 ${stats.failRate.toFixed(1)}%`}
      />
      <StatCard
        title="불량률"
        value={`${stats.failRate.toFixed(2)}%`}
        icon={AlertTriangle}
        bg="Color-1"
        caption={`FAIL / 유효 검사 ${inspectedCount.toLocaleString()}건`}
      />
    </div>
  )
}
