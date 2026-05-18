# Multi-stage cross-compile container for the AEGIS Endpoint Agent.
#
# `docker build` (no target arg) produces the linux/amd64 binary at
# /out/aegis-ea_linux_amd64. To build the full matrix, run from the
# repo root:
#   docker buildx build --platform linux/amd64,linux/arm64 \
#       -f agent/Dockerfile agent/
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal

ARG TARGETOS=linux
ARG TARGETARCH=amd64
ARG VERSION=dev
ENV CGO_ENABLED=0

RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build \
        -ldflags "-s -w -X main.AgentVersion=$VERSION" \
        -o /out/aegis-ea_${TARGETOS}_${TARGETARCH} ./cmd/aegis-ea

# Distroless runtime stage (the agent has no shell dependency).
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/aegis-ea_* /aegis-ea
USER nonroot:nonroot
ENTRYPOINT ["/aegis-ea"]
