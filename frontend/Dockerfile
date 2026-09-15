# Dev-mode frontend container: fast to build, matches `npm run dev` locally.
# For a real deploy, add a multi-stage build (`npm run build` -> nginx) instead.
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
