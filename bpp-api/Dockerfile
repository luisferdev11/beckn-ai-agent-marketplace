FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install --production

COPY migrations/ ./migrations/
COPY src/ ./src/

ENV PORT=3002

EXPOSE 3002

# Run migrations then start the server
CMD ["sh", "-c", "node src/migrate.js; node src/index.js"]
