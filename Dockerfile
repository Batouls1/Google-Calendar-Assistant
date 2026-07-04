# Stage 1: Compile Tailwind CSS
#=================================
# This stage only exists to run the Tailwind CLI build. It produces one file
# we actually need (ui/style.css) and then this entire stage is discarded —
# Node.js itself never ends up in the final image.
FROM node:20-alpine AS css-builder

WORKDIR /build

# Copy dependency manifest first, install, THEN copy source code.
# This ordering matters: Docker caches each instruction as a layer. If we
# copied all the source first, changing any Python file would invalidate
# the npm install cache too, forcing a slow reinstall on every rebuild.
COPY package.json ./
RUN npm install

COPY tailwind.config.js ./
COPY ui/ ./ui/

# Reads ui/input.css + tailwind.config.js, scans ui/*.html for class names
# actually used, outputs a minified production stylesheet.
RUN npx tailwindcss -i ./ui/input.css -o ./ui/style.css --minify



# Stage 2: Python application
#===============================
FROM python:3.11-slim

WORKDIR /app

# Same layer-caching principle as above: requirements.txt rarely changes,
# app code changes often. Installing dependencies before copying code means
# `docker build` skips the slow pip install step on most rebuilds.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the app actually needs to run. credentials.json, token.json,
# memory.db, and .env are deliberately never referenced here — they're
# excluded via .dockerignore as a second layer of protection, but the real
# guarantee is that we only copy these four things, nothing more.
COPY app/ ./app/
COPY server.py main.py ./
COPY ui/ ./ui/

# Overwrite the placeholder ui/ with the compiled stylesheet from stage 1.
COPY --from=css-builder /build/ui/style.css ./ui/style.css

# Swap the CDN <script> tag for a <link> to the compiled stylesheet —
# but only inside this image. The ui/index.html file on your actual machine
# is never touched; this sed command edits the copy that now lives inside
# the container filesystem.
RUN sed -i 's#<script src="https://cdn.tailwindcss.com"></script>#<link rel="stylesheet" href="/ui/style.css">#' ./ui/index.html

EXPOSE 8000

# --host 0.0.0.0 is not optional: uvicorn's default (127.0.0.1) only accepts
# connections from inside the container itself, making the app completely
# unreachable from outside — this is the single most common first-time
# Docker mistake. No --reload here either; that flag is dev-only.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]