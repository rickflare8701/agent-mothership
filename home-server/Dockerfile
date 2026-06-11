FROM node:20-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    git curl tmux \
    && rm -rf /var/lib/apt/lists/*

# Install codebuff
RUN npm install -g codebuff

# Copy project files
COPY . .

# Install web terminal dependencies
RUN cd web-terminal && npm install --production

# Expose web terminal port
EXPOSE 3000

# Start web terminal
CMD ["node", "web-terminal/server.js"]
