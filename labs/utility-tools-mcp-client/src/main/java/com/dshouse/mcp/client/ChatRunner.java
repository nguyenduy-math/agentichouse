package com.dshouse.mcp.client;

import java.time.LocalDate;
import java.util.Scanner;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

/**
 * Interactive REPL: reads a question from the console, sends it to Gemini with the MCP server's
 * tools attached, and prints the answer. Spring AI runs the tool-calling loop automatically — when
 * the model requests a tool, the MCP client invokes it on the server and feeds the result back.
 */
@Component
public class ChatRunner implements CommandLineRunner {

    private final ChatClient chatClient;

    public ChatRunner(ChatClient.Builder chatClientBuilder, ToolCallbackProvider tools) {
        this.chatClient = chatClientBuilder
                .defaultSystem("You are a helpful assistant with access to utility tools "
                        + "(weather, currency conversion, timezones, unit conversion, dates, "
                        + "hashing). Today's date is " + LocalDate.now() + ". "
                        + "Use the tools when they help; answer concisely. "
                        + "For weather by city name, call 'geocode' first to get coordinates.")
                .defaultToolCallbacks(tools)
                .build();
    }

    @Override
    public void run(String... args) {
        System.out.println("Utility Tools chat (Gemini). Type a question, or 'exit' to quit.");
        try (Scanner scanner = new Scanner(System.in)) {
            while (true) {
                System.out.print("\nyou> ");
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
                try {
                    String reply = chatClient.prompt(input).call().content();
                    System.out.println("\nbot> " + reply);
                } catch (Exception e) {
                    System.out.println("\n[error] " + e.getMessage());
                }
            }
        }
        System.out.println("Bye!");
    }
}
