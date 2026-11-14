.PHONY: lint fix

# Markdown (markdownlint-cli2 via npm) + Python (ruff via uvx, no install needed)
lint:
	npm run -s lint:md
	.claude/hooks/no-emoji.sh
	.claude/hooks/no-hard-wrap.py
	uvx ruff@0.16.10 check .
	uvx ruff@0.16.10 format --check .

fix:
	.claude/hooks/no-hard-wrap.py --fix
	npm run -s fix:md
	uvx ruff@0.16.10 check --fix .
	uvx ruff@0.16.10 format .

.PHONY: site site-build bench-image bench-local bench-vps go-test go-parity bench-go-image bench-go-local bench-go-vps

# Blog dev server with drafts: http://localhost:4321
site:
	cd site && npm run dev

# Production build into site/dist (drafts excluded)
site-build:
	cd site && npm run build

# Benchmarks (docs/measurement.md). Close heavy apps first; WSL2 numbers are noisy otherwise.
BENCH_BUNDLE ?= artifacts/tier1-v1/cpu
bench-image:
	docker build -f docker/bench/Dockerfile -t hayate-bench .

bench-local:
	PYTHONUNBUFFERED=1 uv run python scripts/bench_tier1.py --name bench-tier1-v1-local \
		--bundle $(BENCH_BUNDLE) --profile local-1thread --cpus 2

# Small VPS: 2 threads on one physical core (like 2 AWS vCPUs), 4 GB, 1 inference thread.
bench-vps: bench-image
	docker run --rm --cpuset-cpus=0,1 --cpus=2 --memory=4g --memory-swap=4g \
		--user $$(id -u):$$(id -g) \
		-e HAYATE_COMMIT=$$(git rev-parse HEAD)$$(git diff --quiet HEAD -- src scripts || echo -dirty) \
		-v $(CURDIR)/data:/app/data:ro -v $(CURDIR)/artifacts:/app/artifacts \
		-v $(CURDIR)/results:/app/results hayate-bench \
		--name bench-tier1-v1-vps --bundle $(BENCH_BUNDLE) --profile vps-docker-2vcpu --cpus 0

# Go tier 1 (decision 0012). go-parity needs the bundle and reference from scripts/tier1_reference.py.
go-test:
	cd go && gofmt -l . | (! grep .) && go vet ./... && go test ./...

go-parity:
	cd go && go run ./cmd/tier1-parity -bundle ../$(BENCH_BUNDLE)

bench-go-image:
	docker build -f docker/bench-go/Dockerfile -t hayate-bench-go .

bench-go-local:
	cd go && go build -o ../artifacts/tier1-bench ./cmd/tier1-bench
	cd go && GOMAXPROCS=1 taskset -c 2 ../artifacts/tier1-bench -name bench-tier1-go-local \
		-profile local-1thread -cpu 2 -bundle ../$(BENCH_BUNDLE)

bench-go-vps: bench-go-image
	docker run --rm --cpuset-cpus=0,1 --cpus=2 --memory=4g --memory-swap=4g \
		--user $$(id -u):$$(id -g) \
		-e HAYATE_COMMIT=$$(git rev-parse HEAD)$$(git diff --quiet HEAD -- go || echo -dirty) \
		-v $(CURDIR)/artifacts:/app/artifacts -v $(CURDIR)/results:/app/results hayate-bench-go \
		-name bench-tier1-go-vps -profile vps-docker-2vcpu -bundle artifacts/tier1-v1/cpu \
		-cpu 0 -out-dir results -raw-dir artifacts/bench

