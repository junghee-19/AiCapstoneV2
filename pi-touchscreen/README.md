# Pi Touchscreen UI

라즈베리파이 터치스크린(키오스크) 전용 정적 UI.

## 구조

```
pi-touchscreen/
├── index.html    # 3-화면 컨테이너 (LIVE / BUSY / RESULT)
├── style.css     # 터치 친화 큼지막 스타일 (작은 디스플레이 가정)
└── app.js        # SSE 수신 + 화면 전환 + 결함 박스 캔버스 그리기
```

## 동작 방식

1. Pi 에서 `edge` FastAPI 서버가 기동되면
2. 브라우저(키오스크 모드)가 `http://localhost:8000/touch` 를 연다
3. `app.js` 가 `EventSource('/touch/events')` 로 상태(SSE) 구독
4. 검사 시작 → BUSY 화면, 검사 완료 → RESULT 화면, 6초 후 LIVE 복귀

## edge 와의 관계

- **검사 연산은 edge 폴더에서 수행** (YOLO + 정렬 + 결함 검출)
- 결과는 edge 내부의 `runtime/touchscreen_state.py` 가 SSE 로 푸시
- **터치스크린은 Pi 안에서 즉시 결과를 받아 표시** (Spring 왕복 불필요)
- (별개로) edge 가 결과를 Spring DB 에 HTTP POST 하는 흐름은 그대로 유지 — 대시보드 통계용

## 개발 메모

- 서버는 `edge/api/touchscreen.py` 가 담당. 이 폴더는 정적 파일만.
- 폰트/아이콘은 시스템 기본만 사용 (외부 CDN 의존 없음 — 키오스크 오프라인 환경 대비).
- `app.js` 는 의존성 없는 vanilla JS. 빌드 도구 불필요.

## 키오스크 실행 (Pi 에서)

```bash
# edge 서버 (다른 셸)
cd ~/AiCapstoneV2/edge
source .venv/bin/activate
python main.py

# 키오스크 브라우저
chromium --kiosk http://localhost:8000/touch
```
