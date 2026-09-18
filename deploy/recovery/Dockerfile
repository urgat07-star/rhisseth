FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client sshpass git curl ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scripts/automation/ /app/scripts/automation/
COPY tests/test_recovery_safety.py /app/tests/test_recovery_safety.py
COPY deploy/recovery/entrypoint.py /app/entrypoint.py
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python3", "/app/entrypoint.py"]
CMD ["preflight"]
