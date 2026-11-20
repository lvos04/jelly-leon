FROM docker.io/library/docker:29-cli@sha256:34507eb5069d8be82c95dd3b6987d4250fd5fee49b82e2509b7d7a7030740d6d AS cli
FROM docker.io/library/node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS node

FROM docker.io/library/python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS basis
COPY --from=cli /usr/local/bin/docker /usr/bin/docker
COPY --chmod=755 .forgejo/proeven/proefdocker.sh /usr/local/bin/docker
RUN useradd --create-home --uid 1000 proef && install -d -m 700 -o proef -g proef /home/proef/runtime
ENV HOME=/home/proef XDG_RUNTIME_DIR=/home/proef/runtime PYTHONDONTWRITEBYTECODE=1

FROM basis AS browser
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /opt/npm
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
WORKDIR /opt/playwright
COPY tools/b03-harnas/playwright/package*.json ./
RUN node /opt/npm/bin/npm-cli.js ci --no-audit --no-fund \
    && node node_modules/playwright/cli.js install --with-deps chromium firefox webkit \
    && apt-get update && apt-get install --no-install-recommends -y ffmpeg pulseaudio gstreamer1.0-pulseaudio \
       gstreamer1.0-libav gstreamer1.0-alsa libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*
