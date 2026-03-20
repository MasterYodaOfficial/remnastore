FROM node:22-alpine AS build
WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmjs.org
ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_TELEGRAM_BOT_URL
ARG VITE_SUPPORT_TELEGRAM_URL

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ENV VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}
ENV VITE_TELEGRAM_BOT_URL=${VITE_TELEGRAM_BOT_URL}
ENV VITE_SUPPORT_TELEGRAM_URL=${VITE_SUPPORT_TELEGRAM_URL}

COPY apps/web/package*.json ./apps/web/
WORKDIR /app/apps/web
RUN npm ci --no-progress --registry=${NPM_REGISTRY}

COPY apps/web ./
COPY packages/locales /app/packages/locales

RUN npm run build

FROM nginx:1.29-alpine
COPY ops/docker/web.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
