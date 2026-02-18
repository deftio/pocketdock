FROM alpine:3.21
RUN apk add --no-cache python3 py3-pip bash
RUN adduser -D -s /bin/bash sandbox
COPY --chown=sandbox:sandbox demo/ /home/sandbox/demo/
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
