/**
 * 루트 애플리케이션 컴포넌트 (SnowUI 라이트 테마).
 *
 * 레이아웃:
 * ┌─ Sidebar (208px) ─┬─ Header ────────────────────────────┐
 * │  메뉴 4개          │  ┌── <Outlet /> ───────────────────┐│
 * │  대시보드/이력/    │  │  Dashboard / History / ...      ││
 * │  PCB 정보/설정     │  │                                  ││
 * └───────────────────┴──────────────────────────────────────┘
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
    <div className="flex h-screen bg-Background-1 text-Black-100% overflow-hidden">

      <Sidebar />

      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto bg-Background-1">
          <Routes>
            <Route path="/"                element={<DashboardPage />} />
            <Route path="/history"         element={<HistoryPage />} />
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
