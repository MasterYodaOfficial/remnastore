FROM node:20-alpine AS base
WORKDIR /app

# Install dependencies
ARG NPM_REGISTRY=https://registry.npmjs.org
COPY apps/web/package*.json ./apps/web/
WORKDIR /app/apps/web
RUN npm install --no-progress --registry=$NPM_REGISTRY

# Copy source
COPY apps/web ./
COPY packages/locales /app/packages/locales

# Development server (vite)
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
