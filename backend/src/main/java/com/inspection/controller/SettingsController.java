package com.inspection.controller;

import com.inspection.config.CleanupScheduler;
import com.inspection.dto.AppSettingsDto;
import com.inspection.service.AppSettingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 시스템 설정 REST API.
 * <pre>
 *   GET  /api/settings         — 현재 설정 조회
 *   PUT  /api/settings         — 설정 갱신 (저장 + 스케줄러 즉시 재등록)
 * </pre>
 */
@RestController
@RequestMapping("/api/settings")
@RequiredArgsConstructor
public class SettingsController {

    private final AppSettingService settingService;
    private final CleanupScheduler cleanupScheduler;

    @GetMapping
    public ResponseEntity<AppSettingsDto> getSettings() {
        return ResponseEntity.ok(AppSettingsDto.builder()
                .retentionDays(settingService.getRetentionDays())
                .cleanupCron(settingService.getCleanupCron())
                .build());
    }

    @PutMapping
    public ResponseEntity<AppSettingsDto> updateSettings(@Valid @RequestBody AppSettingsDto req) {
        settingService.update(req.getRetentionDays(), req.getCleanupCron());
        // 변경된 cron 으로 즉시 재스케줄
        cleanupScheduler.reschedule();
        return ResponseEntity.ok(AppSettingsDto.builder()
                .retentionDays(settingService.getRetentionDays())
                .cleanupCron(settingService.getCleanupCron())
                .build());
    }
}
