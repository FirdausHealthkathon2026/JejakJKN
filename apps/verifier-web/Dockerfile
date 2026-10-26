FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
ENV UV_USE_IO_URING=0
RUN npm ci
COPY . .
EXPOSE 5175
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
