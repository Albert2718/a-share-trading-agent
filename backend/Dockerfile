FROM python:3.11-slim

WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace:/workspace/backend

COPY backend/requirements.txt /tmp/requirements.txt
COPY requirements.txt /tmp/course-agent-requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/course-agent-requirements.txt

COPY . /workspace
WORKDIR /workspace/backend
