FROM maven:3.9.8-eclipse-temurin-17 AS builder
WORKDIR /app

COPY pom.xml .
COPY src ./src

RUN mvn -DskipTests clean package

FROM eclipse-temurin:17-jre
WORKDIR /app

COPY --from=builder /app/target/*.jar app.jar

# 프로필은 런타임 환경변수로 지정 (compose=docker, Railway=prod)
# 미지정 시 기본 application.yml 사용

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
