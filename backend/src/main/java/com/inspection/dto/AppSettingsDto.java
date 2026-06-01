package com.inspection.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 시스템 설정 DTO — GET 응답 / PUT 요청 공용.
 *
 * - retentionDays: 검사 이력 보관 기간 (일)
 * - cleanupCron:   자동 정리 실행 cron (Spring 6필드)
 *
 * 프론트엔드 편의를 위해 cleanupTime("HH:mm") 도 함께 노출하지만,
 * DB 저장은 cleanupCron 만 사용한다.
 */
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AppSettingsDto {

    @NotNull
    @Min(1)
    @Max(365)
    private Integer retentionDays;

    @NotBlank
    private String cleanupCron;
}
