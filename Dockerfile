FROM php:8.2-apache

# Enable Apache mod_rewrite
RUN a2enmod rewrite

# Install MySQL PDO driver and other dependencies
RUN docker-php-ext-install pdo pdo_mysql mbstring

# Copy application to web root
COPY telegrambot/ /var/www/html/

# Create required directories and set permissions
RUN mkdir -p /var/www/html/logs /var/www/html/uploads /var/www/html/temp \
    && chown -R www-data:www-data /var/www/html \
    && chmod -R 755 /var/www/html \
    && chmod -R 777 /var/www/html/logs /var/www/html/uploads /var/www/html/temp

# Configure Apache to allow .htaccess override
RUN sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf

# Apache config
RUN echo "<VirtualHost *:\${PORT:-80}>\n\
    DocumentRoot /var/www/html\n\
    <Directory /var/www/html>\n\
        Options Indexes FollowSymLinks\n\
        AllowOverride All\n\
        Require all granted\n\
    </Directory>\n\
    ErrorLog /var/www/html/logs/apache_error.log\n\
    CustomLog /var/www/html/logs/apache_access.log combined\n\
</VirtualHost>" > /etc/apache2/sites-available/000-default.conf

# Startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

ENTRYPOINT ["/start.sh"]