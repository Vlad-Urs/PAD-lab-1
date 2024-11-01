# Dockerfile for Gateway
FROM node:16-alpine

WORKDIR /app
# Initialize npm and install dependencies
RUN npm init -y
RUN npm install express axios express-rate-limit dotenv @grpc/grpc-js @grpc/proto-loader lodash
RUN npm install consul
RUN npm install opossum

# Copy the rest of the application files
COPY . .

EXPOSE 3000

CMD ["node", "gateway.js"]