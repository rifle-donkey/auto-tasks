# Dockerfile for Automation Framework (Podman-compatible)
FROM python:3.11-slim

# Metadata
LABEL maintainer="Automation Framework Team"
LABEL version="1.0.0"
LABEL description="Containerized automation framework with task scheduling"

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV AUTOMATION_HOME=/app
ENV AUTOMATION_DATA=/var/automation_file

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Network tools
    nmap \
    iputils-ping \
    dnsutils \
    curl \
    wget \
    # Git for repository operations
    git \
    # System utilities
    cron \
    supervisor \
    # Build tools for Python packages
    gcc \
    python3-dev \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create automation user (non-root)
RUN groupadd -r automation && useradd -r -g automation automation

# Create application directories
RUN mkdir -p $AUTOMATION_HOME \
    && mkdir -p $AUTOMATION_DATA \
    && mkdir -p /var/log/automation \
    && mkdir -p /etc/automation \
    && chown -R automation:automation $AUTOMATION_HOME \
    && chown -R automation:automation $AUTOMATION_DATA \
    && chown -R automation:automation /var/log/automation \
    && chown -R automation:automation /etc/automation

# Set working directory
WORKDIR $AUTOMATION_HOME

# Copy requirements first for better Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY automation_core/ ./automation_core/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY tests/ ./tests/

# Copy entry point scripts
COPY scheduler_entrypoint.py ./
COPY task_entrypoint.py ./
COPY manage_tasks.py ./

# Copy supervisor configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy default configuration files
COPY docker/default_schedules.yml ./config/schedules.yml
COPY docker/logging.conf ./config/logging.conf

# Create Python package structure
RUN touch automation_core/__init__.py \
    && find scripts/ -type d -exec touch {}/__init__.py \;

# Set proper permissions
RUN chown -R automation:automation $AUTOMATION_HOME \
    && chmod +x scheduler_entrypoint.py \
    && chmod +x task_entrypoint.py \
    && chmod +x manage_tasks.py

# Create volume mount points
VOLUME ["$AUTOMATION_DATA", "/home/automation/.config", "/var/log/automation", "/app/git-repos"]

# Expose health check port (optional web interface)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "from automation_core.scheduler import TaskScheduler; print('OK')" || exit 1

# Switch to automation user
USER automation

# Default entry point - run scheduler daemon
ENTRYPOINT ["python3", "scheduler_entrypoint.py"]
CMD ["--daemon"]