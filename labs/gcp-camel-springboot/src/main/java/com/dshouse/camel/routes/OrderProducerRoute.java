package com.dshouse.camel.routes;

import com.dshouse.camel.model.Order;
import org.apache.camel.builder.RouteBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class OrderProducerRoute extends RouteBuilder {

    @Value("${app.pubsub.project-id}")
    private String projectId;

    @Value("${app.pubsub.orders-topic}")
    private String ordersTopic;

    @Override
    public void configure() {
        rest("/orders")
            .tag("Orders")
            .post()
                .description("Publish a new order to the processing queue")
                .consumes("application/json")
                .produces("application/json")
                .type(Order.class)
                .responseMessage().code(200).message("Order accepted and queued for processing").endResponseMessage()
            .to("direct:publishOrder");

        from("direct:publishOrder")
            .routeId("order-producer")
            .log("Publishing order: ${body.id}")
            .marshal().json()
            .toF("google-pubsub:%s:%s", projectId, ordersTopic)
            .setBody(simple("{\"message\": \"Order ${body} accepted\"}"));
    }
}
