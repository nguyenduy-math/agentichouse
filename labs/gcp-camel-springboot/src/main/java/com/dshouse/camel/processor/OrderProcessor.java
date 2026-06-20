package com.dshouse.camel.processor;

import com.dshouse.camel.model.Order;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class OrderProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(OrderProcessor.class);

    @Override
    public void process(Exchange exchange) throws Exception {
        Order order = exchange.getIn().getBody(Order.class);

        if (order == null) {
            throw new IllegalArgumentException("Received null order payload");
        }

        log.info("Processing order: {}", order.getId());

        // Simulate ~30% transient failure rate to demonstrate DLQ routing
        if (Math.random() < 0.3) {
            throw new RuntimeException("Simulated transient failure for order: " + order.getId());
        }

        order.setStatus("PROCESSED");
        exchange.getIn().setBody(order);
        log.info("Order {} processed successfully", order.getId());
    }
}
