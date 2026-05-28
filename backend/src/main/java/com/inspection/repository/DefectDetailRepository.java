package com.inspection.repository;

import com.inspection.domain.entity.DefectDetail;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;

/**
 * 결함 상세 JPA 리포지토리.
 * <p>전체/기간/만료 검사 이력 삭제 시 자식 행을 먼저 배치 삭제하는 데 사용한다.
 */
public interface DefectDetailRepository extends JpaRepository<DefectDetail, Long> {

    /** 지정 기간 검사 이력에 속한 결함 상세를 일괄 삭제. */
    @Modifying(clearAutomatically = true)
    @Query("DELETE FROM DefectDetail d "
         + "WHERE d.inspectionLog.id IN ("
         + "  SELECT l.id FROM InspectionLog l "
         + "  WHERE l.inspectedAt BETWEEN :from AND :to)")
    int deleteByInspectionLogInspectedAtBetween(@Param("from") LocalDateTime from,
                                                @Param("to") LocalDateTime to);

    /** 지정 시각 이전 검사 이력에 속한 결함 상세를 일괄 삭제 (보관기간 만료). */
    @Modifying(clearAutomatically = true)
    @Query("DELETE FROM DefectDetail d "
         + "WHERE d.inspectionLog.id IN ("
         + "  SELECT l.id FROM InspectionLog l "
         + "  WHERE l.inspectedAt < :threshold)")
    int deleteByInspectionLogInspectedAtBefore(@Param("threshold") LocalDateTime threshold);
}
