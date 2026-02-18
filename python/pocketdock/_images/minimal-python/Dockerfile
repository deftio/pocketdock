FROM alpine:3.21
RUN apk add --no-cache python3 py3-pip bash
RUN adduser -D -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
