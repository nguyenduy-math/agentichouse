package com.dshouse.mcp.client.config;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.ai.chat.client.ChatClient;

/**
 * Holds one ready-to-use {@link ChatClient} per available provider (those that had an API key), plus
 * the effective default provider. Wrapped in a dedicated type rather than exposing a raw
 * {@code Map<String, ChatClient>} bean, which Spring would otherwise treat as a by-name collection.
 */
public class ChatClientRegistry {

    private final Map<String, ChatClient> clients;
    private final String defaultProvider;

    public ChatClientRegistry(Map<String, ChatClient> clients, String defaultProvider) {
        this.clients = new LinkedHashMap<>(clients);
        this.defaultProvider = defaultProvider;
    }

    public boolean has(String provider) {
        return provider != null && clients.containsKey(provider);
    }

    public ChatClient get(String provider) {
        return clients.get(provider);
    }

    public Set<String> available() {
        return Collections.unmodifiableSet(clients.keySet());
    }

    public boolean isEmpty() {
        return clients.isEmpty();
    }

    /** The effective default: the configured default if usable, otherwise the first available. */
    public String defaultProvider() {
        if (has(defaultProvider)) {
            return defaultProvider;
        }
        return clients.isEmpty() ? null : clients.keySet().iterator().next();
    }
}
