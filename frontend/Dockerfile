# OSKAR Frontend — Multi-stage build
# Stage 1: Build the Vite app
# Stage 2: Serve with nginx

FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Serve ─────────────────────────────────────────────────────────────────────
FROM nginxinc/nginx-unprivileged:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config: SPA fallback — all routes serve index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
