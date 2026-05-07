package com.example.store;

import io.quarkus.vertx.web.Route;
import io.quarkus.vertx.web.RouteBase;
import io.vertx.ext.web.RoutingContext;
import jakarta.enterprise.context.ApplicationScoped;

/**
 * Forwards all unmatched GET requests to the React SPA's index.html,
 * enabling client-side routing. The regex pattern excludes paths
 * containing a dot (static assets like .js, .css, .svg) and the API/health
 * endpoints, which are handled by their own routes.
 */
@ApplicationScoped
@RouteBase
public class SpaRoute {

    @Route(regex = "^/(?!api/|q/)[^.]*$", methods = Route.HttpMethod.GET)
    void forward(RoutingContext rc) {
        rc.reroute("/index.html");
    }
}
