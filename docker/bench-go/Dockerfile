# Go benchmark image for the "small VPS" profile (docs/measurement.md, decision 0012). A static
# binary on an empty base; the bundle, reference inputs and results are mounted at run time.
FROM golang:1.27 AS build
WORKDIR /src
COPY go/go.mod go/go.sum ./
RUN go mod download
COPY go/ ./
RUN CGO_ENABLED=0 go build -trimpath -o /tier1-bench ./cmd/tier1-bench

FROM scratch
COPY --from=build /tier1-bench /tier1-bench
ENV GOMAXPROCS=1
WORKDIR /app
ENTRYPOINT ["/tier1-bench"]
