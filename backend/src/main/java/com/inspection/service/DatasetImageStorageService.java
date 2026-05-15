package com.inspection.service;

import com.inspection.dto.DatasetImageDto;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriUtils;

import java.io.IOException;
import java.net.MalformedURLException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

@Service
@Slf4j
public class DatasetImageStorageService {

    private static final DateTimeFormatter TS_FMT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    private final Path storageDir;

    public DatasetImageStorageService(
            @Value("${inspection.dataset-image-storage-dir}") String storageDirPath) {
        this.storageDir = Paths.get(storageDirPath).toAbsolutePath().normalize();
    }

    @PostConstruct
    public void init() {
        try {
            Files.createDirectories(storageDir);
            log.info("[데이터셋이미지] 저장 디렉토리 준비 완료: {}", storageDir);
        } catch (IOException e) {
            throw new IllegalStateException("데이터셋 이미지 저장 디렉토리 생성 실패: " + storageDir, e);
        }
    }

    public DatasetImageDto store(
            MultipartFile file,
            String deviceId,
            String session,
            Integer index
    ) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("저장할 데이터셋 이미지가 비어 있습니다.");
        }

        String safeDeviceId = sanitizeSegment(deviceId, "unknown-device");
        String safeSession = sanitizeSegment(session, "manual");
        String ext = extractExtension(file.getOriginalFilename());
        String filename = String.format(Locale.ROOT, "%03d%s", index == null ? 1 : index, ext);

        Path targetDir = storageDir.resolve(safeDeviceId).resolve(safeSession).normalize();
        Path target = targetDir.resolve(filename).normalize();
        ensureInsideStorage(target);

        try {
            Files.createDirectories(targetDir);
            Files.copy(file.getInputStream(), target, StandardCopyOption.REPLACE_EXISTING);
            log.info("[데이터셋이미지] 저장: {}", target);
            return toDto(safeDeviceId, safeSession, target);
        } catch (IOException e) {
            throw new RuntimeException("데이터셋 이미지 저장 실패: " + target, e);
        }
    }

    public List<DatasetImageDto> list() {
        if (!Files.exists(storageDir)) {
            return List.of();
        }

        try (Stream<Path> paths = Files.walk(storageDir, 3)) {
            return paths
                    .filter(Files::isRegularFile)
                    .filter(this::isSupportedImage)
                    .sorted(Comparator.reverseOrder())
                    .map(this::toDtoFromPath)
                    .toList();
        } catch (IOException e) {
            throw new RuntimeException("데이터셋 이미지 목록 조회 실패", e);
        }
    }

    public Resource load(String deviceId, String session, String filename) {
        String safeDeviceId = sanitizeSegment(deviceId, "unknown-device");
        String safeSession = sanitizeSegment(session, "manual");
        String safeFilename = sanitizeFilename(filename);
        Path target = storageDir.resolve(safeDeviceId).resolve(safeSession).resolve(safeFilename).normalize();
        ensureInsideStorage(target);
        if (!Files.exists(target) || !Files.isRegularFile(target)) {
            throw new IllegalArgumentException("데이터셋 이미지 없음: " + filename);
        }
        try {
            return new UrlResource(target.toUri());
        } catch (MalformedURLException e) {
            throw new RuntimeException("데이터셋 이미지 URL 변환 실패: " + filename, e);
        }
    }

    public void delete(String deviceId, String session, String filename) {
        String safeDeviceId = sanitizeSegment(deviceId, "unknown-device");
        String safeSession = sanitizeSegment(session, "manual");
        String safeFilename = sanitizeFilename(filename);
        Path target = storageDir.resolve(safeDeviceId).resolve(safeSession).resolve(safeFilename).normalize();
        ensureInsideStorage(target);
        try {
            Files.deleteIfExists(target);
            cleanupEmptyParents(target.getParent());
            log.info("[데이터셋이미지] 삭제: {}", target);
        } catch (IOException e) {
            throw new RuntimeException("데이터셋 이미지 삭제 실패: " + target, e);
        }
    }

    private DatasetImageDto toDtoFromPath(Path path) {
        Path relative = storageDir.relativize(path);
        String deviceId = relative.getNameCount() >= 1 ? relative.getName(0).toString() : "unknown-device";
        String session = relative.getNameCount() >= 2 ? relative.getName(1).toString() : "manual";
        return toDto(deviceId, session, path);
    }

    private DatasetImageDto toDto(String deviceId, String session, Path path) {
        try {
            BasicFileAttributes attrs = Files.readAttributes(path, BasicFileAttributes.class);
            String filename = path.getFileName().toString();
            return DatasetImageDto.builder()
                    .deviceId(deviceId)
                    .session(session)
                    .filename(filename)
                    .sizeBytes(attrs.size())
                    .createdAt(TS_FMT.format(attrs.creationTime().toInstant().atZone(ZoneId.systemDefault())))
                    .downloadUrl(downloadUrl(deviceId, session, filename))
                    .build();
        } catch (IOException e) {
            throw new RuntimeException("데이터셋 이미지 메타데이터 조회 실패: " + path, e);
        }
    }

    private String downloadUrl(String deviceId, String session, String filename) {
        return "/api/dataset-images/" +
                UriUtils.encodePathSegment(deviceId, StandardCharsets.UTF_8) + "/" +
                UriUtils.encodePathSegment(session, StandardCharsets.UTF_8) + "/" +
                UriUtils.encodePathSegment(filename, StandardCharsets.UTF_8);
    }

    private void ensureInsideStorage(Path path) {
        if (!path.startsWith(storageDir)) {
            throw new IllegalArgumentException("허용되지 않은 데이터셋 이미지 경로: " + path);
        }
    }

    private void cleanupEmptyParents(Path dir) throws IOException {
        Path current = dir;
        while (current != null && !current.equals(storageDir) && current.startsWith(storageDir)) {
            try (Stream<Path> children = Files.list(current)) {
                if (children.findAny().isPresent()) {
                    return;
                }
            }
            Files.deleteIfExists(current);
            current = current.getParent();
        }
    }

    private boolean isSupportedImage(Path path) {
        String name = path.getFileName().toString().toLowerCase(Locale.ROOT);
        return name.endsWith(".jpg") || name.endsWith(".jpeg") || name.endsWith(".png") || name.endsWith(".webp");
    }

    private static String sanitizeSegment(String value, String fallback) {
        String v = value == null || value.isBlank() ? fallback : value.trim();
        return v.replaceAll("[^A-Za-z0-9._-]", "_");
    }

    private static String sanitizeFilename(String value) {
        String v = value == null || value.isBlank() ? "image.jpg" : value.trim();
        return Paths.get(v).getFileName().toString().replaceAll("[^A-Za-z0-9._-]", "_");
    }

    private static String extractExtension(String original) {
        if (original == null) return ".jpg";
        int dot = original.lastIndexOf('.');
        if (dot < 0 || dot == original.length() - 1) return ".jpg";
        String ext = original.substring(dot).toLowerCase(Locale.ROOT);
        return ext.matches("\\.(jpg|jpeg|png|webp)") ? ext : ".jpg";
    }
}
