package com.dshouse.mcp.client.config;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.model.SimpleApiKey;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Builds one {@link ChatClient} per configured provider that has an API key. Each client targets an
 * OpenAI-compatible endpoint (Gemini or SiliconFlow) and shares the same MCP tools and system prompt.
 */
@Configuration
@EnableConfigurationProperties(LlmProperties.class)
public class ChatClientConfig {

    private static final String SYSTEM_PROMPT =
            "You are a helpful assistant with access to utility tools (weather, currency conversion, "
            + "timezones, unit conversion, dates, hashing). Use the tools when they help; answer "
            + "concisely. For weather by city name, call 'geocode' first to get coordinates.";

    @Bean
    public ChatClientRegistry chatClientRegistry(LlmProperties props, ToolCallbackProvider tools) {
        Map<String, ChatClient> clients = new LinkedHashMap<>();
        String system = SYSTEM_PROMPT + " Today's date is " + LocalDate.now() + ".";

        for (Map.Entry<String, LlmProperties.Provider> entry : props.getProviders().entrySet()) {
            LlmProperties.Provider p = entry.getValue();
            if (!p.hasKey()) {
                continue;
            }
            OpenAiApi api = OpenAiApi.builder()
                    .baseUrl(p.getBaseUrl())
                    .apiKey(new SimpleApiKey(p.getApiKey()))
                    .completionsPath(p.getCompletionsPath())
                    .build();
            OpenAiChatModel model = OpenAiChatModel.builder()
                    .openAiApi(api)
                    .defaultOptions(OpenAiChatOptions.builder()
                            .model(p.getModel())
                            .temperature(p.getTemperature())
                            .build())
                    .build();
            ChatClient client = ChatClient.builder(model)
                    .defaultSystem(system)
                    .defaultToolCallbacks(tools)
                    .build();
            clients.put(entry.getKey(), client);
        }
        return new ChatClientRegistry(clients, props.getDefaultProvider());
    }
}
