# Use lightweight official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements if exists
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Environment variables (runtime)
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "main.py"]
