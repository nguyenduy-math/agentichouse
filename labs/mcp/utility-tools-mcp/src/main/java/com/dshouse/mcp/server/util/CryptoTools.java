package com.dshouse.mcp.server.util;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

/** Hashing, encoding, and random-value generation tools (pure JDK, no network). */
@Component
public class CryptoTools {

    private static final SecureRandom RANDOM = new SecureRandom();

    @Tool(name = "hash", description = "Compute a cryptographic hash of some text. "
            + "Supported algorithms: MD5, SHA-1, SHA-256, SHA-512. Returns the lowercase hex digest.")
    public String hash(
            @ToolParam(description = "The text to hash") String text,
            @ToolParam(description = "Algorithm: MD5, SHA-1, SHA-256, or SHA-512") String algorithm) {
        String normalized = switch (algorithm == null ? "" : algorithm.trim().toUpperCase()) {
            case "MD5" -> "MD5";
            case "SHA-1", "SHA1" -> "SHA-1";
            case "SHA-256", "SHA256", "" -> "SHA-256";
            case "SHA-512", "SHA512" -> "SHA-512";
            default -> null;
        };
        if (normalized == null) {
            return "Unsupported algorithm '" + algorithm + "'. Use MD5, SHA-1, SHA-256, or SHA-512.";
        }
        try {
            MessageDigest md = MessageDigest.getInstance(normalized);
            byte[] digest = md.digest(text.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            return "Algorithm not available: " + normalized;
        }
    }

    @Tool(name = "base64_encode", description = "Base64-encode a UTF-8 text string.")
    public String base64Encode(@ToolParam(description = "The text to encode") String text) {
        return Base64.getEncoder().encodeToString(text.getBytes(StandardCharsets.UTF_8));
    }

    @Tool(name = "base64_decode", description = "Decode a Base64 string back to UTF-8 text.")
    public String base64Decode(@ToolParam(description = "The Base64 string to decode") String encoded) {
        try {
            byte[] decoded = Base64.getDecoder().decode(encoded.trim());
            return new String(decoded, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return "Invalid Base64 input: " + e.getMessage();
        }
    }

    @Tool(name = "generate_uuid", description = "Generate a random (version 4) UUID.")
    public String generateUuid() {
        return UUID.randomUUID().toString();
    }

    @Tool(name = "generate_password", description = "Generate a random password. "
            + "Length must be between 4 and 128. Optionally include symbols.")
    public String generatePassword(
            @ToolParam(description = "Desired length (4-128)") int length,
            @ToolParam(description = "Whether to include symbols like !@#$%", required = false)
                    Boolean includeSymbols) {
        if (length < 4 || length > 128) {
            return "Length must be between 4 and 128.";
        }
        String letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
        String digits = "0123456789";
        String symbols = "!@#$%^&*()-_=+[]{}";
        String pool = letters + digits + (Boolean.TRUE.equals(includeSymbols) ? symbols : "");
        StringBuilder sb = new StringBuilder(length);
        for (int i = 0; i < length; i++) {
            sb.append(pool.charAt(RANDOM.nextInt(pool.length())));
        }
        return sb.toString();
    }
}
