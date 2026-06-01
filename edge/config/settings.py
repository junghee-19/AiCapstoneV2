"""
엣지 디바이스 전역 설정 모듈

pydantic-settings를 사용하여 .env 파일 또는 OS 환경변수에서
설정값을 자동으로 로드하고 타입을 검증한다.

사용법:
    from config.settings import settings
    print(settings.SERVER_BASE_URL)
"""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# edge/config/ → edge/.env (CWD와 무관하게 항상 이 파일을 읽음)
_EDGE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    애플리케이션 전체에서 사용하는 설정값 클래스.
    .env 파일이 있으면 우선 적용하고, 없으면 아래 default 값을 사용한다.
    """

    # ── 중앙 서버 연결 정보 ──────────────────────────────────────────────────
    # Spring Boot 서버 주소 (같은 LAN 내 IP 또는 hostname)
    SERVER_BASE_URL: str = Field(default="http://192.168.0.10:8080")
    EDGE_DEVICE_ID: str = Field(default="RPI5-LINE-A")
    # Spring Boot 서버가 edge 제어용 WebSocket endpoint를 열어두면 여기에 연결한다.
    # EDGE_WS_URL이 비어 있으면 SERVER_BASE_URL + EDGE_WS_PATH에서 자동 생성한다.
    EDGE_WS_ENABLED: bool = Field(default=True)
    EDGE_WS_URL: Optional[str] = Field(default=None)
    EDGE_WS_PATH: str = Field(default="/ws/edge")
    EDGE_WS_RECONNECT_DELAY_SEC: float = Field(default=5.0, ge=0.5, le=120.0)
    EDGE_WS_PING_INTERVAL_SEC: float = Field(default=20.0, ge=1.0, le=120.0)
    EDGE_WS_PING_TIMEOUT_SEC: float = Field(default=20.0, ge=1.0, le=120.0)

    # ── 카메라 설정 ──────────────────────────────────────────────────────────
    # /dev/video0 → 0, C922가 video1·video2만 있으면 1 또는 2
    CAMERA_DEVICE_INDEX: int = Field(default=0)
    CAMERA_WIDTH: int = Field(default=1920)
    CAMERA_HEIGHT: int = Field(default=1080)
    # False: 예전 기본과 동일 — 오토포커스 끄고 focus_absolute만 사용(거리 고정 스테이션에 맞으면 유지)
    # True: 거리가 자주 바뀔 때 v4l2 오토포커스
    CAMERA_FOCUS_AUTO: bool = Field(default=False)
    # 수동 초점일 때만 사용 (0~255). 과거 하드코드 30과 동일 기본값
    CAMERA_FOCUS_ABSOLUTE: int = Field(default=30, ge=0, le=255)
    # USB 재연결·전원 리셋 후 펌웨어가 focus_absolute 한 번만으로는 안 먹는 경우가 있어 재적용
    CAMERA_FOCUS_MANUAL_DOUBLE_APPLY: bool = Field(default=True)
    CAMERA_FOCUS_MANUAL_REAPPLY_DELAY_SEC: float = Field(default=0.25, ge=0.0, le=2.0)
    # 수동 모드에서도 0보다 크면: 연속 AF를 이 시간(ms)만 돌린 뒤 AF 끄고 focus_absolute 적용 (재연결 후 흐림 완화)
    CAMERA_FOCUS_POST_PLUG_AF_MS: int = Field(default=0, ge=0, le=10000)
    # 수동 검사 시 PCB가 화면 중앙에 들어온 뒤 거의 안 움직이는 상태를 이 시간(초) 유지하면 캡처
    CAMERA_STABLE_HOLD_SEC: float = Field(default=5.0, ge=0.5, le=30.0)
    # 위 조건을 기다리는 최대 시간(초). 초과 시 최신 프레임으로 강제 진행
    CAMERA_STABLE_WAIT_TIMEOUT_SEC: float = Field(default=20.0, ge=1.0, le=120.0)
    # 피듀셜 중점이 화면 중심에서 이 비율 이내면 "중앙"으로 간주 (가로/세로 각각 적용)
    CAMERA_CENTER_TOLERANCE_RATIO: float = Field(default=0.12, ge=0.01, le=0.5)
    # 연속 프레임 간 피듀셜 중점 이동 허용치(px). 이하면 "거의 안 움직임"으로 간주
    CAMERA_STABLE_CENTER_DELTA_PX: float = Field(default=12.0, ge=1.0, le=200.0)
    # 연속 프레임 간 피듀셜 간격(span) 변화 허용치(px)
    CAMERA_STABLE_SPAN_DELTA_PX: float = Field(default=16.0, ge=1.0, le=300.0)
    # 연속 프레임 간 각도 변화 허용치(°)
    CAMERA_STABLE_ANGLE_DELTA_DEG: float = Field(default=1.5, ge=0.1, le=30.0)
    # 안정 상태 확인 중 프레임 샘플링 주기(초)
    CAMERA_STABLE_SAMPLE_INTERVAL_SEC: float = Field(default=0.2, ge=0.01, le=2.0)
    # 자동 촬영/검사 루프 활성화 여부
    AUTO_INSPECTION_ENABLED: bool = Field(default=True)
    # 자동 루프에서 PCB가 없을 때 카메라를 다시 확인하는 주기(초)
    AUTO_INSPECTION_IDLE_POLL_SEC: float = Field(default=0.5, ge=0.05, le=10.0)
    # 자동 촬영 진입 조건: 이 개수 이상의 피듀셜이 보이면 PCB가 촬영 영역에 들어온 것으로 본다.
    PCB_CAPTURE_MIN_FIDUCIALS: int = Field(default=2, ge=1, le=4)

    # ── YOLO 추론 설정 ───────────────────────────────────────────────────────
    # 단일 통합 모델 (best.pt) 사용
    YOLO_WEIGHTS_PATH: str = Field(default="weights/best.pt")
    USE_SEPARATE_MODELS: bool = Field(default=False)
    # USE_SEPARATE_MODELS=true 일 때 Stage 1/2 전용 모델 경로.
    # YOLO_FIDUCIAL_WEIGHTS는 기존 문서/.env 호환용 이름이다.
    YOLO_FIDUCIAL_WEIGHTS: Optional[str] = Field(default=None)
    YOLO_FIDUCIAL_WEIGHTS_PATH: str = Field(default="weights/fiducial_best.pt")
    YOLO_DEFECT_WEIGHTS: Optional[str] = Field(default=None)
    YOLO_DEFECT_WEIGHTS_PATH: Optional[str] = Field(default=None)

    # 이 값 이상의 confidence (Stage 전용 값이 없을 때 피듀셜·결함 공통 기본)
    YOLO_CONFIDENCE_THRESHOLD: float = Field(default=0.5, ge=0.0, le=1.0)

    # Stage별 덮어쓰기 — None이면 YOLO_CONFIDENCE_THRESHOLD 사용
    # 피듀셜은 낮게(0.25~0.4) 권장
    YOLO_FIDUCIAL_CONFIDENCE_THRESHOLD: Optional[float] = Field(default=None)
    # Stage 2(다클래스 PCB): 0.5면 약한 클래스 누락 다수 — 0.15~0.25 권장
    YOLO_DEFECT_CONFIDENCE_THRESHOLD: Optional[float] = Field(default=0.15)

    # predict() 입력 크기 — 학습 imgsz 와 맞출 것 (1024 학습 시 640 추론이면 탐지 수 급감)
    YOLO_PREDICT_IMGSZ: int = Field(default=1024, ge=320, le=1280)
    # True: TTA(증강 추론) — 약한 클래스 재현율 소폭↑, 추론 시간↑
    YOLO_PREDICT_AUGMENT: bool = Field(default=False)

    # True: Stage 2를 피듀셜 사이 좁은 ROI가 아니라 정합(또는 raw) **전체 프레임**에 수행.
    # PCB 다클래스(mount_hole, gold_finger_row 등)는 ROI 밖이 대부분이라 True 권장.
    DEFECT_INFER_ON_FULL_DESKEW: bool = Field(default=True)
    # Stage 2 입력 소스:
    # - "aligned": Stage1 좌표 정합 후 이미지 기준(권장)
    # - "deskew": 하위 호환 alias (내부적으로 aligned와 동일 처리)
    # - "raw": Stage1 보정 전 원본 이미지 기준
    STAGE2_SOURCE_MODE: str = Field(default="aligned")

    # ── 좌표 정합(Similarity: translation/rotation/scale) ────────────────────
    # 정합 기준 피듀셜 좌표 (정합 결과 이미지 좌표계)
    ALIGN_REF_FIDUCIAL1_X: int = Field(default=278, ge=0)
    ALIGN_REF_FIDUCIAL1_Y: int = Field(default=908, ge=0)
    ALIGN_REF_FIDUCIAL2_X: int = Field(default=1528, ge=0)
    ALIGN_REF_FIDUCIAL2_Y: int = Field(default=202, ge=0)
    # 정합 출력 캔버스 크기
    ALIGN_OUTPUT_WIDTH: int = Field(default=1920, ge=320, le=4096)
    ALIGN_OUTPUT_HEIGHT: int = Field(default=1080, ge=240, le=4096)
    # True(기본): YOLO가 1건이라도 잡으면 FAIL (단선/까짐 전용 모델).
    # False: 정렬 성공 시 PASS — 탐지 박스는 그대로 서버·대시보드에 보냄(부품 검출·표시용).
    FAIL_ON_ANY_YOLO_DETECTION: bool = Field(default=True)
    # 통합 모델에서 FAIL로 처리할 결함 클래스 목록. 정상 구성요소 클래스는 여기에 넣지 않는다.
    # 예: "trace_open,metal_damage,pinhole,short"
    DEFECT_CLASS_NAMES: str = Field(default="trace_open,metal_damage,pinhole,short")

    # ── 멀티보드 라우팅 설정 ──────────────────────────────────────────────────
    MULTI_BOARD_ENABLED: bool = Field(default=False)
    # 보드 식별용 모델 (board-name-zone 클래스 탐지 전용, 기본은 현재 best.pt)
    BOARD_ID_WEIGHTS_PATH: str = Field(default="weights/best.pt")
    # 보드 프로파일(JSON) 파일 경로. edge/ 기준 상대 경로 허용.
    BOARD_PROFILES_PATH: str = Field(default="config/board_profiles.json")
    BOARD_ID_MIN_CONFIDENCE: float = Field(default=0.4, ge=0.0, le=1.0)
    # unknown 처리 정책: abort | fallback_default
    BOARD_UNKNOWN_POLICY: str = Field(default="abort")
    # fallback_default 정책에서 사용할 기본 보드 타입 키
    DEFAULT_BOARD_TYPE: Optional[str] = Field(default=None)

    # ── 정상 샘플 위치 검증 (Position Check) ─────────────────────────────────
    # 활성화 + 레퍼런스 등록되어 있으면 Stage2 후 위치 매칭 → 누락 시 FAIL
    REFERENCE_CHECK_ENABLED: bool = Field(default=False)
    # 정상 샘플 프로파일 JSON 파일 (edge/ 기준 상대 경로 허용)
    REFERENCE_PROFILE_PATH: str = Field(default="config/reference_profile.json")
    # 변환된 예상 위치 ± 이 거리 안에 같은 클래스 검출이 있어야 OK (px)
    REFERENCE_MATCH_TOLERANCE_PX: float = Field(default=80.0, gt=0.0)

    # ── Metal Damage (까짐) YOLO 검출 ────────────────────────────────────────
    # Copy-Paste 증강 학습한 별도 모델. 활성화 시 Stage2 후 추론 → 검출 시 FAIL
    DEFECT_MODEL_ENABLED: bool = Field(default=False)
    DEFECT_MODEL_PATH: str = Field(default="weights/best_defect.pt")
    DEFECT_MODEL_CONFIDENCE: float = Field(default=0.5, ge=0.0, le=1.0)

    # ── PatchCore Anomaly Detection ──────────────────────────────────────────
    # 활성화 + 모델/coreset 파일 존재 시 Stage2 후 추론 → 임계값 초과 시 FAIL
    PATCHCORE_ENABLED: bool = Field(default=False)
    # TorchScript 백본 모델 (.pt) — Colab 학습 후 export
    PATCHCORE_MODEL_PATH: str = Field(default="weights/patchcore_backbone.pt")
    PATCHCORE_CORESET_PATH: str = Field(default="weights/patchcore_coreset.npy")
    PATCHCORE_META_PATH: str = Field(default="weights/patchcore_meta.json")
    # None 이면 meta.json 의 threshold_mean_plus_3sigma 사용. 수동 오버라이드 시 양수 값.
    PATCHCORE_SCORE_THRESHOLD: Optional[float] = Field(default=None)

    # ── FastAPI 서버 포트 ────────────────────────────────────────────────────
    EDGE_API_PORT: int = Field(default=8000)

    # ── 실행 환경 ────────────────────────────────────────────────────────────
    # "production": 실제 라즈베리파이에서 GPIO/YOLO 실제 동작
    # "development": 개발 PC에서 더미 데이터로 동작
    ENVIRONMENT: str = Field(default="development")

    # ── 정렬 / 각도 보정 ───────────────────────────────────────────────────────
    # 피듀셜 2개로 측정한 기울기가 이 각도(°)를 넘으면 FAIL (오탐·이상 배치로 간주, 보정 안 함)
    MAX_DESKEW_ANGLE_DEG: float = Field(default=45.0)
    # 이보다 작으면 회전 보정 생략 (미세 보간 노이즈 감소)
    MIN_DESKEW_ANGLE_DEG: float = Field(default=0.05)
    # 하위 호환·문서용: 과거 "허용 오차 초과 시 FAIL" 모드에서 사용. 파이프라인은 MAX_DESKEW_* 기준.
    MAX_ANGLE_ERROR_DEG: float = Field(default=3.0)

    @field_validator("YOLO_FIDUCIAL_CONFIDENCE_THRESHOLD", "YOLO_DEFECT_CONFIDENCE_THRESHOLD", mode="before")
    @classmethod
    def _empty_conf_to_none(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    @field_validator("YOLO_FIDUCIAL_CONFIDENCE_THRESHOLD", "YOLO_DEFECT_CONFIDENCE_THRESHOLD")
    @classmethod
    def _stage_conf_range(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if not 0.0 <= float(v) <= 1.0:
            raise ValueError("Stage confidence must be between 0.0 and 1.0")
        return float(v)

    def effective_fiducial_confidence(self) -> float:
        if self.YOLO_FIDUCIAL_CONFIDENCE_THRESHOLD is not None:
            return float(self.YOLO_FIDUCIAL_CONFIDENCE_THRESHOLD)
        return float(self.YOLO_CONFIDENCE_THRESHOLD)

    def effective_defect_confidence(self) -> float:
        if self.YOLO_DEFECT_CONFIDENCE_THRESHOLD is not None:
            return float(self.YOLO_DEFECT_CONFIDENCE_THRESHOLD)
        return float(self.YOLO_CONFIDENCE_THRESHOLD)

    def effective_fiducial_weights_path(self) -> str:
        if self.YOLO_FIDUCIAL_WEIGHTS:
            return self.YOLO_FIDUCIAL_WEIGHTS
        return self.YOLO_FIDUCIAL_WEIGHTS_PATH

    def effective_defect_weights_path(self) -> str:
        if self.YOLO_DEFECT_WEIGHTS:
            return self.YOLO_DEFECT_WEIGHTS
        if self.YOLO_DEFECT_WEIGHTS_PATH:
            return self.YOLO_DEFECT_WEIGHTS_PATH
        return self.YOLO_WEIGHTS_PATH

    def defect_class_set(self) -> set[str]:
        return {
            name.strip().lower()
            for name in self.DEFECT_CLASS_NAMES.split(",")
            if name.strip()
        }

    @field_validator("STAGE2_SOURCE_MODE")
    @classmethod
    def _validate_stage2_source_mode(cls, v: str) -> str:
        mode = (v or "").strip().lower()
        if mode not in {"raw", "deskew", "aligned"}:
            raise ValueError("STAGE2_SOURCE_MODE must be 'raw', 'deskew', or 'aligned'")
        if mode == "deskew":
            return "aligned"
        return mode

    @field_validator("BOARD_UNKNOWN_POLICY")
    @classmethod
    def _validate_board_unknown_policy(cls, v: str) -> str:
        policy = (v or "").strip().lower()
        if policy not in {"abort", "fallback_default"}:
            raise ValueError("BOARD_UNKNOWN_POLICY must be 'abort' or 'fallback_default'")
        return policy

    # pydantic-settings 설정:
    # .env 파일을 자동으로 찾아 읽고, 대소문자를 구분하지 않는다.
    # extra='ignore': .env에 아직 모델에 없는 키가 있어도 기동 실패하지 않음(구버전 코드·부분 배포)
    model_config = SettingsConfigDict(
        env_file=str(_EDGE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# 싱글턴 인스턴스: 모든 모듈에서 이 객체를 import해서 사용
settings = Settings()
