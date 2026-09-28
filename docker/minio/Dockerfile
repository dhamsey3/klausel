# MinIO stopped publishing community images (Docker Hub / Quay) in late 2025,
# but the AGPL source is still public. This builds pinned releases of the
# server and the `mc` client from source.
#
#   docker compose build            # done automatically by `docker compose up`

ARG GO_VERSION=1.24

FROM golang:${GO_VERSION}-alpine AS build
RUN apk add --no-cache git
ENV CGO_ENABLED=0 GOTOOLCHAIN=auto

ARG MINIO_RELEASE=RELEASE.2025-04-22T22-12-26Z
RUN git clone --depth 1 --branch ${MINIO_RELEASE} https://github.com/minio/minio.git /src/minio \
 && cd /src/minio \
 && go build -trimpath -ldflags "-s -w" -o /out/minio .

ARG MC_RELEASE=RELEASE.2025-04-16T18-13-26Z
RUN git clone --depth 1 --branch ${MC_RELEASE} https://github.com/minio/mc.git /src/mc \
 && cd /src/mc \
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
