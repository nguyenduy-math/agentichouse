package com.dshouse.mcp.client.config;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration for the available LLM providers. Each provider is an OpenAI-API-compatible endpoint
 * (Gemini via its OpenAI-compat endpoint, SiliconFlow natively), so they share the same shape.
 *
 * <p>Bound from {@code app.llm.*} in {@code application.properties}.
 */
@ConfigurationProperties(prefix = "app.llm")
public class LlmProperties {

    /** Provider used at startup; can be overridden with APP_LLM_DEFAULT_PROVIDER. */
    private String defaultProvider = "gemini";

    /** Provider name → settings. */
    private Map<String, Provider> providers = new LinkedHashMap<>();

    public String getDefaultProvider() {
        return defaultProvider;
    }

    public void setDefaultProvider(String defaultProvider) {
        this.defaultProvider = defaultProvider;
    }

    public Map<String, Provider> getProviders() {
        return providers;
    }

    public void setProviders(Map<String, Provider> providers) {
        this.providers = providers;
    }

    /** Settings for a single OpenAI-compatible provider. */
    public static class Provider {
        private String baseUrl;
        private String completionsPath = "/v1/chat/completions";
        private String apiKey;
        private String model;
        private double temperature = 0.0;

        /** A provider is usable only if an API key has been supplied. */
        public boolean hasKey() {
            return apiKey != null && !apiKey.isBlank();
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public String getCompletionsPath() {
            return completionsPath;
        }

        public void setCompletionsPath(String completionsPath) {
            this.completionsPath = completionsPath;
        }

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public double getTemperature() {
            return temperature;
        }

        public void setTemperature(double temperature) {
            this.temperature = temperature;
        }
    }
}
