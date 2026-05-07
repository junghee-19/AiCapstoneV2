/**
 * 라즈베리파이 FastAPI 엣지 API
 * - 개발 환경: Vite 프록시(/edge)
 * - 배포 환경: VITE_EDGE_CAPTURE_URL 사용
 */

/// <reference types="vite/client" />


const EDGE_BASE_URL = import.meta.env.DEV
  ? '/edge'
  : (import.meta.env.VITE_EDGE_CAPTURE_URL ?? '')

function edgeUrl(path: string) {
  return `${EDGE_BASE_URL}${path}`
}

export function getEdgeCameraStreamUrl(): string {
  return edgeUrl('/edge/camera/stream')
}

/**
 * 수동 PCB 검사 1회 실행 (백그라운드). 결과는 Spring Boot DB에 적재된다.
 */
export async function triggerEdgeInspection(): Promise<{ message: string }> {
  const res = await fetch(edgeUrl('/edge/inspect/trigger'), { method: 'POST' })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<{ message: string }>
}

/** edge/demo_samples 아래 시연용 이미지 목록 */
export async function fetchDemoSamplePaths(): Promise<string[]> {
  const res = await fetch(edgeUrl('/edge/inspect/demo-samples'))
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `${res.status}`)
  }
  const data = (await res.json()) as { paths?: string[] }
  return data.paths ?? []
}

/** 저장된 이미지 경로로 검사 1회 (백그라운드). 결과는 Spring DB에 적재 */
export async function triggerInspectionFromFile(path: string): Promise<{ message: string }> {
  const res = await fetch(edgeUrl('/edge/inspect/from-file'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<{ message: string }>
}

/** 브라우저 파일 업로드로 검사 1회 (백그라운드). 결과는 Spring DB에 적재 */
export async function triggerInspectionFromUpload(
  file: File,
  stage2Source: Stage2SourceMode
): Promise<{ message: string }> {
  const formData = new FormData()
  formData.append('image', file)

  const res = await fetch(edgeUrl('/edge/inspect/upload'), {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<{ message: string }>
}

/** 엣지 서버 상태 확인 */
export async function fetchEdgeHealth() {
  const res = await fetch(edgeUrl('/edge/health'))
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}
