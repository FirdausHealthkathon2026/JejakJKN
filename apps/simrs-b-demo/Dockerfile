FROM node:22-alpine
WORKDIR /app/apps/simrs-b-demo
COPY apps/simrs-b-demo/package*.json ./
COPY libs/web-qr-scanner /app/libs/web-qr-scanner
ENV UV_USE_IO_URING=0
RUN npm install --install-links --no-audit --no-fund
COPY apps/simrs-b-demo .
EXPOSE 5176
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
