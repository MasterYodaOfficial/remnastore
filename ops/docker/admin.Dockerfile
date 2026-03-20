FROM node:22-alpine AS build
WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmjs.org
ARG VITE_API_BASE_URL

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY apps/admin/package*.json ./apps/admin/
WORKDIR /app/apps/admin
RUN npm ci --no-progress --registry=${NPM_REGISTRY}

COPY apps/admin ./

RUN npm run build

FROM nginx:1.29-alpine
COPY ops/docker/admin.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/admin/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
