FROM oven/bun:1-alpine
RUN apk add --no-cache bash
RUN adduser -D -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
