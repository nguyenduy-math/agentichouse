package com.dshouse.camel.config;

import jakarta.annotation.PostConstruct;
import org.apache.camel.CamelContext;
import org.apache.camel.component.google.pubsub.GooglePubsubComponent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PubSubEmulatorConfig {

    private static final Logger log = LoggerFactory.getLogger(PubSubEmulatorConfig.class);

    @Value("${camel.component.google-pubsub.endpoint}")
    private String emulatorEndpoint;

    // CamelContext is a Spring bean; GooglePubsubComponent lives inside it,
    // not in the Spring application context, so it cannot be injected directly.
    private final CamelContext camelContext;

    public PubSubEmulatorConfig(CamelContext camelContext) {
        this.camelContext = camelContext;
    }

    @PostConstruct
    void configureEmulator() {
        GooglePubsubComponent component =
                camelContext.getComponent("google-pubsub", GooglePubsubComponent.class);
        component.setEndpoint(emulatorEndpoint);
        component.setAuthenticate(false);
        log.info("Pub/Sub emulator configured at {} (GCP authentication disabled)", emulatorEndpoint);
    }
}
