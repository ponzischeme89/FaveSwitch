# syntax=docker/dockerfile:1.6

## Build stage: bundle Svelte/Vite frontend
FROM node:20-alpine AS build
WORKDIR /app
ENV NODE_ENV=production

COPY frontend/package*.json ./
RUN npm ci --ignore-scripts

COPY frontend/ ./
RUN npm run build

## Runtime stage: serve static assets with nginx and proxy /api to backend
FROM nginx:1.25-alpine

ENV API_PROXY_TARGET=http://server:5000 \
    PORT=4173

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 4173
CMD ["nginx", "-g", "daemon off;"]
