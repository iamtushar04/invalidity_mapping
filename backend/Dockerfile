# backend/Dockerfile
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv (fast Python package installer)
RUN pip install uv

# Copy dependency files first (to cache the installation step)
COPY pyproject.toml uv.lock ./

# Install dependencies system-wide using uv
RUN uv pip install --system -r pyproject.toml

# Copy the rest of the backend code
COPY . .

# Expose the port your backend runs on (8005 based on your commands)
EXPOSE 8005

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
