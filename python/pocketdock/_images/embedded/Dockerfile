FROM alpine:3.21

# Core toolchain
RUN apk add --no-cache \
    gcc g++ musl-dev make cmake ninja \
    gdb valgrind strace \
    git curl wget unzip \
    python3 py3-pip bash

# ARM cross-compiler (Cortex-M, STM32, nRF, etc.)
RUN apk add --no-cache \
    arm-none-eabi-gcc arm-none-eabi-newlib arm-none-eabi-gdb

# Arduino CLI
RUN wget -qO- https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh -s 1.1.1 \
    && mv bin/arduino-cli /usr/local/bin/

# PlatformIO (manages ESP32/ESP-IDF, AVR, and other toolchains)
RUN pip install --no-cache-dir --break-system-packages \
    platformio meson

# Pre-install Arduino cores for offline use (optional, adds ~200MB)
# Uncomment the platforms you need, then rebuild:
# RUN arduino-cli core install arduino:avr
# RUN arduino-cli core install esp32:esp32

RUN adduser -D -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
