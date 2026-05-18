# AEGIS Endpoint Agent — cross-platform build matrix.
#
# Outputs go to ./build/. Production releases sign each binary with
# cosign (linux/macos) and a code-signing cert (windows); the signing
# step is owned by the release pipeline and not invoked from this file.

VERSION := $(shell git describe --tags --dirty --always 2>/dev/null || echo dev)
LDFLAGS := -ldflags "-s -w -X main.AgentVersion=$(VERSION)"
TARGETS := \
    linux_amd64 linux_arm64 \
    darwin_amd64 darwin_arm64 \
    windows_amd64 windows_arm64

# Auto-detect Go availability so `make build` can fall back to Docker
# when the host machine doesn't have Go installed (common on the
# AEGIS server boxes since the API is Python and operators don't need
# a Go toolchain just to ship agent binaries to their fleet).
HAS_GO := $(shell command -v go 2>/dev/null)

.PHONY: help build build-docker vet test all clean

help:
	@echo "Targets:"
	@echo "  make build           Build for host OS/arch into ./build/."
	@echo "                       Uses host Go when available; otherwise"
	@echo "                       falls back to the Docker build path."
	@echo "  make build-docker    Force the Docker build path (no host Go needed)."
	@echo "  make all             Cross-build for: $(TARGETS)  (host Go required)."
	@echo "  make vet             go vet ./..."
	@echo "  make test            go test ./..."
	@echo "  make clean           Remove ./build/"

build:
ifeq ($(HAS_GO),)
	@echo "==> Go not installed — falling back to Docker build."
	@echo "    Install Go 1.22+ (https://go.dev/dl/) for a faster native build."
	@$(MAKE) build-docker
else
	mkdir -p build
	go build $(LDFLAGS) -o build/aegis-ea$(shell go env GOEXE) ./cmd/aegis-ea
endif

# Build via the multi-stage Dockerfile and copy the resulting binary out.
# Works on any host that has Docker — no host Go install required.
ARCH := $(shell uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')

build-docker:
	mkdir -p build
	docker build \
	    --build-arg TARGETOS=linux \
	    --build-arg TARGETARCH=$(ARCH) \
	    --build-arg VERSION=$(VERSION) \
	    --target build \
	    --output type=local,dest=./build \
	    .
	@echo "==> built: $$(ls -lh build/)"

vet:
	go vet ./...

test:
	go test ./...

all: vet
	@mkdir -p build
	@for target in $(TARGETS); do \
	    GOOS=$$(echo $$target | cut -d_ -f1); \
	    GOARCH=$$(echo $$target | cut -d_ -f2); \
	    EXT=""; if [ "$$GOOS" = "windows" ]; then EXT=".exe"; fi; \
	    echo "==> $$GOOS/$$GOARCH"; \
	    GOOS=$$GOOS GOARCH=$$GOARCH go build $(LDFLAGS) -o build/aegis-ea_$${GOOS}_$${GOARCH}$$EXT ./cmd/aegis-ea; \
	done
	@ls -lh build/

clean:
	rm -rf build/
