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

.PHONY: help build vet test all clean

help:
	@echo "Targets:"
	@echo "  make build           Build for the host OS/arch into ./build/"
	@echo "  make all             Cross-build for: $(TARGETS)"
	@echo "  make vet             go vet ./..."
	@echo "  make test            go test ./..."
	@echo "  make clean           Remove ./build/"

build:
	mkdir -p build
	go build $(LDFLAGS) -o build/aegis-ea$(shell go env GOEXE) ./cmd/aegis-ea

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
