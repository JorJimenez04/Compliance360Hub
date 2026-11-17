# Compliance360 Hub — interfaz web (Next.js). Contexto de build: carpeta web/
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# API_URL se lee al construir (rewrites); Railway la pasa como variable de build
ARG API_URL
ARG NEXT_PUBLIC_APP_CLASICA_URL
ENV API_URL=${API_URL} NEXT_PUBLIC_APP_CLASICA_URL=${NEXT_PUBLIC_APP_CLASICA_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 TZ=America/Bogota
RUN apk add --no-cache tzdata && addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
