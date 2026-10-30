FROM node:22-alpine
WORKDIR /app/apps/simrs-a-web
COPY apps/simrs-a-web/package*.json ./
COPY libs/web-qr-scanner /app/libs/web-qr-scanner
ENV UV_USE_IO_URING=0
RUN npm install --install-links --no-audit --no-fund
COPY apps/simrs-a-web .
EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
