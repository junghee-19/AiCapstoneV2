/**
 * 상단 헤더 (SnowUI 라이트 테마).
 *
 * 좌측: 사이드바 토글·즐겨찾기 아이콘 + breadcrumb (Dashboards / Default)
 * 우측: Search + 알림·테마·기록·전체화면 아이콘 + 라이브 폴링 상태
 */

import { useLocation } from 'react-router-dom'
import {
  PanelLeft, Star, Search,
  Sun, History, Bell, Maximize2, Activity,
} from 'lucide-react'
import { useStats } from '@/hooks/useInspectionData'

/** 경로별 breadcrumb 라벨 */
const ROUTE_LABEL: Record<string, string> = {
  '/':                '대시보드',
  '/history':         '검사 이력',
  '/board-reference': 'PCB 정보',
  '/settings':        '설정',
}

export default function Header() {
  const { isFetching, dataUpdatedAt } = useStats()
  const { pathname } = useLocation()
  const currentLabel = ROUTE_LABEL[pathname] ?? '대시보드'

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('ko-KR')
    : '--:--:--'

  return (
    <header className="h-14 px-7 py-5 border-b border-Black-10% flex justify-between items-center bg-Background-1 shrink-0">

      {/* 좌측: 사이드바 토글 + 즐겨찾기 + breadcrumb */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1">
          <button className="p-1 rounded-xl hover:bg-Black-4%" aria-label="사이드바">
            <PanelLeft size={16} className="text-Black-100%" />
          </button>
          <button className="p-1 rounded-xl hover:bg-Black-4%" aria-label="즐겨찾기">
            <Star size={16} className="text-Black-100%" />
          </button>
        </div>

        {/* Breadcrumb */}
        <nav className="flex items-center gap-2 text-xs leading-4">
          <span className="px-3 py-1 text-Black-40%">Dashboards</span>
          <span className="text-Black-10%">/</span>
          <span className="px-3 py-1 text-Black-100%">{currentLabel}</span>
        </nav>
      </div>

      {/* 우측: 검색 + 아이콘 + 라이브 인디케이터 */}
      <div className="flex items-center gap-5">

        {/* 검색 */}
        <div className="w-40 px-2 py-1 bg-Black-4% rounded-2xl flex items-center gap-2">
          <Search size={14} className="text-Black-20%" />
          <span className="flex-1 text-sm text-Black-20% leading-5">Search</span>
          <span className="w-5 text-center text-xs text-Black-20% rounded border border-Black-10% leading-4">/</span>
        </div>

        {/* 아이콘 4개 */}
        <div className="flex items-center gap-2">
          <button className="p-1 rounded-xl hover:bg-Black-4%" aria-label="테마">
            <Sun size={16} className="text-Black-100%" />
          </button>
          <button className="p-1 rounded-xl hover:bg-Black-4%" aria-label="기록">
            <History size={16} className="text-Black-100%" />
          </button>
          <button className="p-1 rounded-xl hover:bg-Black-4%" aria-label="알림">
            <Bell size={16} className="text-Black-100%" />
          </button>
          <button className="p-1 rounded-xl hover:bg-Black-4%" aria-label="전체화면">
            <Maximize2 size={16} className="text-Black-100%" />
          </button>
        </div>

        {/* 실시간 폴링 인디케이터 (도메인 — PCB 검사 시스템) */}
        <div className="flex items-center gap-2 pl-4 border-l border-Black-10%">
          <span
            className={`w-2 h-2 rounded-full ${
              isFetching ? 'bg-yellow-400 animate-pulse' : 'bg-green-400'
            }`}
          />
          <span className="text-xs text-Black-40%">
            {isFetching ? '갱신 중' : 'LIVE'}
          </span>
          <span className="hidden lg:inline-flex items-center gap-1 text-xs text-Black-40%">
            <Activity size={12} />
            {lastUpdated}
          </span>
        </div>
      </div>
    </header>
  )
}
