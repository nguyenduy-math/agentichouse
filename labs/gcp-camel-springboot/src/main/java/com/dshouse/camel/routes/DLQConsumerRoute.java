package com.dshouse.camel.routes;

import com.dshouse.camel.model.Order;
import com.dshouse.camel.processor.DLQProcessor;
import org.apache.camel.builder.RouteBuilder;
import org.apache.camel.model.rest.RestParamType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DLQConsumerRoute extends RouteBuilder {

    @Value("${app.pubsub.project-id}")
    private String projectId;

    @Value("${app.pubsub.dlq-subscription}")
    private String dlqSubscription;

    @Value("${app.pubsub.orders-topic}")
    private String ordersTopic;

    @Autowired
    private DLQProcessor dlqProcessor;

    @Override
    public void configure() {
        // Consume dead-lettered messages and store them in memory for later recovery
        fromF("google-pubsub:%s:%s", projectId, dlqSubscription)
            .routeId("dlq-consumer")
            .log("[DLQ] Received failed order")
            .process(dlqProcessor)
            .log("[DLQ] Order stored for recovery");

        rest("/recovery")
            .tag("DLQ Recovery")
            .post("/{orderId}")
                .description("Re-queue a dead-lettered order back to the main processing topic")
                .produces("application/json")
                .param().name("orderId").type(RestParamType.path)
                    .description("ID of the order to recover").required(true).dataType("string")
                .endParam()
                .responseMessage().code(200).message("Order re-queued successfully").endResponseMessage()
                .responseMessage().code(404).message("Order not found in DLQ").endResponseMessage()
            .to("direct:recoverOrder");

        from("direct:recoverOrder")
            .routeId("order-recovery")
            .process(exchange -> {
                String orderId = exchange.getIn().getHeader("orderId", String.class);
                Order order = dlqProcessor.getOrder(orderId);

                if (order == null) {
                    exchange.getIn().setHeader("CamelHttpResponseCode", 404);
                    exchange.getIn().setBody("{\"error\": \"Order not found in DLQ: " + orderId + "\"}");
                    exchange.setRouteStop(true);
                    return;
                }

                order.setStatus("RECOVERING");
                dlqProcessor.removeOrder(orderId);
                exchange.getIn().setBody(order);
                log.info("[RECOVERY] Re-publishing order {} to orders-topic", orderId);
            })
            .choice()
                .when(header("CamelHttpResponseCode").isEqualTo(404))
                    .stop()
                .otherwise()
                    .marshal().json()
                    .toF("google-pubsub:%s:%s", projectId, ordersTopic)
                    .setBody(simple("{\"message\": \"Order ${header.orderId} re-queued for processing\"}"))
            .end();

        rest("/recovery")
            .tag("DLQ Recovery")
            .get()
                .description("List all orders currently waiting in the Dead Letter Queue")
                .produces("application/json")
                .outType(Order[].class)
                .responseMessage().code(200).message("Dead-lettered orders").endResponseMessage()
            .to("direct:listDlq");

        from("direct:listDlq")
            .routeId("dlq-list")
            .process(exchange -> {
                var store = dlqProcessor.getDlqStore();
                exchange.getIn().setBody(store.values());
            });
    }
}
