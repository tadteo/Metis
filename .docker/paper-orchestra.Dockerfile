# Build from repository root. Official agent source is mounted read-only at runtime.
FROM python:3.11.14-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-extra texlive-fonts-recommended texlive-science \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY .docker/paper-orchestra-requirements.txt /runtime-requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /runtime-requirements.txt
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg
WORKDIR /job
