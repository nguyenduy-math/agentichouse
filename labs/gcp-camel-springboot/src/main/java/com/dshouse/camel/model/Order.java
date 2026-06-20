package com.dshouse.camel.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class Order {

    private String id;
    private String product;
    private double amount;
    private String status;

    public Order() {}

    public Order(String id, String product, double amount) {
        this.id = id;
        this.product = product;
        this.amount = amount;
        this.status = "PENDING";
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getProduct() { return product; }
    public void setProduct(String product) { this.product = product; }

    public double getAmount() { return amount; }
    public void setAmount(double amount) { this.amount = amount; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    @Override
    public String toString() {
        return "Order{id='" + id + "', product='" + product + "', amount=" + amount + ", status='" + status + "'}";
    }
}
