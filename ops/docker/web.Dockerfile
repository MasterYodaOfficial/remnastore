FROM node:22-alpine AS build
WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmjs.org

COPY apps/web/package*.json ./apps/web/
WORKDIR /app/apps/web
RUN npm ci --no-progress --registry=${NPM_REGISTRY}

COPY apps/web ./
COPY apps/bot/bot/assets /app/apps/bot/bot/assets
COPY packages/locales /app/packages/locales

RUN npm run build

FROM nginx:1.29-alpine
ENV RUNTIME_CONFIG_PATH=/usr/share/nginx/html/runtime-config.js
ENV RUNTIME_CONFIG_KEYS=VITE_API_BASE_URL,VITE_SUPABASE_URL,VITE_SUPABASE_ANON_KEY,VITE_WEB_BRAND_NAME,VITE_TELEGRAM_BOT_URL,VITE_SUPPORT_TELEGRAM_URL,VITE_TELEGRAM_WEB_APP_FALLBACK_URL
COPY ops/docker/web.nginx.conf /etc/nginx/conf.d/default.conf
COPY ops/docker/generate-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.d/40-runtime-config.sh

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
