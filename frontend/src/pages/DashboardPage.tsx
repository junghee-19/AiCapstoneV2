/**
 * 메인 대시보드 페이지
 *
 * 레이아웃 구성:
 * ┌──────────────────────────────────────────────────┐
 * │  헤더 (제목)                                       │
 * │  [StatCard × 4]  전체/합격/불합격/불량률           │
 * ├─────────────────────┬────────────────────────────│
 * │  PassFailChart      │  TrendChart                │
 * │  (도넛 차트)         │  (스택 막대 차트)            │
 * ├─────────────────────┴────────────────────────────│
 * │  FailRateTrendChart (주별 불량률 라인)              │
 * │  InspectionTable    (최근 15건 실시간 피드)          │
 * └──────────────────────────────────────────────────┘
 */

import StatCardGroup from '@/components/dashboard/StatCard'
import PassFailChart from '@/components/dashboard/PassFailChart'
import FailRateTrendChart from '@/components/dashboard/FailRateTrendChart'
import TrendChart from '@/components/dashboard/TrendChart'
import InspectionTable from '@/components/inspection/InspectionTable'
import { useRecentInspections } from '@/hooks/useInspectionData'

export default function DashboardPage() {
  /* 최근 15건 — 대시보드 하단 실시간 피드 테이블 */
  const { data: recentLogs = [], isLoading } = useRecentInspections(15)

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">

      {/* 페이지 제목 */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 pb-6">
        <div>
          <h2 className="text-lg font-bold text-Black-100%">실시간 대시보드</h2>
          <p className="text-xs text-Black-40% mt-0.5">
            검사 이력·통계 자동 갱신 · 이미지 업로드 또는 Edge 디바이스로 PCB 검사
          </p>
        </div>
      </div>

      {/* 1행: 통계 카드 4개 */}
      <StatCardGroup />

      {/* 2행: 도넛 차트 + 트렌드 차트 */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <PassFailChart />
        </div>
        <div className="lg:col-span-3">
          <TrendChart />
        </div>
      </div>

      <div>
        <FailRateTrendChart />
      </div>

      {/* 3행: 실시간 이력 테이블 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-Black-100%">최근 검사 이력</h2>
          <span className="text-xs text-Black-40%">최근 15건</span>
        </div>
        <InspectionTable logs={recentLogs} isLoading={isLoading} />
      </div>
    </div>
  )
}
