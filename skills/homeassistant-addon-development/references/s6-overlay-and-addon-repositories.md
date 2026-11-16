# Home Assistant Add-on Development: S6-Overlay & Repository Patterns

## 1. Fixing `s6-overlay-suexec: fatal: can only run as pid 1`

When packaging standalone single-binary applications (e.g. Matrix Conduit, Go microservices, Rust binaries):

### Recommended `build.yaml`:
```yaml
build_from:
  aarch64: "alpine:3.20"
  amd64: "alpine:3.20"
```

### Recommended `Dockerfile`:
```dockerfile
ARG BUILD_FROM=alpine:3.20
FROM matrixconduit/matrix-conduit:v0.8.0 AS upstream-bin

FROM ${BUILD_FROM}

ENV LANG=C.UTF-8

RUN apk add --no-cache jq curl ca-certificates libgcc libstdc++ sqlite-dev

COPY --from=upstream-bin /srv/conduit/conduit /usr/local/bin/conduit
RUN chmod +x /usr/local/bin/conduit

COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 6167
CMD [ "/run.sh" ]
```

### Recommended `config.yaml`:
```yaml
name: "Matrix Homeserver"
slug: "matrix"
version: "0.1.1"
init: false
startup: services
boot: auto
```

---

## 2. GitHub Custom Repository Indexing (`repository.yaml`)

To ensure Home Assistant Supervisor indexes a GitHub repository cleanly:

### Root `repository.yaml`:
```yaml
name: "<Repository Name>"
url: "https://github.com/<owner>/<addon-repo>"
maintainer: "<Maintainer Name> <<email>>"
```

### Installation Steps in HA UI:
1. Open **Settings > Add-ons > Add-on Store**.
2. Click top-right menu **⋮ > Repositories**.
3. Add `https://github.com/<owner>/<addon-repo>`.
4. Install the add-on from the newly added store section.
