/**
 * 설정 페이지
 *
 * 두 카드형 섹션으로 구성:
 *  1. 시스템 정보 — 백엔드 상태 / 누적 검사 건수 / 정적 정책 항목 (라이트 모드)
 *  2. 디바이스 관리 — Edge WebSocket 연결 디바이스 테이블
 */

import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Server, Cpu, Wifi, WifiOff, Save, Loader2, Camera } from 'lucide-react'
import clsx from 'clsx'
import {
  fetchAppSettings,
  fetchEdgeDevices,
  fetchStats,
  triggerDatasetCapture,
  updateAppSettings,
  type AppSettings,
  type EdgeDevice,
} from '@/api/inspectionApi'

// ── 정적 시스템 정보 항목 ─────────────────────────────────────────────────────

/** 사용자 편집 불가 — 고정 시스템 정보 (코드/환경변수로만 변경) */
const STATIC_SYSTEM_INFO: Array<{ label: string; value: string }> = [
  { label: '대시보드 폴링 주기', value: '5초' },
  { label: '정렬 허용 한도',     value: '45°' },
  { label: '추론 모델',         value: 'YOLOv8n / best.pt' },
]

// ── 자동 정리 cron ↔ HH:mm 변환 ─────────────────────────────────────────────

/** "0 30 5 * * *" → "05:30". 매일 정해진 시:분 패턴만 지원, 그 외엔 null. */
function cronToHHmm(cron: string): string | null {
  const m = cron.trim().match(/^0\s+(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*$/)
  if (!m) return null
  const min = Number(m[1]), hour = Number(m[2])
  if (min < 0 || min > 59 || hour < 0 || hour > 23) return null
  return `${String(hour).padStart(2, '0')}:${String(min).padStart(2, '0')}`
}

/** "05:30" → "0 30 5 * * *" (매일 그 시각). */
function hhmmToCron(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number)
  return `0 ${m} ${h} * * *`
}

// ── 보조 컴포넌트 (라이트 모드 SystemInfo 전용) ───────────────────────────────

function LightInfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-Black-10% last:border-b-0">
      <span className="text-xs text-Black-40%">{label}</span>
      <span className="text-xs font-medium text-Black-100%">{value}</span>
    </div>
  )
}

// ── 1. 시스템 정보 (라이트 모드, 편집 가능) ───────────────────────────────────

function SystemInfoSection() {
  const queryClient = useQueryClient()

  const statsQ = useQuery({
    queryKey: ['inspections', 'stats'],
    queryFn: fetchStats,
    refetchInterval: 10_000,
  })

  const settingsQ = useQuery({
    queryKey: ['app-settings'],
    queryFn: fetchAppSettings,
  })

  /* 로컬 폼 상태 (사용자가 저장 누르기 전까지 보관) */
  const [retentionDays, setRetentionDays] = useState<number>(60)
  const [cleanupTime,   setCleanupTime]   = useState<string>('03:00')

  /* 서버에서 가져온 값으로 초기화 */
  useEffect(() => {
    if (!settingsQ.data) return
    setRetentionDays(settingsQ.data.retentionDays)
    const hhmm = cronToHHmm(settingsQ.data.cleanupCron)
    setCleanupTime(hhmm ?? '03:00')
  }, [settingsQ.data])

  const saveMutation = useMutation({
    mutationFn: (s: AppSettings) => updateAppSettings(s),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['app-settings'] })
      window.alert('설정이 저장되었습니다.')
    },
    onError: (e: Error) =>
      window.alert(e.message || '설정 저장에 실패했습니다.'),
  })

  const isHealthy = statsQ.isSuccess
  const totalCount = (statsQ.data?.totalCount as number | undefined) ?? null

  const handleSave = () => {
    if (retentionDays < 1 || retentionDays > 365) {
      window.alert('보관기간은 1~365일 사이여야 합니다.')
      return
    }
    if (!/^\d{2}:\d{2}$/.test(cleanupTime)) {
      window.alert('정리 시각은 HH:mm 형식이어야 합니다.')
      return
    }
    saveMutation.mutate({
      retentionDays,
      cleanupCron: hhmmToCron(cleanupTime),
    })
  }

  /* 서버 값과 폼 값이 다르면 "변경됨" 상태로 표시 */
  const dirty =
    settingsQ.data != null &&
    (settingsQ.data.retentionDays !== retentionDays ||
      cronToHHmm(settingsQ.data.cleanupCron) !== cleanupTime)

  return (
    <section className="bg-white rounded-xl border border-Black-10% p-5">
      <div className="flex items-center gap-2 mb-4 text-Black-100%">
        <Server size={16} />
        <h3 className="text-sm font-semibold">시스템 정보</h3>
      </div>

      <div className="space-y-0">
        <LightInfoRow
          label="백엔드 상태"
          value={
            statsQ.isLoading ? (
              <span className="text-Black-40%">확인 중...</span>
            ) : isHealthy ? (
              <span className="text-emerald-600">정상</span>
            ) : (
              <span className="text-red-600">연결 실패</span>
            )
          }
        />
        <LightInfoRow
          label="누적 검사 건수"
          value={totalCount != null ? `${totalCount.toLocaleString()}건` : '—'}
        />

        {/* 편집 가능 — 보관기간 */}
        <div className="flex items-center justify-between py-2 border-b border-Black-10%">
          <span className="text-xs text-Black-40%">검사 이력 보관기간</span>
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={1}
              max={365}
              value={retentionDays}
              onChange={(e) => setRetentionDays(Number(e.target.value))}
              className="w-12 bg-Black-4% border border-Black-10% text-Black-100% text-xs rounded-md px-2 py-1 text-right focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <span className="text-xs text-Black-40%">일 (자동 삭제)</span>
          </div>
        </div>

        {/* 편집 가능 — 정리 시각 */}
        <div className="flex items-center justify-between py-2 border-b border-Black-10%">
          <span className="text-xs text-Black-40%">자동 정리 시각</span>
          <div className="flex items-center gap-1">
            <span className="text-xs text-Black-40%">매일</span>
            <input
              type="time"
              value={cleanupTime}
              onChange={(e) => setCleanupTime(e.target.value)}
              className="bg-Black-4% border border-Black-10% text-Black-100% text-xs rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>

        {STATIC_SYSTEM_INFO.map((item) => (
          <LightInfoRow key={item.label} label={item.label} value={item.value} />
        ))}
      </div>

      {/* 저장 버튼 — 변경 사항이 있을 때만 활성화 */}
      <div className="flex items-center justify-end mt-4 gap-2">
        {dirty && !saveMutation.isPending && (
          <span className="text-xs text-amber-600">미저장 변경 사항이 있습니다</span>
        )}
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || saveMutation.isPending}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saveMutation.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Save size={14} />
          )}
          {saveMutation.isPending ? '저장 중...' : '저장'}
        </button>
      </div>
    </section>
  )
}

// ── 2. 디바이스 관리 ──────────────────────────────────────────────────────────

function DeviceStatusBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ring-1',
        connected
          ? 'bg-emerald-500/15 text-emerald-600 ring-emerald-500/30'
          : 'bg-Black-10% text-Black-80% ring-Black-10%'
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
  const queryClient = useQueryClient()
  const devicesQ = useQuery({
    queryKey: ['edge-devices'],
    queryFn: fetchEdgeDevices,
    refetchInterval: 5_000,
  })

  const devices: EdgeDevice[] = devicesQ.data ?? []
  const total = devices.length
  const connected = devices.filter((d) => d.connected).length
  const captureM = useMutation({
    mutationFn: ({ deviceId, count, interval }: { deviceId: string; count: number; interval: number }) =>
      triggerDatasetCapture(deviceId, count, interval),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['edge-devices'] })
      const refreshDelayMs = Math.max(3_000, variables.count * variables.interval * 1000 + 2_000)
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['dataset-images'] })
        queryClient.invalidateQueries({ queryKey: ['edge-devices'] })
      }, refreshDelayMs)
    },
  })

  return (
    <section className="bg-white rounded-xl border border-Black-10% p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-Black-100%">
          <Cpu size={16} />
          <h3 className="text-sm font-semibold">디바이스 관리</h3>
        </div>
        <span className="text-xs text-Black-40%">
          연결됨{' '}
          <span className="text-emerald-600 font-semibold">{connected}</span>
          {' / 전체 '}
          <span className="text-Black-100% font-semibold">{total}</span>
        </span>
      </div>

      {devicesQ.isLoading ? (
        <p className="text-xs text-Black-40% py-6 text-center">디바이스 목록 불러오는 중...</p>
      ) : total === 0 ? (
        <p className="text-xs text-Black-40% py-6 text-center">
          연결된 Edge 디바이스가 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-Black-10%">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-Black-4% text-left">
                {['디바이스 ID', '상태', '연결 시각', '마지막 응답', '데이터셋'].map((h) => (
                  <th
                    key={h}
                    className="px-3 py-2 text-xs font-semibold text-Black-40% uppercase tracking-wider"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-Black-10%">
              {devices.map((device) => (
                <tr key={device.deviceId} className="bg-white hover:bg-Black-4%">
                  <td className="px-3 py-2 text-xs font-mono text-Black-100%">
                    {device.deviceId}
                  </td>
                  <td className="px-3 py-2">
                    <DeviceStatusBadge connected={device.connected} />
                  </td>
                  <td className="px-3 py-2 text-xs text-Black-40% font-mono">
                    {formatTimestamp(device.connectedAt)}
                  </td>
                  <td className="px-3 py-2 text-xs text-Black-40% font-mono">
                    {formatTimestamp(device.lastSeenAt)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() =>
                          captureM.mutate({ deviceId: device.deviceId, count: 1, interval: 1 })
                        }
                        disabled={!device.connected || captureM.isPending}
                        className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-100 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        <Camera size={13} />
                        1장 촬영
                      </button>
                      <button
                        onClick={() =>
                          captureM.mutate({ deviceId: device.deviceId, count: 10, interval: 3 })
                        }
                        disabled={!device.connected || captureM.isPending}
                        className="inline-flex items-center gap-1.5 rounded-md border border-sky-500/40 bg-sky-500/10 px-2.5 py-1.5 text-xs font-semibold text-sky-100 transition-colors hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        <Camera size={13} />
                        10장 촬영
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// ── 메인 ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  /* 화면 설정(테마 토글)이 남긴 body.theme-light 클래스 / localStorage 흔적 제거.
     SnowUI 라이트 테마로 통일됐으므로 토글이 더 이상 필요 없다. */
  useEffect(() => {
    document.body.classList.remove('theme-light')
    try {
      window.localStorage.removeItem('aicapstone:theme')
    } catch {
      /* localStorage 접근 불가 환경은 무시 */
    }
  }, [])

  return (
    <div className="p-6 space-y-5 overflow-y-auto h-full">
      <div>
        <h2 className="text-lg font-bold text-Black-100%">설정</h2>
        <p className="text-xs text-Black-40% mt-0.5">
          시스템 상태와 디바이스 연결을 확인합니다.
        </p>
      </div>

      <SystemInfoSection />
      <DeviceManagementSection />
    </div>
  )
}
