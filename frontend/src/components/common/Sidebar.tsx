/**
 * 좌측 사이드바 (SnowUI 라이트 테마).
 *
 * 구조: 상단 디바이스 식별자 → 메뉴 (대시보드 / 검사 이력 / PCB 정보 / 설정)
 *      하단: 백엔드 / Edge 포트
 */

import { NavLink } from 'react-router-dom'
import { BarChart2, ClipboardList, Images, Layers3, Settings, Cpu } from 'lucide-react'
import clsx from 'clsx'

const NAV_ITEMS = [
  {
    to:    '/',
    icon:  BarChart2,
    label: '대시보드',
    end:   true,  // 루트 경로 정확히 매칭 (하위 경로에서 active 방지)
  },
  {
    to:    '/history',
    icon:  ClipboardList,
    label: '검사 이력',
    end:   false,
  },
  {
    to:    '/board-reference',
    icon:  Layers3,
    label: 'PCB 정보',
    end:   false,
  },
  {
    to:    '/dataset-images',
    icon:  Images,
    label: '데이터셋',
    end:   false,
  },
  {
    to:    '/settings',
    icon:  Settings,
    label: '설정',
    end:   false,
  },
]

function navClass(isActive: boolean) {
  return clsx(
    'flex items-center gap-4 px-2 py-2 rounded-xl text-sm font-normal transition-colors',
    isActive
      ? 'bg-Black-4% text-Black-100%'
      : 'text-Black-100% hover:bg-Black-4%',
  )
}

export default function Sidebar() {
  return (
    <aside className="w-52 h-full p-4 border-r border-Black-10% flex flex-col gap-2 shrink-0 bg-Background-1">

      <div className="pb-3 flex flex-col gap-1">
        <div className="p-2 flex items-center gap-2">
          <div className="w-6 h-6 bg-Black-4% rounded-full flex items-center justify-center">
            <Cpu size={14} className="text-Black-100%" />
          </div>
          <span className="text-sm text-Black-100% font-mono font-bold leading-5">DeepSight</span>
        </div>
      </div>

      {/* 메뉴 */}
      <nav className="flex flex-col gap-2">
        <div className="px-3 py-1 text-sm text-Black-40% leading-5 font-semibold pb-8">Dashboards</div>
        {NAV_ITEMS.map(({ to, icon: Icon, label, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => navClass(isActive)}>
            <Icon size={16} className="shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

    </aside>
  )
}
