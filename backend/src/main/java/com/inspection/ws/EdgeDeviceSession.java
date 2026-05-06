package com.inspection.ws;

import lombok.Getter;
import org.springframework.web.socket.WebSocketSession;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Getter
public class EdgeDeviceSession {

    private final String deviceId;
    private final WebSocketSession session;
    private final LocalDateTime connectedAt;
    private volatile LocalDateTime lastSeenAt;
    private volatile Map<String, Object> lastStatus = new ConcurrentHashMap<>();
    private volatile Map<String, Object> lastMessage = new ConcurrentHashMap<>();

    public EdgeDeviceSession(String deviceId, WebSocketSession session) {
        this.deviceId = deviceId;
        this.session = session;
        this.connectedAt = LocalDateTime.now();
        this.lastSeenAt = this.connectedAt;
    }

    public void touch() {
        this.lastSeenAt = LocalDateTime.now();
    }

    public void updateStatus(Map<String, Object> status) {
        this.lastStatus = status;
        touch();
    }

    public void updateLastMessage(Map<String, Object> message) {
        this.lastMessage = message;
        touch();
    }
}
