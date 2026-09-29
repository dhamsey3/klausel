# MinIO stopped publishing community images (Docker Hub / Quay) in late 2025,
# but the AGPL source is still public. This builds pinned releases of the
# server and the `mc` client from source.
#
#   docker compose build            # done automatically by `docker compose up`

ARG GO_VERSION=1.24

FROM golang:${GO_VERSION}-alpine AS build
RUN apk add --no-cache git
ENV CGO_ENABLED=0 GOTOOLCHAIN=auto

# Each release tag is checked against its expected commit, so a re-pointed tag
# fails the build instead of silently compiling different code.
ARG MINIO_RELEASE=RELEASE.2025-04-22T22-12-26Z
ARG MINIO_COMMIT=0d7408fc9969caf07de6a8c3a84f9fbb10a6739e
RUN git clone --depth 1 --branch ${MINIO_RELEASE} https://github.com/minio/minio.git /src/minio \
 && cd /src/minio \
 && test "$(git rev-parse HEAD)" = "${MINIO_COMMIT}" \
 && go build -trimpath -ldflags "-s -w" -o /out/minio .

ARG MC_RELEASE=RELEASE.2025-04-16T18-13-26Z
ARG MC_COMMIT=b00526b153a31b36767991a4f5ce2cced435ee8e
RUN git clone --depth 1 --branch ${MC_RELEASE} https://github.com/minio/mc.git /src/mc \
 && cd /src/mc \
 && test "$(git rev-parse HEAD)" = "${MC_COMMIT}" \
 && go build -trimpath -ldflags "-s -w" -o /out/mc .

FROM alpine:3.21 AS server
RUN apk add --no-cache ca-certificates curl
COPY --from=build /out/minio /usr/bin/minio
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/minio"]

FROM alpine:3.21 AS mc
RUN apk add --no-cache ca-certificates
COPY --from=build /out/mc /usr/bin/mc
ENTRYPOINT ["/usr/bin/mc"]
