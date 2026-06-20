package com.dshouse.camel.routes;

import com.dshouse.camel.model.Order;
import com.dshouse.camel.processor.OrderProcessor;
import org.apache.camel.builder.RouteBuilder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumerRoute extends RouteBuilder {

    @Value("${app.pubsub.project-id}")
    private String projectId;

    @Value("${app.pubsub.orders-subscription}")
    private String ordersSubscription;

    @Value("${app.pubsub.dlq-topic}")
    private String dlqTopic;

    @Autowired
    private OrderProcessor orderProcessor;

    @Override
    public void configure() {
        // After 3 retries with exponential backoff, route the failed message to the DLQ topic
        errorHandler(
            deadLetterChannel(String.format("google-pubsub:%s:%s", projectId, dlqTopic))
                .maximumRedeliveries(3)
                .redeliveryDelay(500)
                .backOffMultiplier(2.0)
                .useExponentialBackOff()
                .retryAttemptedLogLevel(org.apache.camel.LoggingLevel.WARN)
                .logExhausted(true)
                .logRetryStackTrace(false)
        );

        fromF("google-pubsub:%s:%s", projectId, ordersSubscription)
            .routeId("order-consumer")
            .log("Received raw message from orders-sub")
            .unmarshal().json(Order.class)
            .process(orderProcessor)
            .log("Order ${body.id} processed successfully — status: ${body.status}");
    }
}
