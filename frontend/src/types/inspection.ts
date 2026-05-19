/**
 * 프론트엔드 전체에서 사용하는 TypeScript 인터페이스 정의
 *
 * Spring Boot InspectionResponseDto와 1:1로 매핑되므로
 * 백엔드 DTO가 변경되면 이 파일도 함께 수정해야 한다.
 */

// ── 결함 상세 ─────────────────────────────────────────────────────────────────

/** 개별 결함 정보 (바운딩 박스 포함) */
export interface DefectDetail {
  defectType: string      // "TRACE_OPEN" | "METAL_DAMAGE" | "FIDUCIAL_MISSING"
  confidence: number      // 0.0 ~ 1.0
  bboxX: number           // 좌상단 X (픽셀)
  bboxY: number           // 좌상단 Y (픽셀)
  bboxWidth: number       // 너비 (픽셀)
  bboxHeight: number      // 높이 (픽셀)
}

// ── 검사 이력 ─────────────────────────────────────────────────────────────────

/** 최종 판정 결과 타입 */
export type InspectionResultType = 'PASS' | 'FAIL' | 'SKIPPED'

/** 검사 이력 단건 레코드 (GET /api/inspections 응답 요소) */
export interface InspectionLog {
  id: number
  deviceId: string
  result: InspectionResultType

  /** 피듀셜 마크 좌표 (탐지 실패 시 null) */
  fiducial1X: number | null
  fiducial1Y: number | null
  fiducial2X: number | null
  fiducial2Y: number | null

  /** Stage1 YOLO 탐지 신뢰도 (0~1, 미전송·구 이력은 null/undefined) */
  fiducial1Confidence?: number | null
  fiducial2Confidence?: number | null

  /** 촬영 시 기울기 (°), 보정 적용 전 측정값 */
  angleErrorDeg: number | null

  /** 추론 소요 시간 (ms) */
  inferenceTimeMs: number | null

  /** 전체 처리 시간 (ms) */
  totalTimeMs: number | null

  /** 백엔드 디스크에 저장된 이미지 파일명 (DB 의 image_path 컬럼 그대로) */
  imagePath: string | null

  /**
   * 프론트가 바로 사용할 수 있는 이미지 API URL.
   * 형식: "/api/inspections/{id}/image"
   * imagePath 가 없으면 null.
   */
  imageUrl: string | null

  /** 검사 수행 시각 (ISO 8601) */
  inspectedAt: string

  /** 서버 레코드 생성 시각 */
  createdAt: string

  /** 탐지된 결함 목록 */
  defects: DefectDetail[]
}

// ── 통계 ─────────────────────────────────────────────────────────────────────

/** GET /api/inspections/stats 응답 */
export interface InspectionStats {
  totalCount: number   // 전체 검사 건수
  inspectedCount: number // 실제 판정 건수 (PASS + FAIL)
  passCount:  number   // 합격 건수
  failCount:  number   // 불합격 건수
  skippedCount: number // 판정 생략 건수
  failRate:   number   // 불량률 (0.0 ~ 100.0, %)
}

export interface FailRateTrendPoint {
  key: string
  label: string
  totalCount: number
  inspectedCount: number
  passCount: number
  failCount: number
  skippedCount: number
  failRate: number
}

// ── 차트용 파생 타입 ──────────────────────────────────────────────────────────

/** TrendChart에서 사용하는 시간대별 집계 데이터 포인트 */
export interface TrendDataPoint {
  label: string    // X축 레이블 (예: "14:30", "03/31")
  pass:  number
  fail:  number
}

/** PassFailChart에서 사용하는 도넛 차트 데이터 */
export interface PieDataPoint {
  name:  string
  value: number
  fill:  string
}

// ── 결함 종류 한글 매핑 ───────────────────────────────────────────────────────

export const DEFECT_LABEL: Record<string, string> = {
  TRACE_OPEN:       '단선',
  METAL_DAMAGE:     '까짐',
  FIDUCIAL_MISSING: '마크 누락',
  // Ultralytics data.yaml / Colab 병합 클래스 (소문자 snake_case)
  trace_open:     '단선',
  metal_damage:   '까짐',
  pinhole:        '핀홀',
  short:          '단락',
  // PCB 통합 YOLO (data.yaml 클래스명과 동일)
  mount_hole:           '고정홀',
  gold_finger_row:      '금핑거 열',
  fiducial:             '피듀셜',
  smd_array_block:      'SMD 어레이',
  ic_chip:              'IC',
  edge_connector_zone:  '에지 커넥터',
}

/** 결함 종류별 표시 색상 (Tailwind 클래스 호환 hex) */
export const DEFECT_COLOR: Record<string, string> = {
  TRACE_OPEN:       '#f97316',  // orange-500
  METAL_DAMAGE:     '#ef4444',  // red-500
  FIDUCIAL_MISSING: '#a855f7',  // purple-500
  trace_open:       '#f97316',
  metal_damage:     '#ef4444',
  pinhole:          '#eab308',  // yellow-500
  short:            '#dc2626',  // red-600
  mount_hole:           '#22d3ee',  // cyan-400
  gold_finger_row:      '#fb7185',  // rose-400
  fiducial:             '#4ade80',  // green-400
  smd_array_block:      '#a78bfa',  // violet-400
  ic_chip:              '#fbbf24',  // amber-400
  edge_connector_zone:  '#f472b6',  // pink-400
  // PatchCore Anomaly Detection — 종류 분류 안 됨, 위치만
  ANOMALY:              '#dc2626',  // red-600
}

/** 표시용 라벨 (한글 매핑 없으면 원문 그대로) */
export function defectDisplayName(defectType: string): string {
  // ── Position Check — 카운트 기반 누락 ────────────────────────────────────
  // 예: "MISSING:ic_chip:expected=2,detected=1,missing=1"
  if (defectType.startsWith('MISSING:')) {
    const mCount = defectType.match(
      /^MISSING:([^:]+):expected=(\d+),detected=(\d+),missing=(\d+)$/
    )
    if (mCount) {
      const [, rawCls, expected, detected, missing] = mCount
      const clsKorean =
        DEFECT_LABEL[rawCls] ??
        DEFECT_LABEL[rawCls.toUpperCase()] ??
        rawCls
      return `${clsKorean} 누락 (기대 ${expected}개, 검출 ${detected}개, 누락 ${missing}개)`
    }
    // ── Position Check — 위치 기반 누락 ───────────────────────────────────
    // 예: "MISSING:ic_chip:expected_at=(833,203),nearest=125.5px"
    const mPos = defectType.match(
      /^MISSING:([^:]+):expected_at=\(([\d.-]+),([\d.-]+)\),nearest=([\d.]+|inf)px$/
    )
    if (mPos) {
      const [, rawCls, x, y, nearest] = mPos
      const clsKorean =
        DEFECT_LABEL[rawCls] ??
        DEFECT_LABEL[rawCls.toUpperCase()] ??
        rawCls
      const nearestText = nearest === 'inf' ? '없음' : `${nearest}px`
      return `${clsKorean} 누락 (예상 (${x}, ${y}), 최근접 ${nearestText})`
    }
    return defectType.replace('MISSING:', '누락: ')
  }

  // ── PatchCore Anomaly Detection — 종류 미상 ─────────────────────────────
  // 예: "ANOMALY:score=3.98,threshold=3.95"
  if (defectType.startsWith('ANOMALY:')) {
    const m = defectType.match(/^ANOMALY:score=([\d.]+),threshold=([\d.]+)$/)
    if (m) {
      const [, score, threshold] = m
      return `검토 필요 (점수 ${score} / 기준 ${threshold})`
    }
    return defectType.replace('ANOMALY:', '검토 필요: ')
  }

  return (
    DEFECT_LABEL[defectType] ??
    DEFECT_LABEL[defectType.toUpperCase()] ??
    defectType
  )
}

/** defectType prefix 매핑용 — DEFECT_COLOR 직접 lookup 안 되는 경우 */
export function defectColor(defectType: string): string {
  if (defectType.startsWith('MISSING:')) {
    // 누락 클래스 색을 유지 — MISSING:ic_chip:... → ic_chip 색
    const cls = defectType.split(':')[1]
    return DEFECT_COLOR[cls] ?? DEFECT_COLOR[cls?.toUpperCase()] ?? '#f87171'
  }
  if (defectType.startsWith('ANOMALY:')) {
    return DEFECT_COLOR.ANOMALY ?? '#dc2626'
  }
  return DEFECT_COLOR[defectType] ?? DEFECT_COLOR[defectType.toUpperCase()] ?? '#f87171'
}
