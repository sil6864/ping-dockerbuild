FROM python:3.9-alpine

RUN apk update && \
    apk add --no-cache iputils-ping curl && \
    rm -rf /var/cache/apk/*

WORKDIR /app

COPY main.py /app/

RUN chmod +x /app/main.py

ENTRYPOINT ["python3", "/app/main.py"]
