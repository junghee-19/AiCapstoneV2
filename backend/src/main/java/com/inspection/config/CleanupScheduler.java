package com.inspection.config;

import com.inspection.service.AppSettingService;
import com.inspection.service.InspectionService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.stereotype.Component;

import java.util.concurrent.ScheduledFuture;

/**
 * 보관기간 만료 자동 정리 작업을 동적으로 스케줄링한다.
 *
 * AppSettingService 에 저장된 cron 표현식을 읽어 등록하고,
 * 설정 변경 시 {@link #reschedule()} 호출로 즉시 반영한다.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class CleanupScheduler {

    private final AppSettingService settings;
    private final InspectionService inspectionService;

    /** 정리 작업 전용 스케줄러 — 1 스레드면 충분. Spring 빈으로 노출 안 함 (순환 방지). */
    private ThreadPoolTaskScheduler scheduler;
    private ScheduledFuture<?> currentTask;

    @PostConstruct
    public void start() {
        ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
        s.setPoolSize(1);
        s.setThreadNamePrefix("cleanup-");
        s.initialize();
        this.scheduler = s;
        schedule(settings.getCleanupCron());
    }

    @PreDestroy
    public void stop() {
        if (currentTask != null) currentTask.cancel(false);
        if (scheduler != null) scheduler.shutdown();
    }

    /**
     * 설정 변경 후 외부에서 호출 — 기존 작업 취소 + 새 cron 으로 재등록.
     */
    public synchronized void reschedule() {
        String newCron = settings.getCleanupCron();
        if (currentTask != null) {
            currentTask.cancel(false);
            currentTask = null;
        }
        schedule(newCron);
    }

    private void schedule(String cron) {
        currentTask = scheduler.schedule(
                this::runCleanup,
                new CronTrigger(cron)
        );
        log.info("[정리 스케줄러] 등록 완료 — cron='{}'", cron);
    }

    private void runCleanup() {
        try {
            int retentionDays = settings.getRetentionDays();
            inspectionService.purgeExpiredInspections(retentionDays);
        } catch (Exception e) {
            log.error("[정리 스케줄러] 실행 중 오류", e);
        }
    }
}
