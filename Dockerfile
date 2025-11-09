# Use the official Bun image as a base
FROM oven/bun:1

# Set the working directory
WORKDIR /app

# Copy package.json and bun.lockb to leverage Docker layer caching
# The lockfile is essential for reproducible builds.
COPY package.json bun.lockb ./

# Install dependencies using the frozen lockfile.
# This ensures the exact same dependencies are used as in your local environment.
RUN bun install --frozen-lockfile

# Copy the rest of the application code
COPY . .

# Build the TypeScript code into JavaScript
RUN bun run build

# Expose the port that the application will run on
EXPOSE 3002

# Set the command to run the application
CMD ["bun", "run", "start"]
