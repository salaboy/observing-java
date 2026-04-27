FROM maven:3-eclipse-temurin-21-jammy AS build
WORKDIR /app

# Cache dependencies first
COPY pom.xml .
COPY src/main/webapp/package.json src/main/webapp/package-lock.json src/main/webapp/
RUN mvn -B dependency:go-offline -DskipTests || true

# Build the full application (Maven builds React via frontend-maven-plugin)
COPY src ./src
RUN mvn -B package -DskipTests

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app

RUN groupadd -r spring && useradd -r -g spring spring
USER spring:spring

COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
