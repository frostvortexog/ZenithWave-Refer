FROM php:8.2-apache

# Install required extensions
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    git \
    && docker-php-ext-install mysqli

# Enable Apache rewrite
RUN a2enmod rewrite

# Set working directory
WORKDIR /var/www/html

# Copy project files
COPY . /var/www/html/

# Set permissions
RUN chown -R www-data:www-data /var/www/html

# Expose port
EXPOSE 80
