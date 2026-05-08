/**
 * 메인 대시보드 페이지
 *
 * 레이아웃 구성:
 * ┌──────────────────────────────────────────────────┐
 * │  [StatCard × 4]  전체/합격/불합격/불량률           │
 * ├─────────────────────┬────────────────────────────│
 * │  PassFailChart      │  TrendChart                │
 * │  (도넛 차트)          │  (스택 막대 차트)            │
 * ├─────────────────────┴────────────────────────────│
 * │  InspectionTable  (최근 15건 실시간 피드)           │
 * └──────────────────────────────────────────────────┘
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, FolderOpen, Loader2, Radio, Trash2 } from 'lucide-react'
import StatCardGroup from '@/components/dashboard/StatCard'
import PassFailChart from '@/components/dashboard/PassFailChart'
import FailRateTrendChart from '@/components/dashboard/FailRateTrendChart'
import TrendChart from '@/components/dashboard/TrendChart'
import InspectionTable from '@/components/inspection/InspectionTable'
import {
  deleteAllInspections,
  fetchEdgeDevices,
  inspectImage,
  triggerEdgeInspection,
} from '@/api/inspectionApi'
import { useRecentInspections } from '@/hooks/useInspectionData'

export default function DashboardPage() {
  const queryClient = useQueryClient()
  const [actionMsg, setActionMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [selectedDeviceId, setSelectedDeviceId] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [showCameraPreview, setShowCameraPreview] = useState(false)
  const [streamNonce, setStreamNonce] = useState(0)

  /* 최근 15건 — 대시보드 하단 실시간 피드 테이블 */
  const { data: recentLogs = [], isLoading } = useRecentInspections(15)
  const { data: edgeDevices = [], isLoading: isLoadingEdgeDevices } = useQuery({
    queryKey: ['edge-devices'],
    queryFn: fetchEdgeDevices,
    refetchInterval: 5_000,
  })
  const connectedDevices = useMemo(
    () => edgeDevices.filter((device) => device.connected),
    [edgeDevices]
  )

  useEffect(() => {
    if (selectedDeviceId && connectedDevices.some((device) => device.deviceId === selectedDeviceId)) {
      return
    }
    setSelectedDeviceId(connectedDevices[0]?.deviceId ?? '')
  }, [connectedDevices, selectedDeviceId])

  const invalidateInspections = () => {
    queryClient.invalidateQueries({ queryKey: ['inspections'] })
  }

  // 업로드 검사 — 파일 업로드 → Spring → inference-service → DB 저장
  const uploadInspectMutation = useMutation({
    mutationFn: inspectImage,
    onSuccess: (data) => {
      setActionMsg({ type: 'ok', text: `검사 완료 — 결과: ${data.result}` })
      setUploadFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
  const triggerMutation = useMutation({
    mutationFn: () => triggerEdgeInspection('aligned'),
    onSuccess: (data) => {
      setActionMsg({ type: 'ok', text: data.message })
      invalidateInspections()
      setTimeout(() => invalidateInspections(), 800)
      setTimeout(() => invalidateInspections(), 2500)
    },
    onError: (e: Error) => {
      setActionMsg({ type: 'err', text: e.message || '업로드 검사 실패' })
      setActionMsg({ type: 'err', text: e.message || '검사 트리거 실패' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteAllInspections,
    onSuccess: () => {
      setActionMsg({ type: 'ok', text: '검사 이력이 모두 삭제되었습니다.' })
      invalidateInspections()
    },
    onError: (e: Error) => {
      setActionMsg({ type: 'err', text: e.message || '삭제 실패' })
    },
  })

  const instantInspectMutation = useMutation({
    mutationFn: triggerEdgeInspection,
    onSuccess: (command) => {
      setActionMsg({
        type: 'ok',
        text: `검사 명령 전송 완료 — ${command.deviceId}`,
      })
      queryClient.invalidateQueries({ queryKey: ['edge-devices'] })
    },
    onError: (e: Error) => {
      setActionMsg({ type: 'err', text: e.message || '검사 명령 전송 실패' })
    },
  })

  // 지금 검사 — Spring Boot WebSocket에 연결된 Edge 디바이스로 명령 전송
  const handleInstantInspectClick = () => {
    if (!selectedDeviceId) {
      setActionMsg({ type: 'err', text: '연결된 Edge 디바이스를 선택해주세요.' })
      return
    }
    setActionMsg(null)
    instantInspectMutation.mutate(selectedDeviceId)
  }

  const handleDeleteHistory = () => {
    if (
      !window.confirm(
        '저장된 검사 이력과 결함 기록을 모두 삭제합니다. 계속할까요?'
      )
    ) {
      return
    }
    deleteMutation.mutate()
  }

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">

      {/* 페이지 제목 + 엣지 액션 */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-white">실시간 대시보드</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            검사 이력·통계 자동 갱신 · 이미지 업로드로 PCB 검사 가능
            라즈베리파이 엣지 노드 연결 중 · PCB가 중앙에서 5초간 안정되면 자동 캡처
          </p>
        </div>
        <div className="flex flex-col items-stretch sm:items-end gap-2 shrink-0 min-w-[min(100%,280px)]">
          <div className="flex flex-wrap items-center gap-2 justify-end">
            <label className="relative inline-flex items-center">
              <Radio
                size={15}
                className="pointer-events-none absolute left-3 text-emerald-400"
              />
              <select
                value={selectedDeviceId}
                onChange={(e) => setSelectedDeviceId(e.target.value)}
                disabled={isLoadingEdgeDevices || connectedDevices.length === 0}
                className="h-9 min-w-44 rounded-lg border border-gray-700 bg-gray-900 pl-9 pr-8 text-sm font-medium text-gray-100 outline-none transition-colors hover:border-gray-600 focus:border-indigo-500 disabled:opacity-50"
                title="WebSocket 연결 디바이스 선택"
              >
                {connectedDevices.length === 0 ? (
                  <option value="">
                    {isLoadingEdgeDevices ? '디바이스 확인 중' : '연결 디바이스 없음'}
                  </option>
                ) : (
                  connectedDevices.map((device) => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.deviceId}
                    </option>
                  ))
                )}
              </select>
            </label>
            <button
              type="button"
              onClick={handleInstantInspectClick}
              disabled={!selectedDeviceId || instantInspectMutation.isPending}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition-colors"
            >
              {instantInspectMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Camera size={16} />
              )}
              지금 검사
            </button>
            <button
              type="button"
              onClick={handleDeleteHistory}
              disabled={deleteMutation.isPending}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-gray-800 hover:bg-red-950/80 border border-gray-700 hover:border-red-900 text-gray-200 disabled:opacity-50 transition-colors"
            >
              {deleteMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Trash2 size={16} />
              )}
              이력 전체 삭제
            </button>
          <button
            type="button"
            onClick={() => {
              setActionMsg(null)
              setShowCameraPreview(true)
              setStreamNonce(Date.now())
              triggerMutation.mutate()
            }}
            disabled={triggerMutation.isPending}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition-colors"
          >
            {triggerMutation.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Camera size={16} />
            )}
            지금 검사
          </button>
          <button
            type="button"
            onClick={handleDeleteHistory}
            disabled={deleteMutation.isPending}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-gray-800 hover:bg-red-950/80 border border-gray-700 hover:border-red-900 text-gray-200 disabled:opacity-50 transition-colors"
          >
            {deleteMutation.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Trash2 size={16} />
            )}
            이력 전체 삭제
          </button>
          </div>

          {/* 업로드 검사 — 파일 선택 + 업로드 검사 버튼 */}
          <div className="flex flex-col gap-2 w-full sm:max-w-md">
            <label className="text-[11px] text-gray-500 font-medium uppercase tracking-wide block">
              로컬 이미지 업로드로 검사
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.bmp,.webp,image/*"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-gray-300 file:mr-2 file:px-2 file:py-1.5 file:rounded-md file:border-0 file:bg-gray-800 file:text-gray-200"
              />
              <button
                type="button"
                onClick={() => {
                  if (!uploadFile) return
                  setActionMsg(null)
                  uploadInspectMutation.mutate(uploadFile)
                }}
                disabled={!uploadFile || uploadInspectMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-sky-700 hover:bg-sky-600 disabled:opacity-50 text-white transition-colors"
              >
                {uploadInspectMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <FolderOpen size={16} />
                )}
                업로드 검사
              </button>
            </div>
            <p className="text-[11px] text-gray-600 leading-snug">
              업로드 이미지는 백엔드를 거쳐 inference-service에서 검사됩니다.
            </p>
          </div>
        </div>
      </div>

      {actionMsg && (
        <p
          className={
            actionMsg.type === 'ok'
              ? 'text-xs text-emerald-400/90'
              : 'text-xs text-red-400/90'
          }
        >
          {actionMsg.text}
        </p>
      )}

      {showCameraPreview && (
        <section className="rounded-2xl border border-gray-800 bg-gray-950/80 overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-800">
            <div>
              <h3 className="text-sm font-semibold text-white">라즈베리 카메라 실시간 화면</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                PCB가 화면 중앙에서 5초간 거의 움직이지 않으면 자동 캡처됩니다. 현재 추론 결과 박스 오버레이는 포함되지 않습니다.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowCameraPreview(false)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-gray-900 hover:bg-gray-800 border border-gray-700 text-gray-300 transition-colors"
            >
              <X size={14} />
              닫기
            </button>
          </div>
          <div className="p-4">
            <div className="relative w-full overflow-hidden rounded-xl border border-gray-800 bg-black">
              <img
                src={cameraStreamUrl}
                alt="라즈베리 카메라 실시간 스트림"
                className="block w-full aspect-video object-cover bg-black"
                onError={() => {
                  setActionMsg({
                    type: 'err',
                    text: '라즈베리 카메라 스트림을 불러오지 못했습니다. edge 서버와 카메라 상태를 확인하세요.',
                  })
                }}
              />
              <div className="absolute left-3 top-3 inline-flex items-center gap-2 rounded-full bg-black/55 px-3 py-1 text-[11px] font-medium text-emerald-300 backdrop-blur-sm">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                LIVE CAMERA
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 1행: 통계 카드 4개 */}
      <StatCardGroup />

      {/* 2행: 도넛 차트 + 트렌드 차트 */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        {/* PassFailChart: 2/5 너비 */}
        <div className="lg:col-span-2">
          <PassFailChart />
        </div>
        {/* TrendChart: 3/5 너비 */}
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
          <h2 className="text-sm font-semibold text-gray-300">최근 검사 이력</h2>
          <span className="text-xs text-gray-500">최근 15건</span>
        </div>
        <InspectionTable logs={recentLogs} isLoading={isLoading} />
      </div>
    </div>
  )
}
