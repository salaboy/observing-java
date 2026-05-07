package com.example.store;

import io.smallrye.mutiny.Multi;
import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.jboss.resteasy.reactive.RestStreamElementType;

@Path("/api/chat")
public class ChatResource {

    @Inject
    ChatAssistant assistant;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public ChatResponse chat(ChatRequest request) {
        String response = assistant.chat(request.conversationId(), request.message());
        return new ChatResponse(response);
    }

    @POST
    @Path("/stream")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.SERVER_SENT_EVENTS)
    @RestStreamElementType(MediaType.TEXT_PLAIN)
    public Multi<String> chatStream(ChatRequest request) {
        return assistant.chatStream(request.conversationId(), request.message());
    }

    public record ChatRequest(String conversationId, String message) {}
    public record ChatResponse(String response) {}
}
