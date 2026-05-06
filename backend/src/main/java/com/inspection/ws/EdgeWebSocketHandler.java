package com.inspection.ws;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.lang.NonNull;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.util.UriComponentsBuilder;

import java.util.Map;

@Component
@Slf4j
@RequiredArgsConstructor
public class EdgeWebSocketHandler extends TextWebSocketHandler {

    private static final TypeReference<Map<String, Object>> MESSAGE_TYPE = new TypeReference<>() {};

    private final ObjectMapper objectMapper;
    private final EdgeDeviceRegistry edgeDeviceRegistry;

    @Override
    public void afterConnectionEstablished(@NonNull WebSocketSession session) {
        String deviceId = resolveDeviceId(session);
        edgeDeviceRegistry.register(deviceId, session);
    }

    @Override
    protected void handleTextMessage(@NonNull WebSocketSession session, @NonNull TextMessage textMessage) throws Exception {
        Map<String, Object> message = objectMapper.readValue(textMessage.getPayload(), MESSAGE_TYPE);
        String deviceId = String.valueOf(message.getOrDefault("deviceId", resolveDeviceId(session)));
        String type = String.valueOf(message.getOrDefault("type", ""));

        edgeDeviceRegistry.updateFromMessage(deviceId, message);
        log.info("[Edge WS] 메시지 수신: deviceId={}, type={}, ok={}, requestId={}",
                deviceId,
                type,
                message.get("ok"),
                message.get("requestId"));
    }

    @Override
    public void afterConnectionClosed(@NonNull WebSocketSession session, @NonNull CloseStatus status) {
        edgeDeviceRegistry.unregister(session);
    }

    @Override
    public void handleTransportError(@NonNull WebSocketSession session, @NonNull Throwable exception) {
        log.warn("[Edge WS] 전송 오류: sessionId={}, error={}", session.getId(), exception.getMessage());
        edgeDeviceRegistry.unregister(session);
    }

    private String resolveDeviceId(WebSocketSession session) {
        if (session.getUri() == null) {
            return session.getId();
        }
        String deviceId = UriComponentsBuilder.fromUri(session.getUri())
                .build()
                .getQueryParams()
                .getFirst("deviceId");
        return (deviceId == null || deviceId.isBlank()) ? session.getId() : deviceId;
    }
}

