package com.inspection.controller;

import com.inspection.dto.DatasetImageDto;
import com.inspection.service.DatasetImageStorageService;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.util.List;

@RestController
@RequestMapping("/api/dataset-images")
@RequiredArgsConstructor
public class DatasetImageController {

    private final DatasetImageStorageService datasetImageStorageService;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DatasetImageDto> uploadDatasetImage(
            @RequestPart("image") MultipartFile image,
            @RequestParam String deviceId,
            @RequestParam String session,
            @RequestParam Integer index
    ) {
        DatasetImageDto saved = datasetImageStorageService.store(image, deviceId, session, index);
        return ResponseEntity.status(201).body(saved);
    }

    @GetMapping
    public ResponseEntity<List<DatasetImageDto>> listDatasetImages() {
        return ResponseEntity.ok(datasetImageStorageService.list());
    }

    @GetMapping("/{deviceId}/{session}/{filename}")
    public ResponseEntity<Resource> downloadDatasetImage(
            @PathVariable String deviceId,
            @PathVariable String session,
            @PathVariable String filename
    ) {
        Resource resource = datasetImageStorageService.load(deviceId, session, filename);

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
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"" + resource.getFilename() + "\"")
                .body(resource);
    }

    @DeleteMapping("/{deviceId}/{session}/{filename}")
    public ResponseEntity<Void> deleteDatasetImage(
            @PathVariable String deviceId,
            @PathVariable String session,
            @PathVariable String filename
    ) {
        datasetImageStorageService.delete(deviceId, session, filename);
        return ResponseEntity.noContent().build();
    }
}
