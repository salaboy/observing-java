package com.example.store.tracing;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.restclient.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import reactor.core.publisher.Hooks;

@Configuration(proxyBeanMethods = false)
public class ContextPropagationConfiguration {

    @PostConstruct
    void enableReactorContextPropagation() {
        Hooks.enableAutomaticContextPropagation();  // bridges ThreadLocal → Reactor Context
    }

}

