(() => {
  const body = document.body
  const liveStream = document.getElementById('live-stream')
  const busyMessage = document.getElementById('busy-message')
  const resultHeader = document.getElementById('result-header')
  const resultIcon = document.getElementById('result-icon')
  const resultText = document.getElementById('result-text')
  const resultDefectsCount = document.getElementById('result-defects-count')
  const canvas = document.getElementById('result-canvas')
  const ctx = canvas.getContext('2d')

  // SSE 연결 — 자동 재연결은 EventSource 가 기본 제공
  const events = new EventSource('/touch/events')

  events.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      handleStateUpdate(data)
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

    const ICON = { PASS: '✓', FAIL: '✕', SKIPPED: '?' }
    resultIcon.textContent = ICON[result] || '?'
    resultText.textContent = result

    const defects = state.defects || []
    if (result === 'PASS') {
      resultDefectsCount.textContent = '정상 — 결함 없음'
    } else if (result === 'FAIL') {
      resultDefectsCount.textContent = `결함 ${defects.length}건 검출`
    } else {
      resultDefectsCount.textContent = '검사 건너뜀 (정렬 실패)'
    }

    if (state.imageUrl) {
      drawCapturedImage(state.imageUrl, defects, result)
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

  function drawCapturedImage(url, defects, result) {
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
        ctx.lineWidth = Math.max(3, canvas.width / 250)
        ctx.strokeStyle = '#ef4444'
        ctx.fillStyle = 'rgba(239, 68, 68, 0.15)'
        ctx.font = `${Math.max(14, canvas.width / 60)}px sans-serif`

        defects.forEach((d) => {
          const x = d.bboxX * ratio
          const y = d.bboxY * ratio
          const w = d.bboxWidth * ratio
          const h = d.bboxHeight * ratio
          ctx.fillRect(x, y, w, h)
          ctx.strokeRect(x, y, w, h)

          // 라벨
          const label = d.defectType || '결함'
          ctx.fillStyle = '#ef4444'
          const padding = 4
          const labelY = y > 24 ? y - padding : y + h + 18
          ctx.fillText(label, x, labelY)
          ctx.fillStyle = 'rgba(239, 68, 68, 0.15)'
        })
      }
    }
    img.onerror = () => {
      console.warn('[touch] 결과 이미지 로드 실패:', url)
    }
    img.src = url
  }

  // 페이지 로드 시 라이브 스트림 강제 시작
  if (liveStream && !liveStream.src) {
    liveStream.src = '/edge/camera/stream'
  }
})()
