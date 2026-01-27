# syntax=docker/dockerfile:1.6

## Build stage: bundle Svelte/Vite app
FROM node:20-alpine AS build
WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

## Runtime stage: serve static assets with nginx and proxy /api to backend
FROM nginx:1.25-alpine

# Default backend target can be overridden at runtime (e.g. API_PROXY_TARGET=http://backend:5000)
ENV API_PROXY_TARGET=http://server:5000 \
    PORT=4173

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 4173
CMD ["nginx", "-g", "daemon off;"]
