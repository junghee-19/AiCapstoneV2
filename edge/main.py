"""
엣지 디바이스 메인 진입점

FastAPI 서버를 기동하고, 2-Stage 비전 검사 파이프라인을 실행한다.

실행 방법:
    # 개발 환경 (더미 모드)
    ENVIRONMENT=development uvicorn main:app --host 0.0.0.0 --port 8000 --reload

    # 라즈베리파이 운영 환경
    uvicorn main:app --host 0.0.0.0 --port 8000

검사 파이프라인 흐름:
    ┌──────────────────────────────────────────────────────────────┐
    │  1. 카메라 캡처 (1080p)                                        │
    │  2-A. Stage 1: YOLO → 피듀셜 탐지 → 기울기 측정 → 이미지 회전 보정  │
    │  2-B. Stage 2: 보정된 ROI Crop → YOLO → 결함 탐지              │
    │  3. 판정 (PASS / FAIL)                                         │
    │  4. GPIO 즉시 알람 (부저 + LED)                                 │
    │  5. Spring Boot 서버로 JSON 전송                               │
    └──────────────────────────────────────────────────────────────┘
"""

import asyncio
from collections import Counter
import json
import logging
import math
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

# 캡처 저장·정적 서빙 경로 (settings와 무관, 항상 main.py 기준 edge/captures)
_EDGE_DIR = Path(__file__).resolve().parent
CAPTURES_DIR = _EDGE_DIR / "captures"
DEMO_SAMPLES_DIR = _EDGE_DIR / "demo_samples"
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.router import router as edge_router
from api.sender import ServerSender, create_dummy_packet
from capture.camera import CameraCapture
from config.settings import settings
from inference.alignment import (
    align_image_to_reference_by_fiducials,
    compute_alignment,
    crop_inspection_roi_with_offset,
)
from inference.yolo_detector import YoloDetector
from models.schemas import (
    AlignmentResult,
    DefectPayload,
    InspectionPacket,
    InspectionResult,
)
from runtime.inspection_control import stop_auto_inspection
from ws.client import run_edge_ws_client

# ── 로깅 설정 ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


def _fiducial_confidences(alignment: AlignmentResult) -> tuple[Optional[float], Optional[float]]:
    """피듀셜 DetectionItem.confidence → 서버 전송용 (없으면 None)."""
    f1 = float(alignment.fiducial1.confidence) if alignment.fiducial1 else None
    f2 = float(alignment.fiducial2.confidence) if alignment.fiducial2 else None
    return f1, f2


def _save_frame(frame: np.ndarray, save_dir: Optional[Path] = None) -> str:
    """메모리 프레임을 captures 아래에 저장하고 절대 경로를 반환한다."""
    base = save_dir if save_dir is not None else CAPTURES_DIR
    base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = base / f"{timestamp}.jpg"
    cv2.imwrite(str(file_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    logger.info("[카메라] 이미지 저장: %s", file_path)
    return str(file_path)


def _stage1_detector() -> Optional[YoloDetector]:
    """현재 설정에 맞는 Stage 1 피듀셜 탐지기 반환."""
    return fiducial_detector if settings.USE_SEPARATE_MODELS else detector


async def _wait_for_centered_stable_pcb_frame() -> tuple[np.ndarray, str, list, int, AlignmentResult]:
    """
    PCB가 화면 중앙에 들어오고 일정 시간 거의 움직이지 않을 때까지 대기한 뒤 캡처한다.

    판단 기준:
    - 피듀셜 2개 검출
    - 화면 중심 근처
    - 직전 유효 프레임 대비 중점/간격/각도 변화가 허용치 이하
    - 위 상태가 CAMERA_STABLE_HOLD_SEC 동안 연속 유지

    타임아웃 시에는 최신 유효 프레임으로 강제 진행한다.
    """
    if camera is None:
        raise RuntimeError("카메라가 초기화되지 않았습니다.")

    stage1 = _stage1_detector()
    if stage1 is None:
        raise RuntimeError("Stage 1 탐지기가 로드되지 않았습니다.")

    timeout_deadline = time.perf_counter() + settings.CAMERA_STABLE_WAIT_TIMEOUT_SEC
    stable_since: Optional[float] = None
    last_signature: Optional[tuple[float, float, float, float]] = None
    latest_valid: Optional[tuple[np.ndarray, list, int, AlignmentResult]] = None

    logger.info(
        "[캡처대기] 중앙 + 안정 상태 대기 시작 (hold=%.1fs, timeout=%.1fs)",
        settings.CAMERA_STABLE_HOLD_SEC,
        settings.CAMERA_STABLE_WAIT_TIMEOUT_SEC,
    )

    while True:
        frame = camera.capture()
        fiducials, fiducial_ms = _stage1_detector().detect_fiducials(frame)
        alignment = compute_alignment(fiducials)

        if alignment.fiducial1 is not None and alignment.fiducial2 is not None:
            h, w = frame.shape[:2]
            center_x = (alignment.fiducial1.center_x + alignment.fiducial2.center_x) / 2.0
            center_y = (alignment.fiducial1.center_y + alignment.fiducial2.center_y) / 2.0
            span_px = math.hypot(
                alignment.fiducial2.center_x - alignment.fiducial1.center_x,
                alignment.fiducial2.center_y - alignment.fiducial1.center_y,
            )
            signature = (center_x, center_y, span_px, float(alignment.angle_error_deg))
            latest_valid = (frame, fiducials, fiducial_ms, alignment)

            center_dx = abs(center_x - (w / 2.0))
            center_dy = abs(center_y - (h / 2.0))
            centered = (
                center_dx <= (w * settings.CAMERA_CENTER_TOLERANCE_RATIO)
                and center_dy <= (h * settings.CAMERA_CENTER_TOLERANCE_RATIO)
            )

            stable_motion = False
            if last_signature is not None:
                prev_cx, prev_cy, prev_span, prev_angle = last_signature
                stable_motion = (
                    abs(center_x - prev_cx) <= settings.CAMERA_STABLE_CENTER_DELTA_PX
                    and abs(center_y - prev_cy) <= settings.CAMERA_STABLE_CENTER_DELTA_PX
                    and abs(span_px - prev_span) <= settings.CAMERA_STABLE_SPAN_DELTA_PX
                    and abs(float(alignment.angle_error_deg) - prev_angle) <= settings.CAMERA_STABLE_ANGLE_DELTA_DEG
                )

            if alignment.is_aligned and centered and (stable_motion or stable_since is None):
                if stable_since is None:
                    stable_since = time.perf_counter()
                    logger.info(
                        "[캡처대기] 안정 후보 시작 — center=(%.0f,%.0f), span=%.1fpx, angle=%.2f°",
                        center_x,
                        center_y,
                        span_px,
                        float(alignment.angle_error_deg),
                    )

                held_for = time.perf_counter() - stable_since
                if held_for >= settings.CAMERA_STABLE_HOLD_SEC:
                    image_path = _save_frame(frame)
                    logger.info("[캡처대기] 안정 상태 %.2fs 유지 확인 — 캡처", held_for)
                    return frame, image_path, fiducials, fiducial_ms, alignment
            else:
                if stable_since is not None:
                    logger.info("[캡처대기] 안정 상태 해제 — 중심/움직임 조건 재대기")
                stable_since = None

            last_signature = signature
        else:
            if stable_since is not None:
                logger.info("[캡처대기] 피듀셜 부족으로 안정 상태 해제")
            stable_since = None
            last_signature = None

        if time.perf_counter() >= timeout_deadline:
            if latest_valid is not None:
                frame, fiducials, fiducial_ms, alignment = latest_valid
                image_path = _save_frame(frame)
                logger.warning("[캡처대기] 타임아웃 — 최신 유효 프레임으로 강제 캡처")
                return frame, image_path, fiducials, fiducial_ms, alignment

            logger.warning("[캡처대기] 타임아웃 — 유효 피듀셜 없이 최신 프레임 강제 캡처")
            frame = camera.capture()
            image_path = _save_frame(frame)
            return frame, image_path, [], 0, compute_alignment([])

        await asyncio.sleep(settings.CAMERA_STABLE_SAMPLE_INTERVAL_SEC)


# ── 전역 싱글턴 객체 (앱 수명 주기 동안 유지) ─────────────────────────────────
camera:           Optional[CameraCapture] = None
detector:         Optional[YoloDetector]  = None  # 단일 모델 모드
sender:           Optional[ServerSender]   = None
gpio:             Any = None
board_id_detector: Optional[YoloDetector] = None
board_profiles: dict[str, dict[str, Any]] = {}
board_detector_cache: dict[str, YoloDetector] = {}
ws_stop_event: Optional[asyncio.Event] = None
ws_task: Optional[asyncio.Task[None]] = None
_patchcore_detector: Any = None  # inference.anomaly_patchcore.PatchCoreDetector — lazy load


def _resolve_edge_relative_path(path_like: str) -> Path:
    p = Path(path_like)
    if p.is_absolute():
        return p
    return (_EDGE_DIR / p).resolve()


def _load_board_profiles() -> dict[str, dict[str, Any]]:
    config_path = _resolve_edge_relative_path(settings.BOARD_PROFILES_PATH)
    if not config_path.exists():
        logger.warning("[멀티보드] board profile 파일이 없어 멀티보드를 비활성화합니다: %s", config_path)
        return {}
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("[멀티보드] board profile 로드 실패: %s", e)
        return {}
    if not isinstance(raw, dict):
        logger.error("[멀티보드] board profile 최상위는 object여야 합니다.")
        return {}
    profiles: dict[str, dict[str, Any]] = {}
    for board_type, profile in raw.items():
        if not isinstance(profile, dict):
            continue
        identifiers = profile.get("identifier_classes") or []
        model_path = profile.get("model_path") or settings.YOLO_WEIGHTS_PATH
        profiles[str(board_type)] = {
            "identifier_classes": [str(x).lower() for x in identifiers if str(x).strip()],
            "model_path": str(model_path),
            "expected_counts": profile.get("expected_counts") or {},
        }
    logger.info("[멀티보드] profiles 로드: %s", list(profiles.keys()))
    return profiles


def _select_board_type(frame: np.ndarray) -> tuple[Optional[str], float, str]:
    if board_id_detector is None or not board_profiles:
        return None, 0.0, ""
    detections, _ = board_id_detector.detect(frame, target_class=None, conf=settings.BOARD_ID_MIN_CONFIDENCE)
    best_board: Optional[str] = None
    best_conf = 0.0
    best_cls = ""
    for d in detections:
        cls_name = d.defect_type.lower()
        for board_type, profile in board_profiles.items():
            ids = profile.get("identifier_classes", [])
            if cls_name in ids and d.confidence > best_conf:
                best_board = board_type
                best_conf = d.confidence
                best_cls = cls_name
    return best_board, best_conf, best_cls


def _get_board_detector(model_path: str) -> Optional[YoloDetector]:
    key = str(_resolve_edge_relative_path(model_path))
    det = board_detector_cache.get(key)
    if det is not None:
        return det
    det = YoloDetector(weights_path=model_path, confidence_threshold=settings.YOLO_CONFIDENCE_THRESHOLD)
    det.load()
    board_detector_cache[key] = det
    return det


# ── FastAPI 수명 주기 이벤트 ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 앱 시작/종료 시 실행되는 수명 주기 관리자.

    [시작 시]
    - 카메라 초기화 및 오토포커스 비활성화
    - YOLO 모델 로드 (최초 1회만 수행, 이후 캐시 재사용)
    - GPIO 초기화
    - 서버 HTTP 세션 준비

    [종료 시]
    - 카메라 자원 해제
    - GPIO 핀 안전 초기화
    - HTTP 세션 종료
    """
    global camera, detector, sender, board_id_detector, board_profiles, ws_stop_event, ws_task
    logger.info("=" * 60)
    logger.info("   PCB 비전 검사 스테이션 시작 [%s]", settings.ENVIRONMENT.upper())
    logger.info("=" * 60)

    # 카메라 초기화
    camera = CameraCapture()
    try:
        camera.open()
        logger.info("[시작] 카메라 초기화 완료")
    except RuntimeError as e:
        logger.warning("[시작] 카메라 초기화 실패 (더미 모드로 계속): %s", e)
        camera = None

    # 단일 통합 모델: best.pt 하나로 모든 클래스 탐지
    logger.info("[시작] 단일 통합 모델 로드 모드")
    detector = YoloDetector()
    detector.load()

    if settings.MULTI_BOARD_ENABLED:
        board_profiles = _load_board_profiles()
        if board_profiles:
            board_id_detector = YoloDetector(
                weights_path=settings.BOARD_ID_WEIGHTS_PATH,
                confidence_threshold=settings.BOARD_ID_MIN_CONFIDENCE,
            )
            board_id_detector.load()
        else:
            logger.warning("[멀티보드] 유효한 profiles가 없어 단일보드 모드로 동작합니다.")

    # HTTP 송신 세션 준비
    sender = ServerSender()
    logger.info("[시작] 서버 연결 준비 완료: %s", settings.SERVER_BASE_URL)
    ws_stop_event = asyncio.Event()
    ws_task = asyncio.create_task(run_edge_ws_client(ws_stop_event), name="edge-server-ws")
    logger.info("[시작] 서버 WebSocket 제어 루프 준비 완료")
    logger.info("[시작] 초기화 완료 — 검사 대기 중")

    yield  # ← FastAPI 앱이 여기서 실행된다.

    # ── 종료 시 자원 정리 ─────────────────────────────────────────────────────
    logger.info("[종료] 자원 해제 시작...")
    await stop_auto_inspection()
    if ws_stop_event is not None:
        ws_stop_event.set()
    if ws_task is not None and not ws_task.done():
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
    if camera:
        camera.release()
    if sender:
        sender.close()
    logger.info("[종료] 정상 종료 완료.")


# ── FastAPI 앱 인스턴스 ───────────────────────────────────────────────────────

app = FastAPI(
    title="PCB Edge Vision Inspection API",
    description="라즈베리파이 5 엣지 디바이스 로컬 제어 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정: 같은 LAN의 운영자 PC 브라우저에서 직접 접근 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ai-capstone-v2.vercel.app",
        "https://ai-capstone-v2-junghee-19s-projects.vercel.app",
        "https://deepsight.웹.한국",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 엣지 라우터 등록 (/edge/health, /edge/inspect/dummy 등)
app.include_router(edge_router)

# 터치스크린 라우터 등록 (/touch, /touch/events)
from api.touchscreen import router as touchscreen_router
app.include_router(touchscreen_router)

# 캡처 이미지 정적 서빙 — edge/captures 고정 (uvicorn 실행 위치와 무관). 라우터보다 뒤에 마운트.
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
DEMO_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/captures", StaticFiles(directory=str(CAPTURES_DIR)), name="captures")
app.mount("/demo_samples", StaticFiles(directory=str(DEMO_SAMPLES_DIR)), name="demo_samples")

# 터치스크린 정적 자원 (HTML/CSS/JS) — 프로젝트 루트의 pi-touchscreen/ 에서 서빙
# edge 폴더와 분리해 별도 디렉토리로 둠 (UI 와 추론 로직의 책임 분리)
_TOUCHSCREEN_DIR = _EDGE_DIR.parent / "pi-touchscreen"
_TOUCHSCREEN_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/touch/static", StaticFiles(directory=str(_TOUCHSCREEN_DIR)), name="touch-static")


# ── 2-Stage 비전 검사 파이프라인 ──────────────────────────────────────────────

async def run_inspection_pipeline(
    stage2_source_mode: Optional[str] = None,
    *,
    force_camera: bool = False,
) -> Optional[InspectionPacket]:
    """
    PCB 검사 전체 파이프라인을 실행한다.

    개발(ENVIRONMENT=development) 환경:
        카메라/YOLO 없이 더미 데이터로 파이프라인 흐름을 테스트한다.
        단, force_camera=True인 수동 트리거는 실제 카메라 캡처를 수행한다.

    운영(ENVIRONMENT=production) 환경:
        실제 카메라 캡처 → YOLO 추론 → GPIO 알람 → 서버 전송을 수행한다.

    Returns:
        생성된 InspectionPacket (서버 전송 완료 여부와 무관하게 반환)
        파이프라인 오류 시 None
    """
    pipeline_start = time.perf_counter()

    # ── 개발 환경: 더미 모드 ─────────────────────────────────────────────────
    if camera is None:
        if force_camera:
            logger.error("[파이프라인] 실제 카메라 검사 요청이지만 카메라가 초기화되지 않았습니다.")
            return None
        logger.info("[파이프라인] 카메라 없음 — 더미 모드 실행")
        packet = create_dummy_packet()

        # 서버 전송
        if sender:
            sender.send(packet)

        total_ms = int((time.perf_counter() - pipeline_start) * 1000)
        logger.info("[파이프라인] 더미 완료: %s (%dms)", packet.result.value, total_ms)
        return packet

    if settings.ENVIRONMENT == "development" and not force_camera:
        logger.info("[파이프라인] 더미 모드 실행")
        packet = create_dummy_packet()

        # 서버 전송
        if sender:
            sender.send(packet)

        total_ms = int((time.perf_counter() - pipeline_start) * 1000)
        logger.info("[파이프라인] 더미 완료: %s (%dms)", packet.result.value, total_ms)
        return packet

    # ── 운영 환경: 실제 파이프라인 ───────────────────────────────────────────
    try:
        # STEP 1: 중앙 + 안정 상태 대기 후 이미지 캡처
        logger.info("[파이프라인] STEP 1 — 중앙/안정 상태 확인 후 이미지 캡처")
        if gpio:
            gpio.signal_processing()  # 처리 중 LED 점멸

        frame, image_path, fiducials, fiducial_ms, alignment = await _wait_for_centered_stable_pcb_frame()

        debug_imshow = settings.ENVIRONMENT == "development" and not force_camera
        mode = (stage2_source_mode or settings.STAGE2_SOURCE_MODE).strip().lower()
        return _run_production_vision_pipeline(
            frame,
            image_path,
            pipeline_start,
            stage2_source_mode=mode,
            debug_imshow=debug_imshow,
            fiducials_precomputed=fiducials,
            fiducial_ms_precomputed=fiducial_ms,
            alignment_precomputed=alignment,
        )

    except Exception as e:
        logger.error("[파이프라인] 예외 발생: %s", e, exc_info=True)
        return None


def _run_production_vision_pipeline(
    frame: np.ndarray,
    image_path: str,
    pipeline_start: float,
    *,
    stage2_source_mode: str = "aligned",
    debug_imshow: bool = False,
    fiducials_precomputed=None,
    fiducial_ms_precomputed: Optional[int] = None,
    alignment_precomputed: Optional[AlignmentResult] = None,
) -> Optional[InspectionPacket]:
    """카메라/파일 공통 — Stage 1·2 및 전송."""
    try:
        if debug_imshow:
            cv2.imshow("Captured Frame", cv2.resize(frame, (640, 360)))
            cv2.waitKey(1)

        stage1_detector = detector
        stage2_detector = detector
        selected_board_type: Optional[str] = None
        selected_expected_counts: dict[str, int] = {}
        if settings.MULTI_BOARD_ENABLED and board_profiles:
            board_type, board_conf, board_cls = _select_board_type(frame)
            if board_type:
                profile = board_profiles[board_type]
                selected_board_type = board_type
                selected_expected_counts = profile.get("expected_counts") or {}
                routed = _get_board_detector(profile["model_path"])
                if routed is not None:
                    # 통일 모드: Stage1/Stage2 모두 보드별 모델로 라우팅.
                    stage1_detector = routed
                    stage2_detector = routed
                    logger.info(
                        "[멀티보드] board=%s (class=%s, conf=%.3f) -> model=%s",
                        board_type,
                        board_cls,
                        board_conf,
                        profile["model_path"],
                    )
            else:
                logger.warning("[멀티보드] 보드 식별 실패 (min_conf=%.2f)", settings.BOARD_ID_MIN_CONFIDENCE)
                if settings.BOARD_UNKNOWN_POLICY == "fallback_default" and settings.DEFAULT_BOARD_TYPE:
                    fallback = board_profiles.get(settings.DEFAULT_BOARD_TYPE)
                    if fallback:
                        routed = _get_board_detector(fallback["model_path"])
                        if routed is not None:
                            stage1_detector = routed
                            stage2_detector = routed
                            selected_board_type = settings.DEFAULT_BOARD_TYPE
                            selected_expected_counts = fallback.get("expected_counts") or {}
                            logger.warning(
                                "[멀티보드] unknown -> fallback_default=%s (%s)",
                                settings.DEFAULT_BOARD_TYPE,
                                fallback["model_path"],
                            )
                elif settings.BOARD_UNKNOWN_POLICY == "abort":
                    packet = _build_packet(
                        result=InspectionResult.FAIL,
                        f1x=None, f1y=None, f2x=None, f2y=None,
                        f1_conf=None, f2_conf=None,
                        angle_error=0.0,
                        inference_ms=0,
                        defects=[
                            DefectPayload(
                                defect_type="BOARD_TYPE_UNKNOWN",
                                confidence=1.0,
                                bbox_x=0,
                                bbox_y=0,
                                bbox_width=1,
                                bbox_height=1,
                            )
                        ],
                        image_path=image_path,
                        pipeline_start=pipeline_start,
                        device_id=selected_board_type,
                    )
                    _finalize(packet)
                    return packet

        # STEP 2-A: Stage 1 — 피듀셜 마크 탐지 및 정렬 검사
        if fiducials_precomputed is None or fiducial_ms_precomputed is None or alignment_precomputed is None:
            logger.info("[파이프라인] STEP 2-A — 피듀셜 마크 탐지")
            stage1 = fiducial_detector if settings.USE_SEPARATE_MODELS else detector
            fiducials, fiducial_ms = stage1.detect_fiducials(frame)
            alignment = compute_alignment(fiducials)
        else:
            logger.info("[파이프라인] STEP 2-A — 사전 감지된 피듀셜 사용")
            fiducials = fiducials_precomputed
            fiducial_ms = fiducial_ms_precomputed
            alignment = alignment_precomputed

        measured_skew_deg = alignment.angle_error_deg

        logger.info(
            "[파이프라인] 기울기 측정: %s, |각도|: %.2f°",
            "보정 가능" if alignment.is_aligned else "한도 초과",
            measured_skew_deg,
        )

        f1x = f1y = f2x = f2y = None
        if alignment.fiducial1:
            f1x, f1y = alignment.fiducial1.center_x, alignment.fiducial1.center_y
        if alignment.fiducial2:
            f2x, f2y = alignment.fiducial2.center_x, alignment.fiducial2.center_y

        if len(fiducials) < 2:
            logger.info("[파이프라인] PCB/피듀셜 미검출 → SKIPPED, Stage 2 건너뜀")
            f1c, f2c = _fiducial_confidences(alignment)
            packet = _build_packet(
                result=InspectionResult.SKIPPED,
                f1x=f1x, f1y=f1y, f2x=f2x, f2y=f2y,
                f1_conf=f1c, f2_conf=f2c,
                angle_error=measured_skew_deg,
                inference_ms=fiducial_ms,
                defects=[],
                image_path=image_path,
                pipeline_start=pipeline_start,
            )
            _finalize(packet)
            return packet

        if not alignment.is_aligned:
            logger.warning("[파이프라인] 피듀셜/기울기 조건 불충족 → FAIL, Stage 2 건너뜀")
            f1c, f2c = _fiducial_confidences(alignment)
            packet = _build_packet(
                result=InspectionResult.FAIL,
                f1x=f1x, f1y=f1y, f2x=f2x, f2y=f2y,
                f1_conf=f1c, f2_conf=f2c,
                angle_error=measured_skew_deg,
                inference_ms=fiducial_ms,
                defects=[],
                image_path=image_path,
                pipeline_start=pipeline_start,
                device_id=selected_board_type,
            )
            _finalize(packet)
            return packet

        raw_frame = frame.copy()
        stage2_mode = (stage2_source_mode or "aligned").strip().lower()
        if stage2_mode == "deskew":
            # 하위 호환: 기존 deskew 모드는 aligned로 통일 처리
            stage2_mode = "aligned"
        if stage2_mode not in {"raw", "aligned"}:
            logger.warning("[파이프라인] 알 수 없는 Stage2 모드 '%s' → aligned로 대체", stage2_mode)
            stage2_mode = "aligned"

        # Stage2 raw 모드에서 대시보드 오버레이가 원본 좌표계를 유지하도록
        # 정합 전 피듀셜 중심을 보존한다.
        pre_align_f1x, pre_align_f1y = f1x, f1y
        pre_align_f2x, pre_align_f2y = f2x, f2y

        logger.info("[파이프라인] STEP 2-A′ — 좌표 정합 (translation/rotation/scale)")
        aligned_frame, alignment, _m = align_image_to_reference_by_fiducials(
            frame,
            alignment,
            ref_f1=(settings.ALIGN_REF_FIDUCIAL1_X, settings.ALIGN_REF_FIDUCIAL1_Y),
            ref_f2=(settings.ALIGN_REF_FIDUCIAL2_X, settings.ALIGN_REF_FIDUCIAL2_Y),
            out_size=(settings.ALIGN_OUTPUT_WIDTH, settings.ALIGN_OUTPUT_HEIGHT),
        )
        frame = aligned_frame

        orig_p = Path(image_path)
        aligned_path = str(orig_p.parent / f"{orig_p.stem}_aligned{orig_p.suffix}")
        cv2.imwrite(aligned_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        logger.info("[파이프라인] 정합 후 이미지 저장: %s", aligned_path)

        if stage2_mode == "aligned":
            if alignment.fiducial1:
                f1x, f1y = alignment.fiducial1.center_x, alignment.fiducial1.center_y
            if alignment.fiducial2:
                f2x, f2y = alignment.fiducial2.center_x, alignment.fiducial2.center_y
        else:
            f1x, f1y = pre_align_f1x, pre_align_f1y
            f2x, f2y = pre_align_f2x, pre_align_f2y

        logger.info("[파이프라인] STEP 2-B — 결함 탐지 (입력=%s)", stage2_mode)
        stage2_source_image = raw_frame if stage2_mode == "raw" else frame
        if settings.DEFECT_INFER_ON_FULL_DESKEW:
            roi = stage2_source_image
            roi_x, roi_y = 0, 0
            logger.info(
                "[파이프라인] 결함 입력: %s 전체 이미지 (%dx%d) — DEFECT_INFER_ON_FULL_DESKEW",
                stage2_mode,
                stage2_source_image.shape[1],
                stage2_source_image.shape[0],
            )
        else:
            # ROI 크롭은 aligned 좌표계 기준이므로 raw 모드에서는 혼동 방지를 위해 full-frame만 허용.
            if stage2_mode == "raw":
                roi = stage2_source_image
                roi_x, roi_y = 0, 0
                logger.warning("[파이프라인] raw 모드에서는 ROI 대신 전체 프레임으로 Stage2 수행")
            else:
                roi, roi_x, roi_y = crop_inspection_roi_with_offset(stage2_source_image, alignment)
        defect_items, defect_ms = stage2_detector.detect_defects(roi)

        logger.info("[파이프라인] 결함 탐지: %d건", len(defect_items))

        if settings.FAIL_ON_ANY_YOLO_DETECTION:
            final_result = InspectionResult.FAIL if defect_items else InspectionResult.PASS
        else:
            # 부품/영역 다클래스 표시용: 박스는 전부 전송, 판정은 정렬만 만족하면 PASS
            final_result = InspectionResult.PASS

        defect_payloads = [
            DefectPayload(
                defect_type=d.defect_type,
                confidence=d.confidence,
                bbox_x=d.bbox.x + roi_x,
                bbox_y=d.bbox.y + roi_y,
                bbox_width=d.bbox.width,
                bbox_height=d.bbox.height,
            )
            for d in defect_items
        ]

        # expected_counts 기반 누락 판정:
        # - 보드 프로파일에 선언된 필수 클래스 기대 개수보다 실제 검출 개수가 적으면 FAIL 처리
        # - 누락 정보를 synthetic defect로 추가해 대시보드에서 원인을 바로 확인할 수 있게 한다.
        missing_payloads: list[DefectPayload] = []
        if selected_expected_counts:
            detected_counts = Counter(d.defect_type.lower() for d in defect_items)
            for cls_name, expected_raw in selected_expected_counts.items():
                try:
                    expected = int(expected_raw)
                except (TypeError, ValueError):
                    continue
                if expected <= 0:
                    continue
                cls_key = str(cls_name).strip().lower()
                detected = int(detected_counts.get(cls_key, 0))
                if detected < expected:
                    missing = expected - detected
                    missing_payloads.append(
                        DefectPayload(
                            defect_type=f"MISSING:{cls_name}:expected={expected},detected={detected},missing={missing}",
                            confidence=1.0,
                            bbox_x=0,
                            bbox_y=0,
                            bbox_width=1,
                            bbox_height=1,
                        )
                    )
                    logger.warning(
                        "[카운트판정] 누락 클래스 감지: %s (expected=%d, detected=%d, missing=%d)",
                        cls_name,
                        expected,
                        detected,
                        missing,
                    )
            if missing_payloads:
                logger.warning("[카운트판정] expected_counts 불일치로 FAIL 처리 (%d건)", len(missing_payloads))

        # ── 정상 샘플 기준 위치 검증 (Position Check) ─────────────────────────
        # 레퍼런스 등록 + REFERENCE_CHECK_ENABLED 일 때만 작동.
        # 레퍼런스의 부품 위치를 현재 이미지로 투영 → 매칭 없으면 MISSING 추가.
        if settings.REFERENCE_CHECK_ENABLED:
            from inference.reference_check import load_reference, check_missing_components
            ref_path = Path(settings.REFERENCE_PROFILE_PATH)
            if not ref_path.is_absolute():
                ref_path = _EDGE_DIR / ref_path
            reference = load_reference(ref_path)
            if reference is None:
                logger.warning("[위치검증] 레퍼런스 미등록 — 위치 검증 건너뜀: %s", ref_path)
            else:
                position_missing = check_missing_components(
                    reference,
                    current_alignment=alignment,
                    current_detections=defect_items,
                    tolerance_px=settings.REFERENCE_MATCH_TOLERANCE_PX,
                )
                if position_missing:
                    logger.warning(
                        "[위치검증] 누락 부품 %d개 감지 — FAIL 처리",
                        len(position_missing),
                    )
                    missing_payloads.extend(position_missing)

        # ── PatchCore Anomaly Detection ───────────────────────────────────────
        # 정렬된 이미지에서 정상 패치 분포와의 거리 → 결함 영역 검출.
        # 학습은 외부 (Colab) — Pi 는 ONNX 추론만.
        anomaly_payloads: list[DefectPayload] = []
        if settings.PATCHCORE_ENABLED:
            global _patchcore_detector
            if _patchcore_detector is None:
                from inference.anomaly_patchcore import get_detector
                model_p = _resolve_edge_relative_path(settings.PATCHCORE_MODEL_PATH)
                cs_p = _resolve_edge_relative_path(settings.PATCHCORE_CORESET_PATH)
                meta_p = _resolve_edge_relative_path(settings.PATCHCORE_META_PATH)
                _patchcore_detector = get_detector(
                    model_p, cs_p, meta_p,
                    score_threshold=settings.PATCHCORE_SCORE_THRESHOLD,
                )

            if _patchcore_detector is not None:
                # Stage2 입력 이미지 그대로 사용 (정합된 frame)
                result = _patchcore_detector.infer(stage2_source_image)
                if result["is_anomaly"]:
                    # 위치 컨텍스트: 가장 가까운 검출 부품의 클래스를 라벨에 포함
                    # (PatchCore 만으론 종류 모름 → 어느 부품 부근인지로 운영자에게 힌트)
                    detected_centers = [
                        (d.defect_type.lower(), d.bbox.x + d.bbox.width / 2, d.bbox.y + d.bbox.height / 2)
                        for d in defect_items
                        if "fiducial" not in d.defect_type.lower()
                    ]

                    for x, y, w, h, score in result["boxes"]:
                        cx = x + w / 2.0
                        cy = y + h / 2.0
                        nearest_cls = None
                        nearest_dist = float("inf")
                        for cls, dcx, dcy in detected_centers:
                            d = math.hypot(cx - dcx, cy - dcy)
                            if d < nearest_dist:
                                nearest_dist = d
                                nearest_cls = cls
                        near_part = f"near={nearest_cls or 'unknown'},dist={nearest_dist:.0f}"
                        anomaly_payloads.append(DefectPayload(
                            defect_type=(
                                f"ANOMALY:{near_part},"
                                f"score={score:.2f},threshold={result['threshold']:.2f}"
                            ),
                            confidence=min(1.0, float(score) / max(1e-3, float(result["threshold"]))),
                            bbox_x=float(x),
                            bbox_y=float(y),
                            bbox_width=float(w),
                            bbox_height=float(h),
                        ))
                    logger.warning(
                        "[PatchCore] anomaly %d영역 감지 — FAIL 처리 (max score=%.2f)",
                        len(anomaly_payloads),
                        result["score"],
                    )

        f1c, f2c = _fiducial_confidences(alignment)
        if missing_payloads or anomaly_payloads:
            final_result = InspectionResult.FAIL
        all_defects = defect_payloads + missing_payloads + anomaly_payloads
        packet = _build_packet(
            result=final_result,
            f1x=f1x, f1y=f1y, f2x=f2x, f2y=f2y,
            f1_conf=f1c, f2_conf=f2c,
            angle_error=measured_skew_deg,
            inference_ms=fiducial_ms + defect_ms,
            defects=all_defects,
            image_path=image_path if stage2_mode == "raw" else aligned_path,
            pipeline_start=pipeline_start,
            device_id=selected_board_type,
        )

        if selected_board_type:
            logger.info("[멀티보드] 선택된 보드 타입: %s", selected_board_type)

        _finalize(packet)
        return packet

    except Exception as e:
        logger.error("[파이프라인] 예외 발생: %s", e, exc_info=True)
        return None


async def run_inspection_pipeline_from_source_file(
    relative_path: str,
    stage2_source_mode: Optional[str] = None,
) -> Optional[InspectionPacket]:
    """
    edge/captures 또는 edge/demo_samples 아래 저장된 이미지로 동일 파이프라인 실행.
    카메라 없이 시연·합성 데이터 검증에 사용한다.
    """
    from inference.model_compare import resolve_safe_inspection_source_image

    pipeline_start = time.perf_counter()
    has_models = detector is not None
    if not has_models:
        logger.error("[파이프라인] YOLO 모델이 로드되지 않아 파일 검사를 건너뜁니다.")
        return None

    src = resolve_safe_inspection_source_image(relative_path)

    frame = cv2.imread(str(src))
    if frame is None:
        raise RuntimeError(f"이미지 디코딩 실패: {src}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = CAPTURES_DIR / f"{ts}_fromfile{src.suffix.lower() if src.suffix else '.jpg'}"
    cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    image_path = str(dest.resolve())

    logger.info("[파이프라인] STEP 1 — 파일 로드 검사: %s → %s", src.name, dest.name)
    mode = (stage2_source_mode or settings.STAGE2_SOURCE_MODE).strip().lower()
    return _run_production_vision_pipeline(
        frame,
        image_path,
        pipeline_start,
        stage2_source_mode=mode,
        debug_imshow=False,
    )


def _build_packet(
    result: InspectionResult,
    f1x, f1y, f2x, f2y,
    angle_error: float,
    inference_ms: int,
    defects: list[DefectPayload],
    image_path: str,
    pipeline_start: float,
    f1_conf: Optional[float] = None,
    f2_conf: Optional[float] = None,
    device_id: Optional[str] = None,
) -> InspectionPacket:
    """InspectionPacket 조립 헬퍼."""
    total_ms = int((time.perf_counter() - pipeline_start) * 1000)
    return InspectionPacket(
        device_id=(device_id or "RPI5-LINE-A"),
        result=result,
        fiducial1_x=f1x, fiducial1_y=f1y,
        fiducial2_x=f2x, fiducial2_y=f2y,
        fiducial1_confidence=f1_conf,
        fiducial2_confidence=f2_conf,
        angle_error_deg=angle_error,
        inference_time_ms=inference_ms,
        total_time_ms=total_ms,
        image_path=image_path,
        inspected_at=datetime.now(),
        defects=defects,
    )


def run_inspection_pipeline_when_pcb_present() -> bool:
    """
    자동 검사 전용:
    라이브 프레임에서 PCB(피듀셜 2개)가 보일 때만 이미지를 저장하고 본검사를 실행한다.

    Returns:
        실제 검사까지 수행했으면 True, PCB 미검출로 건너뛰었으면 False.
    """
    if camera is None:
        logger.debug("[자동검사] 카메라가 없어 PCB 감지를 건너뜁니다.")
        return False

    has_models = (
        (fiducial_detector is not None and defect_detector is not None)
        if settings.USE_SEPARATE_MODELS
        else detector is not None
    )
    if not has_models:
        logger.warning("[자동검사] YOLO 모델이 로드되지 않아 PCB 감지를 건너뜁니다.")
        return False

    pipeline_start = time.perf_counter()
    frame = camera.capture()
    stage1 = fiducial_detector if settings.USE_SEPARATE_MODELS else detector
    fiducials, fiducial_ms = stage1.detect_fiducials(frame)

    if len(fiducials) < 2:
        logger.debug("[자동검사] PCB 미감지 — 피듀셜 %d개", len(fiducials))
        return False

    alignment = compute_alignment(fiducials)
    image_path = _save_frame(frame)

    logger.info("[자동검사] PCB 감지 — 본검사 시작")
    _run_production_vision_pipeline(
        frame,
        image_path,
        pipeline_start,
        debug_imshow=False,
        fiducials_precomputed=fiducials,
        fiducial_ms_precomputed=fiducial_ms,
        alignment_precomputed=alignment,
    )
    return True


def _finalize(packet: InspectionPacket) -> None:
    """GPIO 알람 출력 및 서버 전송을 수행하는 마무리 단계."""
    # Spring Boot 서버로 결과 전송
    if sender:
        sender.send(packet)

    logger.info(
        "[파이프라인] 완료 — 결과: %s, 결함: %d건, 총시간: %dms",
        packet.result.value,
        len(packet.defects),
        packet.total_time_ms or 0,
    )


# ── 루트 엔드포인트 ───────────────────────────────────────────────────────────

@app.get("/", tags=["Root"])
async def root():
    """API 루트 — 기본 안내 메시지."""
    return {
        "service": "PCB Edge Vision Inspection",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/edge/health",
        "dummy_test": "POST /edge/inspect/dummy",
    }


# ── 직접 실행 (python main.py) ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.EDGE_API_PORT,
        reload=(settings.ENVIRONMENT == "development"),
        log_level="debug" if settings.ENVIRONMENT == "development" else "info",
    )
