package com.inspection.controller;

import com.inspection.ws.EdgeCommandMessage;
import com.inspection.ws.EdgeDeviceRegistry;
import com.inspection.ws.EdgeDeviceSession;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/edge")
@Slf4j
@RequiredArgsConstructor
public class EdgeControlController {

    private final EdgeDeviceRegistry edgeDeviceRegistry;

    @GetMapping("/devices")
    public ResponseEntity<List<Map<String, Object>>> listDevices() {
        List<Map<String, Object>> devices = edgeDeviceRegistry.listDevices().stream()
                .map(this::toDeviceResponse)
                .toList();
        return ResponseEntity.ok(devices);
    }

    @PostMapping("/{deviceId}/inspect/trigger")
    public ResponseEntity<EdgeCommandMessage> triggerInspection(@PathVariable String deviceId) {
        EdgeCommandMessage command = edgeDeviceRegistry.sendCommand(
                deviceId,
                "inspect.trigger",
                Map.of()
        );
        return ResponseEntity.accepted().body(command);
    }

    @PostMapping("/{deviceId}/inspect/auto/start")
    public ResponseEntity<EdgeCommandMessage> startAutoInspection(
            @PathVariable String deviceId,
            @RequestParam(defaultValue = "5.0") double interval
    ) {
        EdgeCommandMessage command = edgeDeviceRegistry.sendCommand(
                deviceId,
                "inspect.auto.start",
                Map.of("interval", interval)
        );
        return ResponseEntity.accepted().body(command);
    }

    @PostMapping("/{deviceId}/inspect/auto/stop")
    public ResponseEntity<EdgeCommandMessage> stopAutoInspection(@PathVariable String deviceId) {
        EdgeCommandMessage command = edgeDeviceRegistry.sendCommand(
                deviceId,
                "inspect.auto.stop",
                Map.of()
        );
        return ResponseEntity.accepted().body(command);
    }

    @PostMapping("/{deviceId}/inspect/auto/status")
    public ResponseEntity<EdgeCommandMessage> requestAutoStatus(@PathVariable String deviceId) {
        EdgeCommandMessage command = edgeDeviceRegistry.sendCommand(
                deviceId,
                "inspect.auto.status",
                Map.of()
        );
        return ResponseEntity.accepted().body(command);
    }

    private Map<String, Object> toDeviceResponse(EdgeDeviceSession device) {
        return Map.of(
                "deviceId", device.getDeviceId(),
                "connected", device.getSession().isOpen(),
                "connectedAt", device.getConnectedAt(),
                "lastSeenAt", device.getLastSeenAt(),
                "lastStatus", device.getLastStatus(),
                "lastMessage", device.getLastMessage()
        );
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, Object>> handleIllegalState(IllegalStateException e) {
        log.warn("[Edge Control] 명령 처리 불가: {}", e.getMessage());
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("message", e.getMessage()));
    }
}
