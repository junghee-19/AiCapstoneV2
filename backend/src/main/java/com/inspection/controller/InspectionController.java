package com.inspection.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.inspection.dto.InspectionRequestDto;
import com.inspection.dto.InspectionResponseDto;
import com.inspection.service.ImageStorageService;
import com.inspection.service.InspectionService;
import jakarta.validation.Validator;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.constraints.Min;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.Resource;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.io.IOException;
import java.nio.file.Files;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 검사 이력 REST API 컨트롤러
 *
 * <p>Base URL: /api/inspections
 *
 * <p>엔드포인트 목록:
 * - POST   /api/inspections          → 엣지 디바이스 검사 결과 수신
 * - GET    /api/inspections          → 전체 이력 조회 (프론트엔드)
 * - GET    /api/inspections/{id}     → 단건 상세 조회
 * - GET    /api/inspections/recent   → 최근 N건 조회
 * - GET    /api/inspections/stats    → 통계 요약
 * - GET    /api/inspections/period   → 기간 필터 조회
 * - DELETE /api/inspections          → 전체 이력 삭제 (검사 이력 페이지)
 * - DELETE /api/inspections/period   → 기간 단위 이력 삭제 (검사 이력 페이지)
 *
 * CORS는 {@link com.inspection.global.CorsConfig} 에서 전역 설정.
 *   - 환경변수 CORS_ALLOWED_ORIGINS 로 허용 origin 목록 주입
 */
@RestController
@RequestMapping("/api/inspections")
@Slf4j
@RequiredArgsConstructor
public class InspectionController {

    private final InspectionService inspectionService;
    private final ImageStorageService imageStorageService;
    private final ObjectMapper objectMapper;
    private final Validator validator;

    // ========================================================================
    // 1. 검사 결과 수신 (라즈베리파이 → 서버)
    // ========================================================================

    /**
     * [엣지 디바이스 전용] 검사 결과 multipart 수신 및 DB 저장
     *
     * <p>POST /api/inspections
     * <p>Content-Type: multipart/form-data
     *
     * <p>두 파트:
     *   - {@code metadata} : InspectionRequestDto 직렬화 JSON 텍스트
     *   - {@code image}    : 캡처 이미지 바이너리 (선택 — SKIPPED 등에는 생략)
     *
     * <p>이미지는 디스크에 저장되고 DB 의 image_path 에는 파일명만 들어간다.
     *
     * @return 201 Created + 저장된 검사 이력 DTO
     */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<InspectionResponseDto> receiveInspectionResult(
            @RequestPart("metadata") String metadataJson,
            @RequestPart(value = "image", required = false) MultipartFile image) {

        InspectionRequestDto requestDto = parseMetadata(metadataJson);
        validateMetadata(requestDto);

        log.info("[POST /api/inspections] 수신 - 디바이스: {}, 결과: {}, 이미지: {}",
                requestDto.getDeviceId(),
                requestDto.getResult(),
                (image != null && !image.isEmpty()) ? image.getOriginalFilename() : "없음");

        InspectionResponseDto response = inspectionService.saveInspectionResult(requestDto, image);
        return ResponseEntity.status(201).body(response);
    }

    private InspectionRequestDto parseMetadata(String json) {
        try {
            return objectMapper.readValue(json, InspectionRequestDto.class);
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "metadata 파싱 실패: " + e.getMessage(), e);
        }
    }

    private void validateMetadata(InspectionRequestDto dto) {
        Set<ConstraintViolation<InspectionRequestDto>> violations = validator.validate(dto);
        if (!violations.isEmpty()) {
            String msg = violations.stream()
                    .map(v -> v.getPropertyPath() + " " + v.getMessage())
                    .collect(Collectors.joining(", "));
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "metadata 검증 실패: " + msg);
        }
    }

    /**
     * 검사 캡처 이미지 단건 조회.
     *
     * <p>GET /api/inspections/{id}/image
     *
     * <p>DB 의 image_path 컬럼에 저장된 파일명을 ImageStorageService 로 로드해 그대로 스트리밍.
     */
    @GetMapping("/{id}/image")
    public ResponseEntity<Resource> getInspectionImage(@PathVariable Long id) {
        InspectionResponseDto found = inspectionService.getInspectionById(id);
        String filename = found.getImagePath();
        if (filename == null || filename.isBlank()) {
            return ResponseEntity.notFound().build();
        }
        Resource resource = imageStorageService.load(filename);

        MediaType contentType = MediaType.IMAGE_JPEG;
        try {
            String probed = Files.probeContentType(resource.getFile().toPath());
            if (probed != null) {
                contentType = MediaType.parseMediaType(probed);
            }
        } catch (IOException ignored) {
            // 기본 JPEG 로 fallback
        }

        return ResponseEntity.ok()
                .contentType(contentType)
                .header(HttpHeaders.CACHE_CONTROL, "public, max-age=86400")
                .body(resource);
    }

    // ========================================================================
    // 2. 이력 조회 (프론트엔드 → 서버)
    // ========================================================================

    /**
     * 전체 검사 이력 목록 조회
     *
     * <p>GET /api/inspections
     *
     * @return 200 OK + 검사 이력 목록
     */
    @GetMapping
    public ResponseEntity<List<InspectionResponseDto>> getAllInspections() {
        log.debug("[GET /api/inspections] 전체 이력 조회");
        return ResponseEntity.ok(inspectionService.getAllInspections());
    }

    /**
     * 단건 검사 이력 상세 조회
     *
     * <p>GET /api/inspections/{id}
     *
     * @param id 검사 로그 ID (PathVariable)
     * @return 200 OK + 검사 상세 DTO / 404 Not Found
     */
    @GetMapping("/{id}")
    public ResponseEntity<InspectionResponseDto> getInspectionById(
            @PathVariable Long id) {
        log.debug("[GET /api/inspections/{}] 단건 조회", id);
        return ResponseEntity.ok(inspectionService.getInspectionById(id));
    }

    /**
     * 최근 N건 검사 이력 조회 (대시보드 실시간 피드)
     *
     * <p>GET /api/inspections/recent?limit=10
     *
     * @param limit 조회 건수 (기본값: 10, 최솟값: 1)
     * @return 200 OK + 최근 N건 이력 목록
     */
    @GetMapping("/recent")
    public ResponseEntity<List<InspectionResponseDto>> getRecentInspections(
            @RequestParam(defaultValue = "10") @Min(1) int limit) {
        log.debug("[GET /api/inspections/recent] 최근 {}건 조회", limit);
        return ResponseEntity.ok(inspectionService.getRecentInspections(limit));
    }

    /**
     * 전체 통계 요약 조회 (대시보드 StatCard)
     *
     * <p>GET /api/inspections/stats
     *
     * <p>응답 예시:
     * {
     *   "totalCount": 350,
     *   "passCount": 320,
     *   "failCount": 30,
     *   "skippedCount": 8,
     *   "inspectedCount": 350,
     *   "failRate": 8.57
     * }
     *
     * @return 200 OK + 통계 집계 Map
     */
    @GetMapping("/stats")
    public ResponseEntity<Map<String, Object>> getStatsSummary() {
        log.debug("[GET /api/inspections/stats] 통계 조회");
        return ResponseEntity.ok(inspectionService.getStatsSummary());
    }

    /**
     * 기간 단위 오류율 추이 조회
     *
     * <p>GET /api/inspections/stats/fail-rate-trend?groupBy=month&periods=6
     *
     * @param groupBy week 또는 month
     * @param periods 최근 구간 수
     * @return 200 OK + 기간별 오류율 추이
     */
    @GetMapping("/stats/fail-rate-trend")
    public ResponseEntity<List<Map<String, Object>>> getFailRateTrend(
            @RequestParam(defaultValue = "month") String groupBy,
            @RequestParam(defaultValue = "6") @Min(1) int periods) {
        log.debug("[GET /api/inspections/stats/fail-rate-trend] groupBy={}, periods={}", groupBy, periods);
        return ResponseEntity.ok(inspectionService.getFailRateTrend(groupBy, periods));
    }

    /**
     * 기간 필터 검사 이력 조회
     *
     * <p>GET /api/inspections/period?from=2026-03-01T00:00:00&to=2026-03-31T23:59:59
     *
     * @param from 시작 시각 (ISO 형식)
     * @param to   종료 시각 (ISO 형식)
     * @return 200 OK + 해당 기간 검사 이력 목록
     */
    @GetMapping("/period")
    public ResponseEntity<List<InspectionResponseDto>> getInspectionsByPeriod(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {
        log.debug("[GET /api/inspections/period] {} ~ {}", from, to);
        return ResponseEntity.ok(inspectionService.getInspectionsByPeriod(from, to));
    }

    /**
     * 전체 검사 이력 및 결함 상세 삭제 (검사 이력 페이지 초기화).
     *
     * <p>DELETE /api/inspections
     */
    @DeleteMapping
    public ResponseEntity<Void> deleteAllInspections() {
        log.warn("[DELETE /api/inspections] 전체 이력 삭제 요청");
        inspectionService.deleteAllInspections();
        return ResponseEntity.noContent().build();
    }

    /**
     * 기간 단위 검사 이력 및 결함 상세 삭제.
     *
     * <p>DELETE /api/inspections/period?from=2026-03-01T00:00:00&to=2026-03-31T23:59:59
     *
     * @param from 시작 시각 (포함)
     * @param to   종료 시각 (포함)
     * @return 200 OK + 삭제 건수 Map
     */
    @DeleteMapping("/period")
    public ResponseEntity<Map<String, Object>> deleteInspectionsByPeriod(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {
        log.warn("[DELETE /api/inspections/period] {} ~ {} 기간 삭제 요청", from, to);
        int removed = inspectionService.deleteInspectionsByPeriod(from, to);
        return ResponseEntity.ok(Map.of("deletedCount", removed));
    }
}
