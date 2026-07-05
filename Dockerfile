# Stage 1: Compile Tailwind CSS
FROM node:20-alpine AS css-builder
WORKDIR /build

COPY package.json ./
RUN npm install

COPY tailwind.config.js ./
COPY ui/ ./ui/
RUN npx tailwindcss -i ./ui/input.css -o ./ui/style.css --minify



# Stage 2: Python application
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY server.py main.py ./
COPY ui/ ./ui/

# Copy compiled CSS from Stage 1
COPY --from=css-builder /build/ui/style.css ./ui/style.css

# Inject production stylesheet into HTML template
RUN sed -i 's#<script src="https://cdn.tailwindcss.com"></script>#<link rel="stylesheet" href="/ui/style.css">#' ./ui/index.html

EXPOSE 8000

# host 0.0.0.0 is required for container network binding
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]