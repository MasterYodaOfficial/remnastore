FROM node:20-alpine AS base
WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmjs.org
COPY apps/admin/package*.json ./apps/admin/
WORKDIR /app/apps/admin
RUN npm install --no-progress --registry=$NPM_REGISTRY

COPY apps/admin ./

EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5174"]
