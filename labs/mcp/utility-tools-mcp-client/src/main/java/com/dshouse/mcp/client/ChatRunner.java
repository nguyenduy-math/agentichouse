package com.dshouse.mcp.client;

import com.dshouse.mcp.client.config.ChatClientRegistry;
import java.util.Scanner;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

/**
 * Interactive REPL. Sends each question to the currently selected provider's {@link ChatClient} with
 * the MCP server's tools attached; Spring AI runs the tool-calling loop automatically.
 *
 * <p>Pick the starting provider with {@code app.llm.default-provider} (or APP_LLM_DEFAULT_PROVIDER),
 * and switch mid-session with {@code /use <provider>}.
 */
@Component
public class ChatRunner implements CommandLineRunner {

    private final ChatClientRegistry registry;
    private String currentProvider;

    public ChatRunner(ChatClientRegistry registry) {
        this.registry = registry;
        this.currentProvider = registry.defaultProvider();
    }

    @Override
    public void run(String... args) {
        if (registry.isEmpty()) {
            System.out.println("No LLM provider is configured with an API key. "
                    + "Set GEMINI_API_KEY and/or SILICONFLOW_API_KEY and restart.");
            return;
        }
        System.out.println("Utility Tools chat. Available providers: " + registry.available());
        System.out.println("Active provider: " + currentProvider
                + "   (type /help for commands, exit to quit)");

        try (Scanner scanner = new Scanner(System.in)) {
            while (true) {
                System.out.print("\n[" + currentProvider + "] you> ");
                if (!scanner.hasNextLine()) {
                    break;
                }
                String input = scanner.nextLine().trim();
                if (input.isEmpty()) {
                    continue;
                }
                if (input.equalsIgnoreCase("exit") || input.equalsIgnoreCase("quit")) {
                    break;
                }
                if (input.startsWith("/")) {
                    handleCommand(input);
                    continue;
                }
                ask(input);
            }
        }
        System.out.println("Bye!");
    }

    private void handleCommand(String input) {
        String[] parts = input.split("\\s+", 2);
        switch (parts[0].toLowerCase()) {
            case "/help" -> System.out.println("""
                    Commands:
                      /use <provider>   switch the active provider
                      /providers        list configured providers and availability
                      /provider         show the active provider
                      /help             show this help
                      exit              quit""");
            case "/providers" -> System.out.println("Available: " + registry.available()
                    + "   Active: " + currentProvider);
            case "/provider" -> System.out.println("Active provider: " + currentProvider);
            case "/use" -> {
                if (parts.length < 2 || parts[1].isBlank()) {
                    System.out.println("Usage: /use <provider>. Available: " + registry.available());
                } else {
                    switchProvider(parts[1].trim());
                }
            }
            default -> System.out.println("Unknown command. Type /help.");
        }
    }

    private void switchProvider(String provider) {
        if (registry.has(provider)) {
            currentProvider = provider;
            System.out.println("Switched to '" + provider + "'.");
        } else {
            System.out.println("Provider '" + provider + "' is not available. Available: "
                    + registry.available());
        }
    }

    private void ask(String input) {
        ChatClient client = registry.get(currentProvider);
        try {
            String reply = client.prompt(input).call().content();
            System.out.println("\nbot> " + reply);
        } catch (Exception e) {
            System.out.println("\n[error] " + e.getMessage());
        }
    }
}
