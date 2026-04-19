# Use Python 3.11 as a stable base for AI
FROM python:3.11-slim

# Set Hugging Face User Environment
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Create Project Directory
WORKDIR $HOME/app

# Install System Dependencies for PDF Parsing and AI
USER root
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*
USER user

# Copy Requirements and Install
COPY --chown=user:user backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt
RUN pip install --no-cache-dir fastembed  # High-efficiency RAG engine

# Copy Project Files
COPY --chown=user:user backend/ ./backend/
COPY --chown=user:user frontend/ ./frontend/

# Set working directory to backend for uvicorn
WORKDIR $HOME/app/backend

# Create data directories with permissions
RUN mkdir -p app/data/faiss_index app/data/library_files data/pitch_decks

# Hugging Face runs on port 7860
EXPOSE 7860

# Launch with Production Hardening
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
