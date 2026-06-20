package com.dshouse.camel.processor;

import com.dshouse.camel.model.Order;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.concurrent.ConcurrentHashMap;

@Component
public class DLQProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(DLQProcessor.class);

    // In-memory store for DLQ orders — supports the /api/recovery endpoint
    private final ConcurrentHashMap<String, Order> dlqStore = new ConcurrentHashMap<>();

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void process(Exchange exchange) throws Exception {
        String body = exchange.getIn().getBody(String.class);
        Order order = objectMapper.readValue(body, Order.class);

        order.setStatus("DEAD_LETTERED");
        dlqStore.put(order.getId(), order);

        log.warn("[DLQ] Dead-lettered order stored: {} | Total in DLQ: {}", order.getId(), dlqStore.size());
    }

    public Order getOrder(String orderId) {
        return dlqStore.get(orderId);
    }

    public ConcurrentHashMap<String, Order> getDlqStore() {
        return dlqStore;
    }

    public boolean removeOrder(String orderId) {
        return dlqStore.remove(orderId) != null;
    }
}
