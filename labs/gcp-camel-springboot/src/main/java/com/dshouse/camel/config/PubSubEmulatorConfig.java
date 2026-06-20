package com.dshouse.camel.config;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PubSubEmulatorConfig {

    private static final Logger log = LoggerFactory.getLogger(PubSubEmulatorConfig.class);

    @Value("${camel.component.google-pubsub.endpoint}")
    private String emulatorEndpoint;

    // The Camel Google Pub/Sub component reads PUBSUB_EMULATOR_HOST from the
    // environment. We set it programmatically here so the app works without
    // needing it pre-set in the shell.
    @PostConstruct
    void configureEmulator() {
        System.setProperty("PUBSUB_EMULATOR_HOST", emulatorEndpoint);
        log.info("Pub/Sub emulator configured at {}", emulatorEndpoint);
    }
}
