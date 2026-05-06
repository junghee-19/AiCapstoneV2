package com.inspection.ws;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;
import java.util.Map;

@Getter
@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
public class EdgeCommandMessage {

    private final String type;
    private final String requestId;
    private final String deviceId;
    private final LocalDateTime timestamp;
    private final Map<String, Object> payload;
}

