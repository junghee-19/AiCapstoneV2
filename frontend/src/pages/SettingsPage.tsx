/**
 * 설정 페이지
 *
 * 세 카드형 섹션으로 구성:
 *  1. 시스템 정보 — 백엔드 상태 / 누적 검사 건수 / 정적 정책 항목
 *  2. 디바이스 관리 — Edge WebSocket 연결 디바이스 테이블
 *  3. 화면 설정   — 다크/라이트 테마 토글
 */

import { useQuery } from '@tanstack/react-query'
import { Server, Cpu, HardDrive, Wifi, WifiOff, Sun, Moon } from 'lucide-react'
import clsx from 'clsx'
import { fetchEdgeDevices, fetchStats, type EdgeDevice } from '@/api/inspectionApi'
import { useTheme } from '@/hooks/useTheme'

// ── 정적 시스템 정보 항목 ─────────────────────────────────────────────────────

const SYSTEM_INFO: Array<{ label: string; value: string }> = [
  { label: '검사 이력 보관기간', value: '60일 (자동 삭제)' },
  { label: '자동 정리 시각',     value: '매일 03:00' },
  { label: '대시보드 폴링 주기', value: '5초' },
  { label: '정렬 허용 한도',     value: '45°' },
  { label: '추론 모델',         value: 'YOLOv8n / best.pt' },
]

// ── 보조 컴포넌트 ─────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-800 last:border-b-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xs font-medium text-gray-200">{value}</span>
    </div>
  )
}

function SectionCard({
  icon,
  title,
  right,
  children,
}: {
  icon: React.ReactNode
  title: string
  right?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="bg-gray-900 rounded-xl border border-gray-800 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-gray-200">
          {icon}
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

// ── 1. 시스템 정보 ────────────────────────────────────────────────────────────

function SystemInfoSection() {
  const statsQ = useQuery({
    queryKey: ['inspections', 'stats'],
    queryFn: fetchStats,
    refetchInterval: 10_000,
  })

  const isHealthy = statsQ.isSuccess
  const totalCount = (statsQ.data?.totalCount as number | undefined) ?? null

  return (
    <SectionCard icon={<Server size={16} />} title="시스템 정보">
      <div className="space-y-0">
        <InfoRow
          label="백엔드 상태"
          value={
            statsQ.isLoading ? (
              <span className="text-gray-400">확인 중...</span>
            ) : isHealthy ? (
              <span className="text-emerald-400">정상</span>
            ) : (
              <span className="text-red-400">연결 실패</span>
            )
          }
        />
        <InfoRow
          label="누적 검사 건수"
          value={totalCount != null ? `${totalCount.toLocaleString()}건` : '—'}
        />
        {SYSTEM_INFO.map((item) => (
          <InfoRow key={item.label} label={item.label} value={item.value} />
        ))}
      </div>
    </SectionCard>
  )
}

// ── 2. 디바이스 관리 ──────────────────────────────────────────────────────────

function DeviceStatusBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ring-1',
        connected
          ? 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30'
          : 'bg-slate-500/15 text-slate-300 ring-slate-500/30'
      )}
    >
      {connected ? <Wifi size={11} /> : <WifiOff size={11} />}
      {connected ? '연결됨' : '끊김'}
    </span>
  )
}

function formatTimestamp(iso?: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return iso
  }
}

function DeviceManagementSection() {
  const devicesQ = useQuery({
    queryKey: ['edge-devices'],
    queryFn: fetchEdgeDevices,
    refetchInterval: 5_000,
  })

  const devices: EdgeDevice[] = devicesQ.data ?? []
  const total = devices.length
  const connected = devices.filter((d) => d.connected).length

  return (
    <SectionCard
      icon={<Cpu size={16} />}
      title="디바이스 관리"
      right={
        <span className="text-xs text-gray-500">
          연결됨{' '}
          <span className="text-emerald-400 font-semibold">{connected}</span>
          {' / 전체 '}
          <span className="text-gray-300 font-semibold">{total}</span>
        </span>
      }
    >
      {devicesQ.isLoading ? (
        <p className="text-xs text-gray-500 py-6 text-center">디바이스 목록 불러오는 중...</p>
      ) : total === 0 ? (
        <p className="text-xs text-gray-500 py-6 text-center">
          연결된 Edge 디바이스가 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-900/60 text-left">
                {['디바이스 ID', '상태', '연결 시각', '마지막 응답'].map((h) => (
                  <th
                    key={h}
                    className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {devices.map((device) => (
                <tr key={device.deviceId} className="bg-gray-900/40">
                  <td className="px-3 py-2 text-xs font-mono text-gray-300">
                    {device.deviceId}
                  </td>
                  <td className="px-3 py-2">
                    <DeviceStatusBadge connected={device.connected} />
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-400 font-mono">
                    {formatTimestamp(device.connectedAt)}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-400 font-mono">
                    {formatTimestamp(device.lastSeenAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  )
}

// ── 3. 화면 설정 ──────────────────────────────────────────────────────────────

function DisplaySection() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <SectionCard icon={<HardDrive size={16} />} title="화면 설정">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs text-gray-500">현재 모드</p>
          <p className="text-sm font-semibold text-gray-100 mt-0.5">
            {isDark ? '다크' : '라이트'}
          </p>
        </div>
        <button
          onClick={toggleTheme}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-gray-800 hover:bg-gray-700 text-gray-200 transition-colors"
        >
          {isDark ? <Sun size={14} /> : <Moon size={14} />}
          {isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}
        </button>
      </div>
    </SectionCard>
  )
}

// ── 메인 ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="p-6 space-y-5 overflow-y-auto h-full">
      <div>
        <h2 className="text-lg font-bold text-white">설정</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          시스템 상태와 디바이스 연결, 화면 표시 모드를 관리합니다.
        </p>
      </div>

      <SystemInfoSection />
      <DeviceManagementSection />
      <DisplaySection />
    </div>
  )
}
