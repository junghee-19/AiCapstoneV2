/**
 * 루트 애플리케이션 컴포넌트
 *
 * React Router의 라우팅 트리와 전체 레이아웃(Header + Sidebar + 콘텐츠)을 정의한다.
 *
 * 레이아웃 구조:
 * ┌──────────────────────────── Header (h-16) ──────────────────────────────┐
 * │ ┌─ Sidebar ─┐  ┌──────────── <Outlet /> ──────────────────────────────┐ │
 * │ │  (w-56)   │  │  DashboardPage / HistoryPage / SettingsPage           │ │
 * │ │           │  │                                                        │ │
 * │ └───────────┘  └────────────────────────────────────────────────────────┘ │
 * └─────────────────────────────────────────────────────────────────────────┘
 */

import { Routes, Route, Navigate } from 'react-router-dom'
import Header from '@/components/common/Header'
import Sidebar from '@/components/common/Sidebar'
import DashboardPage from '@/pages/DashboardPage'
import HistoryPage from '@/pages/HistoryPage'
import BoardReferencePage from '@/pages/BoardReferencePage'
import DatasetImagesPage from '@/pages/DatasetImagesPage'
import SettingsPage from '@/pages/SettingsPage'
import { useTheme } from '@/hooks/useTheme'

export default function App() {
  /* 라이트/다크 테마를 전체 화면에 한 번 적용 */
  useTheme()

  return (
    /* 전체 화면을 채우는 flex 컨테이너 */
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 overflow-hidden">

      {/* 상단 고정 헤더 */}
      <Header />

      {/* 헤더 아래 본문 영역: 사이드바 + 페이지 */}
      <div className="flex flex-1 overflow-hidden">

        {/* 좌측 고정 사이드바 */}
        <Sidebar />

        {/* 우측 페이지 콘텐츠 (스크롤 가능) */}
        <main className="flex-1 overflow-hidden bg-gray-950">
          <Routes>
            {/* 기본 경로: 대시보드 */}
            <Route path="/"         element={<DashboardPage />} />

            {/* 검사 이력 */}
            <Route path="/history"  element={<HistoryPage />} />

            {/* 보드 기준(정상 이미지/기대 개수) */}
            <Route path="/board-reference" element={<BoardReferencePage />} />

            {/* 라벨링 데이터셋 이미지 */}
            <Route path="/dataset-images" element={<DatasetImagesPage />} />

            {/* 설정 */}
            <Route path="/settings" element={<SettingsPage />} />

            {/* 정의되지 않은 경로는 루트로 리다이렉트 */}
            <Route path="*"         element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
