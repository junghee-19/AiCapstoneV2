package com.inspection.domain.entity;

import jakarta.persistence.*;
import lombok.*;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

/**
 * 운영자가 UI 에서 변경할 수 있는 키-값 시스템 설정.
 *
 * 예:
 *   key="retention_days",   value="60"
 *   key="cleanup_cron",     value="0 0 3 * * *"
 *
 * 단일 행(set) 단위로 저장하며, AppSettingService 가 키별 기본값을 제공한다.
 */
@Entity
@Table(name = "app_setting", uniqueConstraints = @UniqueConstraint(columnNames = "config_key"))
@EntityListeners(AuditingEntityListener.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class AppSetting {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "config_key", length = 64, nullable = false)
    private String key;

    @Column(name = "config_value", length = 255, nullable = false)
    private String value;

    @LastModifiedDate
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public void updateValue(String value) {
        this.value = value;
    }
}
