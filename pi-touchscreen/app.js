(() => {
  const body = document.body
  const liveStream = document.getElementById('live-stream')
  const busyMessage = document.getElementById('busy-message')
  const resultHeader = document.getElementById('result-header')
  const resultText = document.getElementById('result-text')
  const canvas = document.getElementById('result-canvas')
  const ctx = canvas.getContext('2d')

  // ── 결함 종류별 색상·라벨 (대시보드와 동일 매핑) ─────────────────────────
  const DEFECT_COLOR = {
    TRACE_OPEN:       '#f97316',
    METAL_DAMAGE:     '#ef4444',
    FIDUCIAL_MISSING: '#a855f7',
    trace_open:       '#f97316',
    metal_damage:     '#ef4444',
    pinhole:          '#eab308',
    short:            '#dc2626',
    mount_hole:           '#22d3ee',
    gold_finger_row:      '#fb7185',
    fiducial:             '#4ade80',
    smd_array_block:      '#a78bfa',
    ic_chip:              '#fbbf24',
    edge_connector_zone:  '#f472b6',
  }
  const DEFECT_LABEL = {
    TRACE_OPEN:   '단선',
    METAL_DAMAGE: '까짐',
    FIDUCIAL_MISSING: '마크 누락',
    trace_open:   '단선',
    metal_damage: '까짐',
    pinhole:      '핀홀',
    short:        '단락',
    mount_hole:           '고정홀',
    gold_finger_row:      '금핑거 열',
    fiducial:             '피듀셜',
    smd_array_block:      'SMD 어레이',
    ic_chip:               'IC',
    edge_connector_zone:   '에지 커넥터',
  }
  const colorOf = (t) => DEFECT_COLOR[t] || '#ef4444'
  const labelOf = (t) => DEFECT_LABEL[t] || t || '결함'

  // ── SSE ────────────────────────────────────────────────────────────────
  const events = new EventSource('/touch/events')
  events.onmessage = (e) => {
    try {
      handleStateUpdate(JSON.parse(e.data))
    } catch (err) {
      console.error('[touch] SSE 파싱 실패:', err)
    }
  }
  events.onerror = (err) => {
    console.warn('[touch] SSE 연결 끊김 (자동 재시도):', err)
  }

  function handleStateUpdate(state) {
    const status = state.status || 'IDLE'
    body.dataset.status = status

    if (status === 'BUSY') {
      busyMessage.textContent = state.message || '검사 중...'
    }
    if (status === 'RESULT') {
      renderResult(state)
    }
    if (status === 'IDLE') {
      // 라이브 스트림이 끊겼을 수 있으니 강제 새로고침
      liveStream.src = `/edge/camera/stream?t=${Date.now()}`
    }
  }

  function renderResult(state) {
    const result = state.result || 'SKIPPED'
    resultHeader.dataset.result = result
    resultText.textContent = result

    const defects = state.defects || []
    const fiducials = state.fiducials || []
    if (state.imageUrl) {
      drawCapturedImage(state.imageUrl, defects, fiducials, result)
    } else {
      // 이미지 없을 때 — 캔버스 비우고 텍스트만
      canvas.width = 800
      canvas.height = 600
      ctx.fillStyle = '#0b0f17'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = '#94a3b8'
      ctx.font = '20px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('이미지 없음', canvas.width / 2, canvas.height / 2)
    }
  }

  function drawCapturedImage(url, defects, fiducials, result) {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      // 캔버스 크기를 이미지 비율에 맞춤
      const wrap = canvas.parentElement
      const maxW = wrap.clientWidth
      const maxH = wrap.clientHeight
      const ratio = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight, 1)
      canvas.width = Math.round(img.naturalWidth * ratio)
      canvas.height = Math.round(img.naturalHeight * ratio)

      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

      if (result === 'FAIL' && defects.length) {
        drawDefectBoxes(defects, ratio)
      }
      if (fiducials.length) {
        drawFiducialMarkers(fiducials, ratio)
      }
    }
    img.onerror = () => {
      console.warn('[touch] 결과 이미지 로드 실패:', url)
    }
    img.src = url
  }

  // ── 결함 박스 + 라벨 그리기 (대시보드 DefectBox 와 동일 스타일) ────────────
  function drawDefectBoxes(defects, ratio) {
    const stroke = Math.max(2, canvas.width / 320)
    const fontSize = Math.max(11, Math.round(canvas.width / 70))
    ctx.lineWidth = stroke
    ctx.font = `700 ${fontSize}px ui-monospace, monospace`
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'

    defects.forEach((d) => {
      const x = d.bboxX * ratio
      const y = d.bboxY * ratio
      const w = d.bboxWidth * ratio
      const h = d.bboxHeight * ratio
      const color = colorOf(d.defectType)
      const label = labelOf(d.defectType)

      // 박스 (테두리만, 채우지 않음)
      ctx.strokeStyle = color
      ctx.strokeRect(x, y, w, h)

      // 라벨 배경 + 텍스트
      const padX = 6
      const padY = 3
      const textWidth = ctx.measureText(label).width
      const labelW = textWidth + padX * 2
      const labelH = fontSize + padY * 2
      const labelX = x
      const labelY = y > labelH ? y - labelH : y + h
      // 어두운 배경
      ctx.fillStyle = 'rgba(15, 23, 42, 0.86)'
      ctx.fillRect(labelX, labelY, labelW, labelH)
      // 색상 테두리
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.strokeRect(labelX, labelY, labelW, labelH)
      // 텍스트 (결함 색상)
      ctx.fillStyle = color
      ctx.fillText(label, labelX + padX, labelY + padY)

      // 다음 박스를 위해 stroke 굵기 복구
      ctx.lineWidth = stroke
    })
  }

  // ── 피듀셜 마커 그리기 (대시보드 FiducialMarker 와 동일 스타일) ──────────────
  function drawFiducialMarkers(fiducials, ratio) {
    const color = '#38bdf8'
    // 캔버스 크기에 맞춰 마커 크기 스케일 — 대시보드 SVG 기본값(arm=16) 기준으로
    // 캔버스가 클수록 마커도 키워야 보임
    const scale = Math.max(1, canvas.width / 800)
    const arm = 16 * scale
    const gap = 5 * scale
    const radius = 11 * scale
    const stroke = 1.75 * scale
    const labelFont = Math.round(10 * scale)
    const coordFont = Math.round(13 * scale)

    fiducials.forEach((f) => {
      const sx = f.x * ratio
      const sy = f.y * ratio

      // 십자선 (가운데 빔)
      ctx.strokeStyle = color
      ctx.lineWidth = stroke
      ctx.lineCap = 'round'
      ctx.beginPath()
      ctx.moveTo(sx - arm, sy); ctx.lineTo(sx - gap, sy)
      ctx.moveTo(sx + gap, sy); ctx.lineTo(sx + arm, sy)
      ctx.moveTo(sx, sy - arm); ctx.lineTo(sx, sy - gap)
      ctx.moveTo(sx, sy + gap); ctx.lineTo(sx, sy + arm)
      ctx.stroke()

      // 중심 원
      ctx.beginPath()
      ctx.arc(sx, sy, radius, 0, Math.PI * 2)
      ctx.stroke()

      // 라벨 (예: "F1 95%") — 마크 위쪽
      const cap =
        f.confidence != null && !Number.isNaN(f.confidence)
          ? `${f.label} ${(f.confidence * 100).toFixed(0)}%`
          : f.label
      ctx.font = `600 ${labelFont}px ui-monospace, monospace`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      const labelTextW = ctx.measureText(cap).width
      const tw = Math.min(160 * scale, Math.max(44 * scale, labelTextW + 12 * scale))
      const labelH = labelFont + 6
      const labelY = sy - 14 * scale - labelH / 2
      ctx.fillStyle = 'rgba(15, 23, 42, 0.78)'
      ctx.fillRect(sx - tw / 2, labelY - labelH / 2, tw, labelH)
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)'
      ctx.lineWidth = 1
      ctx.strokeRect(sx - tw / 2, labelY - labelH / 2, tw, labelH)
      ctx.fillStyle = '#e0f2fe'
      ctx.fillText(cap, sx, labelY)

      // 좌표 박스 (예: "(123, 456)") — 마크 아래쪽
      const coord = `(${Math.round(f.x)}, ${Math.round(f.y)})`
      ctx.font = `700 ${coordFont}px ui-monospace, monospace`
      const coordTextW = ctx.measureText(coord).width
      const cw = Math.max(176 * scale, coordTextW + 16 * scale)
      const ch = coordFont + 12
      const coordY = sy + arm + 2 * scale + ch / 2
      ctx.fillStyle = 'rgba(15, 23, 42, 0.95)'
      ctx.fillRect(sx - cw / 2, coordY - ch / 2, cw, ch)
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.85)'
      ctx.lineWidth = 1.5
      ctx.strokeRect(sx - cw / 2, coordY - ch / 2, cw, ch)
      ctx.fillStyle = '#e0f2fe'
      ctx.fillText(coord, sx, coordY)

      // stroke 굵기 복구
      ctx.lineWidth = stroke
      ctx.strokeStyle = color
    })
  }

  // 페이지 로드 시 라이브 스트림 강제 시작
  if (liveStream && !liveStream.src) {
    liveStream.src = '/edge/camera/stream'
  }

  // ── RESULT 화면 탭 시 LIVE 로 복귀 ─────────────────────────────────────
  const resultScreen = document.querySelector('.screen-result')
  if (resultScreen) {
    const dismiss = () => {
      // RESULT 상태일 때만 작동 (IDLE/BUSY 에서는 무시)
      if (body.dataset.status !== 'RESULT') return
      fetch('/touch/dismiss', { method: 'POST' }).catch((err) => {
        console.warn('[touch] dismiss 요청 실패:', err)
      })
    }
    resultScreen.addEventListener('click', dismiss)
    resultScreen.addEventListener('touchend', (e) => {
      e.preventDefault()
      dismiss()
    }, { passive: false })
  }
})()
