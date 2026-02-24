# Use official PHP image
FROM php:8.2-cli

# Install required extensions
RUN apt-get update && apt-get install -y \
    curl \
    git \
    unzip \
    && docker-php-ext-install

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Expose port (Render requires this)
EXPOSE 10000

# Start PHP built-in server
CMD ["php", "-S", "0.0.0.0:10000"]
