package com.inspection.service;

import com.inspection.domain.entity.AppSetting;
import com.inspection.repository.AppSettingRepository;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.support.CronExpression;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 시스템 설정(보관기간, 정리 시각 등) CRUD 서비스.
 *
 * 키별 기본값을 코드에 두고, 최초 기동 시 DB에 없으면 시드한다.
 * 변경 시 SettingsScheduler 가 listener 로 감지하여 cron 을 재등록한다.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AppSettingService {

    /** 검사 이력 보관 기간 (일). */
    public static final String KEY_RETENTION_DAYS = "retention_days";
    public static final int DEFAULT_RETENTION_DAYS = 60;

    /** 자동 정리 cron 표현식 (Spring 6필드: 초 분 시 일 월 요일). */
    public static final String KEY_CLEANUP_CRON = "cleanup_cron";
    public static final String DEFAULT_CLEANUP_CRON = "0 0 3 * * *";

    public static final int RETENTION_MIN = 1;
    public static final int RETENTION_MAX = 365;

    private final AppSettingRepository repository;

    @PostConstruct
    @Transactional
    public void seedDefaults() {
        ensureSetting(KEY_RETENTION_DAYS, String.valueOf(DEFAULT_RETENTION_DAYS));
        ensureSetting(KEY_CLEANUP_CRON, DEFAULT_CLEANUP_CRON);
    }

    private void ensureSetting(String key, String defaultValue) {
        repository.findByKey(key).orElseGet(() ->
                repository.save(AppSetting.builder().key(key).value(defaultValue).build())
        );
    }

    @Transactional(readOnly = true)
    public int getRetentionDays() {
        return repository.findByKey(KEY_RETENTION_DAYS)
                .map(s -> safeParseInt(s.getValue(), DEFAULT_RETENTION_DAYS))
                .orElse(DEFAULT_RETENTION_DAYS);
    }

    @Transactional(readOnly = true)
    public String getCleanupCron() {
        return repository.findByKey(KEY_CLEANUP_CRON)
                .map(AppSetting::getValue)
                .orElse(DEFAULT_CLEANUP_CRON);
    }

    /**
     * 보관기간(일)과 정리 cron 을 함께 갱신.
     * 검증 통과 후에만 저장하며, 둘 다 통과해야 둘 다 반영(원자성).
     */
    @Transactional
    public void update(int retentionDays, String cleanupCron) {
        if (retentionDays < RETENTION_MIN || retentionDays > RETENTION_MAX) {
            throw new IllegalArgumentException(
                    "retentionDays 는 " + RETENTION_MIN + "~" + RETENTION_MAX + " 사이여야 합니다.");
        }
        if (!CronExpression.isValidExpression(cleanupCron)) {
            throw new IllegalArgumentException("cleanupCron 표현식이 유효하지 않습니다: " + cleanupCron);
        }
        upsert(KEY_RETENTION_DAYS, String.valueOf(retentionDays));
        upsert(KEY_CLEANUP_CRON, cleanupCron);
        log.info("[설정] 갱신 — retentionDays={}, cleanupCron={}", retentionDays, cleanupCron);
    }

    private void upsert(String key, String value) {
        AppSetting setting = repository.findByKey(key)
                .orElseGet(() -> AppSetting.builder().key(key).value(value).build());
        setting.updateValue(value);
        repository.save(setting);
    }

    private static int safeParseInt(String s, int fallback) {
        try {
            return Integer.parseInt(s);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
