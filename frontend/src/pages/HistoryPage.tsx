/**
 * 검사 이력 페이지
 *
 * 전체 검사 이력을 조회하고 날짜 기간 필터 및 결과(PASS/FAIL) 필터를 제공한다.
 *
 * 기능:
 * - 날짜 범위 선택 (from ~ to)
 * - 결과 필터 버튼 그룹 (전체 / PASS / FAIL)
 * - 총 건수 / 합격 / 불합격 미니 통계
 * - InspectionTable 렌더링 (행 클릭 → DefectViewer)
 */

import { useState, useMemo } from 'react'
import { Search, Filter, Download, Trash2, Loader2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import InspectionTable from '@/components/inspection/InspectionTable'
import { useAllInspections } from '@/hooks/useInspectionData'
import {
  deleteAllInspections,
  deleteInspectionsByPeriod,
} from '@/api/inspectionApi'
import type { InspectionResultType } from '@/types/inspection'

// ── 결과 필터 버튼 ────────────────────────────────────────────────────────────

type ResultFilter = 'ALL' | InspectionResultType

function getLocalDateString(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

interface FilterButtonProps {
  label:    string
  value:    ResultFilter
  current:  ResultFilter
  count:    number
  onClick:  (v: ResultFilter) => void
}

function FilterButton({ label, value, current, count, onClick }: FilterButtonProps) {
  const active = value === current
  return (
    <button
      onClick={() => onClick(value)}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
        active
          ? 'bg-indigo-600 text-white'
          : 'bg-Black-4% text-Black-40% hover:text-Black-100% hover:bg-Black-10%'
      )}
    >
      {label}
      <span className={clsx(
        'px-1.5 py-0.5 rounded-full text-xs',
        active ? 'bg-white/30' : 'bg-Black-10%'
      )}>
        {count}
      </span>
    </button>
  )
}

// ── CSV 다운로드 유틸 ─────────────────────────────────────────────────────────

function downloadCsv(data: ReturnType<typeof useAllInspections>['data']) {
  if (!data?.length) return

  /* CSV 헤더 */
  const header = ['ID', '시각', '디바이스', '결과', '오차(°)', '추론(ms)', '총처리(ms)', '결함수']
  const rows = data.map((l) => [
    l.id,
    new Date(l.inspectedAt).toLocaleString('ko-KR'),
    l.deviceId,
    l.result,
    l.angleErrorDeg?.toFixed(2) ?? '',
    l.inferenceTimeMs ?? '',
    l.totalTimeMs ?? '',
    l.defects.length,
  ])

  const csv = [header, ...rows].map((r) => r.join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)

  /* 가상 <a> 태그로 다운로드 트리거 */
  const link = document.createElement('a')
  link.href = url
  link.download = `inspection_history_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const queryClient = useQueryClient()
  const { data: allLogs = [], isLoading } = useAllInspections()

  /* 결과 필터 상태 */
  const [resultFilter, setResultFilter] = useState<ResultFilter>('ALL')

  /* 날짜 범위 필터 상태 (YYYY-MM-DD 형식) */
  const today = getLocalDateString()
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo,   setDateTo]   = useState(today)

  /* 기간 삭제 모달 상태 */
  const [periodModalOpen, setPeriodModalOpen] = useState(false)
  const [modalFrom, setModalFrom] = useState('')
  const [modalTo,   setModalTo]   = useState(today)

  // ── 삭제 mutation ───────────────────────────────────────────────────────────

  const invalidateInspections = () =>
    queryClient.invalidateQueries({ queryKey: ['inspections'] })

  const deleteAllMutation = useMutation({
    mutationFn: deleteAllInspections,
    onSuccess: invalidateInspections,
    onError: (e: Error) => window.alert(e.message || '전체 삭제에 실패했습니다.'),
  })

  const deletePeriodMutation = useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) =>
      deleteInspectionsByPeriod(from, to),
    onSuccess: (res) => {
      invalidateInspections()
      setPeriodModalOpen(false)
      window.alert(`기간 내 ${res.deletedCount}건이 삭제되었습니다.`)
    },
    onError: (e: Error) => window.alert(e.message || '기간 삭제에 실패했습니다.'),
  })

  const handleDeleteAll = () => {
    if (!window.confirm('전체 검사 이력과 결함 기록을 모두 삭제합니다. 계속할까요?')) return
    deleteAllMutation.mutate()
  }

  const openPeriodModal = () => {
    setModalFrom('')
    setModalTo(today)
    setPeriodModalOpen(true)
  }

  const handleConfirmDeletePeriod = () => {
    if (!modalFrom || !modalTo) {
      window.alert('시작일과 종료일을 모두 선택해 주세요.')
      return
    }
    if (modalFrom > modalTo) {
      window.alert('시작일이 종료일보다 늦을 수 없습니다.')
      return
    }
    if (!window.confirm(`${modalFrom} ~ ${modalTo} 기간의 검사 이력을 삭제합니다. 계속할까요?`)) {
      return
    }
    deletePeriodMutation.mutate({
      from: `${modalFrom}T00:00:00`,
      to:   `${modalTo}T23:59:59`,
    })
  }

  /* 필터 적용된 데이터 계산 (useMemo로 불필요한 재연산 방지) */
  const filteredLogs = useMemo(() => {
    return allLogs.filter((log) => {
      /* 결과 필터 */
      if (resultFilter !== 'ALL' && log.result !== resultFilter) return false

      /* 날짜 범위 필터 */
      const logDate = log.inspectedAt.slice(0, 10)
      if (dateFrom && logDate < dateFrom) return false
      if (dateTo   && logDate > dateTo)   return false

      return true
    })
  }, [allLogs, resultFilter, dateFrom, dateTo])

  /* 필터 결과 미니 통계 */
  const passCount = filteredLogs.filter((l) => l.result === 'PASS').length
  const failCount = filteredLogs.filter((l) => l.result === 'FAIL').length
  const inspectedCount = passCount + failCount

  return (
    <div className="p-6 space-y-5 overflow-y-auto h-full">

      {/* 페이지 제목 */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-black">검사 이력</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            전체 검사 기록 조회 및 결함 상세 확인 · 보관기간 60일 (자동 삭제)
          </p>
        </div>

        {/* 액션 버튼 그룹: CSV / 기간 삭제 / 전체 삭제 */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => downloadCsv(filteredLogs)}
            className="flex items-center gap-2 px-3 py-2 bg-Color-white hover:bg-Color-1 text-Black-100% border border-Black-10% rounded-lg text-xs font-medium transition-colors"
          >
            <Download size={14} />
            CSV 내보내기
          </button>

          <button
            onClick={openPeriodModal}
            disabled={deletePeriodMutation.isPending}
            className="flex items-center gap-2 px-3 py-2 bg-Color-white hover:bg-red-200 border border-red-200 text-red-500 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {deletePeriodMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
            {deletePeriodMutation.isPending ? '삭제 중...' : '기간 삭제'}
          </button>

          <button
            onClick={handleDeleteAll}
            disabled={deleteAllMutation.isPending}
            className="flex items-center gap-2 px-3 py-2 bg-Color-white hover:bg-red-700/80 border border-red-600/60 text-red-700/80 hover:text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {deleteAllMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
            {deleteAllMutation.isPending ? '삭제 중...' : '전체 삭제'}
          </button>
        </div>
      </div>

      {/* 필터 영역 */}
      <div className="bg-white border border-Black-10% rounded-xl p-4">
        <div className="flex flex-wrap gap-4 items-end">

          {/* 날짜 범위 필터 */}
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-Black-40% shrink-0" />
            <div className="flex items-center gap-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-Black-40%">시작일</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  max={dateTo || today}
                  className="bg-Black-4% border border-Black-10% text-Black-80% text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <span className="text-Black-40% text-sm mt-4">~</span>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-Black-40%">종료일</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  min={dateFrom}
                  max={today}
                  className="bg-Black-4% border border-Black-10% text-Black-80% text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>
          </div>

          {/* 결과 필터 버튼 그룹 */}
          <div className="flex items-center gap-2 ml-auto">
            <Search size={14} className="text-Black-40%" />
            <FilterButton label="전체"  value="ALL"  current={resultFilter} count={allLogs.length}                        onClick={setResultFilter} />
            <FilterButton label="PASS"  value="PASS" current={resultFilter} count={allLogs.filter(l => l.result==='PASS').length} onClick={setResultFilter} />
            <FilterButton label="FAIL"  value="FAIL" current={resultFilter} count={allLogs.filter(l => l.result==='FAIL').length} onClick={setResultFilter} />
          </div>
        </div>
      </div>

      {/* 필터 결과 미니 통계 바 */}
      <div className="flex items-center gap-4 text-xs text-Black-40%">
        <span>
          조회 결과: <span className="text-Black-100% font-semibold">{filteredLogs.length}건</span>
        </span>
        <span>
          합격: <span className="text-emerald-600 font-semibold">{passCount}건</span>
        </span>
        <span>
          불합격: <span className="text-red-600 font-semibold">{failCount}건</span>
        </span>
        {inspectedCount > 0 && (
          <span>
            불량률: <span className="text-yellow-600 font-semibold">
              {((failCount / inspectedCount) * 100).toFixed(2)}%
            </span>
          </span>
        )}
      </div>

      {/* 검사 이력 테이블 */}
      <InspectionTable
        logs={filteredLogs}
        isLoading={isLoading}
      />

      {/* 기간 삭제 모달 — 외부 클릭 시 닫힘 */}
      {periodModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-Black-40% p-4"
          onClick={() => setPeriodModalOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-Black-10%"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-Black-100% mb-1">기간 삭제</h3>
            <p className="text-xs text-Black-40% mb-4">
              선택한 기간(시작일 00:00 ~ 종료일 23:59)의 검사 이력을 영구 삭제합니다.
            </p>

            <div className="flex items-end gap-3 mb-6">
              <div className="flex-1 flex flex-col gap-1">
                <label className="text-xs text-Black-40%">시작일</label>
                <input
                  type="date"
                  value={modalFrom}
                  onChange={(e) => setModalFrom(e.target.value)}
                  max={modalTo || today}
                  className="bg-Black-4% border border-Black-10% text-Black-100% text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <span className="text-Black-40% text-sm pb-2">~</span>
              <div className="flex-1 flex flex-col gap-1">
                <label className="text-xs text-Black-40%">종료일</label>
                <input
                  type="date"
                  value={modalTo}
                  onChange={(e) => setModalTo(e.target.value)}
                  min={modalFrom}
                  max={today}
                  className="bg-Black-4% border border-Black-10% text-Black-100% text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setPeriodModalOpen(false)}
                className="px-4 py-2 bg-Black-4% hover:bg-Black-10% text-Black-100% rounded-lg text-sm font-medium transition-colors"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleConfirmDeletePeriod}
                disabled={deletePeriodMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {deletePeriodMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Trash2 size={14} />
                )}
                {deletePeriodMutation.isPending ? '삭제 중...' : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
