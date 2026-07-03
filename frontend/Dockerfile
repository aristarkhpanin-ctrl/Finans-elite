# Frontend: сборка SPA (Node) → раздача статики через nginx.
# --- Стадия сборки ---
FROM node:20-alpine AS build
WORKDIR /app

# Сначала манифесты — кэш слоя npm ci не сбрасывается при правке исходников.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Стадия раздачи ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
