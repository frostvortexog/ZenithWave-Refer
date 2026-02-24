# Use PHP CLI
FROM php:8.2-cli

# Install system packages
RUN apt-get update && apt-get install -y \
    curl \
    git \
    unzip

# (Optional but recommended) install useful PHP extensions
RUN docker-php-ext-install pdo pdo_mysql

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Expose port (Render requirement)
EXPOSE 10000

# Run PHP server
CMD ["php", "-S", "0.0.0.0:10000", "-t", "/app"]
