#!/bin/bash
set -e

echo "Initializing database..."

# Wait for MySQL to be ready
until php -r "
try {
    \$dsn = 'mysql:host=' . getenv('DB_HOST') . ';charset=' . getenv('DB_CHARSET');
    \$pdo = new PDO(\$dsn, getenv('DB_USER'), getenv('DB_PASS'));
    echo 'MySQL is ready\n';
} catch (Exception \$e) {
    echo 'Waiting for MySQL...\n';
    exit(1);
}
"; do
    echo "Waiting for database connection..."
    sleep 3
done

# Import schema if tables don't exist
php -r "
try {
    \$dsn = 'mysql:host=' . getenv('DB_HOST') . ';dbname=' . getenv('DB_NAME') . ';charset=' . getenv('DB_CHARSET');
    \$pdo = new PDO(\$dsn, getenv('DB_USER'), getenv('DB_PASS'));
    \$stmt = \$pdo->query(\"SHOW TABLES LIKE 'transactions'\");
    if (\$stmt->rowCount() === 0) {
        \$sql = file_get_contents('/var/www/html/database/schema.sql');
        \$statements = array_filter(array_map('trim', explode(';', \$sql)));
        foreach (\$statements as \$statement) {
            if (!empty(\$statement) && !preg_match('/^(--|CREATE DATABASE|USE)/i', \$statement)) {
                \$pdo->exec(\$statement);
            }
        }
        echo \"Database schema imported successfully\\n\";
    } else {
        echo \"Database already initialized\\n\";
    }
} catch (Exception \$e) {
    echo \"Database init error: \" . \$e->getMessage() . \"\\n\";
}
"

# Start Apache
echo "Starting Apache..."
apache2-foreground