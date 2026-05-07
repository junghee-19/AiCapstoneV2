package com.inspection.ws;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Component
@Slf4j
@RequiredArgsConstructor
public class EdgeDeviceRegistry {

    private final ObjectMapper objectMapper;
    private final Map<String, EdgeDeviceSession> devices = new ConcurrentHashMap<>();

    public void register(String deviceId, WebSocketSession session) {
        devices.put(deviceId, new EdgeDeviceSession(deviceId, session));
        log.info("[Edge WS] 디바이스 연결: {} ({})", deviceId, session.getId());
    }

    public void unregister(WebSocketSession session) {
        devices.entrySet().removeIf(entry -> {
            boolean matched = entry.getValue().getSession().getId().equals(session.getId());
            if (matched) {
                log.info("[Edge WS] 디바이스 연결 해제: {} ({})", entry.getKey(), session.getId());
            }
            return matched;
        });
    }

    public Collection<EdgeDeviceSession> listDevices() {
        return devices.values();
    }

    public Optional<EdgeDeviceSession> find(String deviceId) {
        return Optional.ofNullable(devices.get(deviceId))
                .filter(device -> device.getSession().isOpen());
    }

    public EdgeCommandMessage sendCommand(
            String deviceId,
            String type,
            Map<String, Object> payload
    ) {
        EdgeDeviceSession device = find(deviceId)
                .orElseThrow(() -> new IllegalStateException("Edge device is not connected: " + deviceId));

        EdgeCommandMessage message = EdgeCommandMessage.builder()
                .type(type)
                .requestId(UUID.randomUUID().toString())
                .deviceId(deviceId)
                .timestamp(LocalDateTime.now())
                .payload(payload)
                .build();

        try {
            String raw = objectMapper.writeValueAsString(message);
            synchronized (device.getSession()) {
                device.getSession().sendMessage(new TextMessage(raw));
            }
            device.touch();
            log.info("[Edge WS] 명령 전송: deviceId={}, type={}, requestId={}",
                    deviceId, type, message.getRequestId());
            return message;
        } catch (IOException e) {
            throw new IllegalStateException("Failed to send command to edge device: " + deviceId, e);
        }
    }

    public void updateFromMessage(String deviceId, Map<String, Object> message) {
        find(deviceId).ifPresent(device -> {
            device.updateLastMessage(message);
            Object payload = message.get("payload");
            if (payload instanceof Map<?, ?> rawPayload) {
                @SuppressWarnings("unchecked")
                Map<String, Object> status = (Map<String, Object>) rawPayload;
                if ("inspect.auto.status".equals(message.get("type")) || "edge.connected".equals(message.get("type"))) {
                    device.updateStatus(status);
                    return;
                }
            }
            device.touch();
        });
    }
}
