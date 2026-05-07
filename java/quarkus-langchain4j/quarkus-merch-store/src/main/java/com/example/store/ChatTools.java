package com.example.store;

import com.example.store.model.MerchItem;
import com.example.store.model.Order;
import com.example.store.model.OrderLine;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.agent.tool.Tool;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.jboss.logging.Logger;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@ApplicationScoped
public class ChatTools {
    private static final Logger logger = Logger.getLogger(ChatTools.class);

    @Inject
    ObjectMapper objectMapper;

    private static final String LOGO_BASE = "https://quarkus.io/extensions/static";

    static final List<MerchItem> INVENTORY = List.of(
            // 1. WireMock
            new MerchItem("WireMock",     "T-Shirt",  50, 29.99, LOGO_BASE + "/4b869a186e92db546d314d917109077a/wiremock.svg.svg"),
            new MerchItem("WireMock",     "Socks",   100, 12.99, LOGO_BASE + "/4b869a186e92db546d314d917109077a/wiremock.svg.svg"),
            new MerchItem("WireMock",     "Sticker", 200,  4.99, LOGO_BASE + "/4b869a186e92db546d314d917109077a/wiremock.svg.svg"),

            // 2. Temporal
            new MerchItem("Temporal",     "T-Shirt",  30, 29.99, LOGO_BASE + "/2a99f301eed21b0efd148d6f99670145/temporal_logo.svg.svg"),
            new MerchItem("Temporal",     "Socks",    75, 12.99, LOGO_BASE + "/2a99f301eed21b0efd148d6f99670145/temporal_logo.svg.svg"),
            new MerchItem("Temporal",     "Sticker", 150,  4.99, LOGO_BASE + "/2a99f301eed21b0efd148d6f99670145/temporal_logo.svg.svg"),

            // 3. Playwright
            new MerchItem("Playwright",   "T-Shirt",  40, 29.99, LOGO_BASE + "/3a2e616a4c02faa220f078f403535bfa/playwright-logo.svg.svg"),
            new MerchItem("Playwright",   "Socks",    80, 12.99, LOGO_BASE + "/3a2e616a4c02faa220f078f403535bfa/playwright-logo.svg.svg"),
            new MerchItem("Playwright",   "Sticker", 175,  4.99, LOGO_BASE + "/3a2e616a4c02faa220f078f403535bfa/playwright-logo.svg.svg"),

            // 4. Sentry
            new MerchItem("Sentry",       "T-Shirt",  35, 29.99, LOGO_BASE + "/2ecdfff31d4aac618b268429ffb002b8/sentry.svg.svg"),
            new MerchItem("Sentry",       "Socks",    90, 12.99, LOGO_BASE + "/2ecdfff31d4aac618b268429ffb002b8/sentry.svg.svg"),
            new MerchItem("Sentry",       "Sticker", 160,  4.99, LOGO_BASE + "/2ecdfff31d4aac618b268429ffb002b8/sentry.svg.svg"),

            // 5. Splunk
            new MerchItem("Splunk",       "T-Shirt",  25, 29.99, LOGO_BASE + "/47b235fc9026b8e5a75164e3fe88a779/splunk.svg.svg"),
            new MerchItem("Splunk",       "Socks",    60, 12.99, LOGO_BASE + "/47b235fc9026b8e5a75164e3fe88a779/splunk.svg.svg"),
            new MerchItem("Splunk",       "Sticker", 140,  4.99, LOGO_BASE + "/47b235fc9026b8e5a75164e3fe88a779/splunk.svg.svg"),

            // 6. OpenAPI
            new MerchItem("OpenAPI",      "T-Shirt",  20, 29.99, LOGO_BASE + "/174f0565ebd592ea8d5d190654c10c0e/openapi.svg.svg"),
            new MerchItem("OpenAPI",      "Socks",    55, 12.99, LOGO_BASE + "/174f0565ebd592ea8d5d190654c10c0e/openapi.svg.svg"),
            new MerchItem("OpenAPI",      "Sticker", 120,  4.99, LOGO_BASE + "/174f0565ebd592ea8d5d190654c10c0e/openapi.svg.svg"),

            // 7. Apache POI
            new MerchItem("Apache POI",   "T-Shirt",  15, 29.99, LOGO_BASE + "/1707321346263664c650828ef1bd8cd5/poi.svg.svg"),
            new MerchItem("Apache POI",   "Socks",    40, 12.99, LOGO_BASE + "/1707321346263664c650828ef1bd8cd5/poi.svg.svg"),
            new MerchItem("Apache POI",   "Sticker", 100,  4.99, LOGO_BASE + "/1707321346263664c650828ef1bd8cd5/poi.svg.svg"),

            // 8. Helm
            new MerchItem("Helm",         "T-Shirt",  10, 29.99, LOGO_BASE + "/da45637ad3f2757f40cc09e80ebc25c0/helm.svg.svg"),
            new MerchItem("Helm",         "Socks",    30, 12.99, LOGO_BASE + "/da45637ad3f2757f40cc09e80ebc25c0/helm.svg.svg"),
            new MerchItem("Helm",         "Sticker",  80,  4.99, LOGO_BASE + "/da45637ad3f2757f40cc09e80ebc25c0/helm.svg.svg"),

            // 9. Apache PDFBox
            new MerchItem("Apache PDFBox","T-Shirt",  18, 29.99, LOGO_BASE + "/b3290b889b7a52e00b8ffb49f1c62100/pdfbox.svg.svg"),
            new MerchItem("Apache PDFBox","Sticker",  90,  4.99, LOGO_BASE + "/b3290b889b7a52e00b8ffb49f1c62100/pdfbox.svg.svg"),

            // 10. JGit
            new MerchItem("JGit",         "T-Shirt",  12, 29.99, LOGO_BASE + "/f7287ff316e284af16ce082c870c478f/jgit.svg.svg"),
            new MerchItem("JGit",         "Sticker",  70,  4.99, LOGO_BASE + "/f7287ff316e284af16ce082c870c478f/jgit.svg.svg")
    );


    @Tool("Get the stock quantity and price of a Quarkus merch item by project name and/or type (T-Shirt, Socks, Sticker)")
    public String getItemStock(String itemName) {
        String query = itemName.toLowerCase();
        List<MerchItem> matches = INVENTORY.stream()
                .filter(item -> item.displayName().toLowerCase().contains(query)
                        || item.projectName().toLowerCase().contains(query)
                        || item.type().toLowerCase().contains(query))
                .toList();

        if (matches.isEmpty()) {
            return "No merch found matching '" + itemName + "'";
        }

        return matches.stream()
                .map(item -> String.format("- %s: %d units in stock at $%.2f (logo: %s)",
                        item.displayName(), item.quantity(), item.price(), item.logoUrl()))
                .collect(Collectors.joining("\n"));
    }

    @Tool("Display visual product cards for Quarkus merch items with their project logos in the UI. "
            + "Pass a project name (e.g. 'Quarkus'), a type (e.g. 'T-Shirt', 'Socks', 'Sticker'), or 'all' to show everything.")
    public String displayMerchImages(String query) {
        List<MerchItem> items;
        if ("all".equalsIgnoreCase(query.trim())) {
            items = INVENTORY;
        } else {
            String q = query.toLowerCase();
            items = INVENTORY.stream()
                    .filter(item -> item.displayName().toLowerCase().contains(q)
                            || item.projectName().toLowerCase().contains(q)
                            || item.type().toLowerCase().contains(q))
                    .toList();
        }
        String json = items.stream()
                .map(item -> String.format(
                        "{\"projectName\":\"%s\",\"type\":\"%s\",\"price\":%.2f,\"stock\":%d,\"logoUrl\":\"%s\"}",
                        item.projectName(), item.type(), item.price(), item.quantity(), item.logoUrl()))
                .collect(Collectors.joining(",", "[", "]"));
        return "<merch-items>" + json + "</merch-items>";
    }

    @Tool("Place a confirmed order for one or more Quarkus merch items. "
            + "Call this only after the user has explicitly confirmed they want to place the order. "
            + "Each line must include the project name, type (T-Shirt, Socks, or Sticker), and quantity.")
    public String placeOrder(List<OrderLine> items) {
        // The tool-argument deserializer erases the generic element type, so
        // entries arrive as LinkedHashMap. Iterating as Stream<OrderLine> would
        // trigger an implicit checkcast in the lambda's SAM bridge before any
        // instanceof check could run, so convert the whole list via Jackson.
        List<OrderLine> orderLines = objectMapper.convertValue(items,
                objectMapper.getTypeFactory().constructCollectionType(List.class, OrderLine.class));

        List<MerchItem> orderedItems = new ArrayList<>();
        double total = 0.0;
        List<String> notFound = new ArrayList<>();

        for (OrderLine line : orderLines) {
            MerchItem match = INVENTORY.stream()
                    .filter(inv -> inv.projectName().equalsIgnoreCase(line.projectName())
                            && inv.type().equalsIgnoreCase(line.type()))
                    .findFirst()
                    .orElse(null);

            if (match == null) {
                notFound.add(line.projectName() + " " + line.type());
                continue;
            }
            for (int i = 0; i < line.quantity(); i++) {
                orderedItems.add(match);
            }
            total += match.price() * line.quantity();
        }

        if (!notFound.isEmpty()) {
            return "Could not place order — the following items were not found in the catalog: "
                    + String.join(", ", notFound);
        }

        String orderId = UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        Order order = new Order(orderId, orderedItems, total);
        logger.infof("Placed order #%s for %s", orderId, order.items());
        return String.format(
                "Your order #%s has been placed successfully! 🎉%n" +
                        "Items: %s%n" +
                        "Total: %s%n" +
                        "It will be shipped to you as soon as possible. Thank you for shopping at the Quarkus Merch Store!",
                order.orderId(),
                orderedItems.stream()
                        .collect(Collectors.groupingBy(MerchItem::displayName, Collectors.counting()))
                        .entrySet().stream()
                        .map(e -> e.getValue() + "x " + e.getKey())
                        .collect(Collectors.joining(", ")),
                order.displayTotalPrice()
        );
    }

    @Tool("List all available Quarkus project merch items (T-Shirts, Socks, Stickers) with their quantities and prices")
    public String listAllItems() {
        StringBuilder sb = new StringBuilder("Current Quarkus merch inventory:\n");
        String currentProject = "";
        for (MerchItem item : INVENTORY) {
            if (!item.projectName().equals(currentProject)) {
                currentProject = item.projectName();
                sb.append("\n").append(currentProject).append(" (").append(item.logoUrl()).append(")\n");
            }
            sb.append(String.format("  - %s: %d units at $%.2f%n", item.type(), item.quantity(), item.price()));
        }
        return sb.toString();
    }
}
