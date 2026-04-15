package com.example.store;


import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.Network;

@TestConfiguration(proxyBeanMethods = false)
public class ContainersConfig {

    @Bean
    Network network() {
        return Network.newNetwork();
    }


}
