#!/usr/bin/env bash
# Установка сайта на CentOS Stream 9 / Rocky Linux 9 / AlmaLinux 9.
# Запуск от root из папки проекта:
#   DOMAIN=example.kg SITE_NAME="НомераКР" bash deploy/install_centos.sh
#
# Что делает: ставит Python 3.11, PostgreSQL, Nginx; создаёт пользователя и БД,
# виртуальное окружение, .env, применяет миграции, заполняет регионы/марки,
# настраивает systemd (Gunicorn), Nginx, firewalld и SELinux.
set -euo pipefail

DOMAIN="${DOMAIN:?Укажите DOMAIN, например DOMAIN=example.kg}"
SITE_NAME="${SITE_NAME:-НомераКР}"
APP_USER="nomera"
APP_DIR="/opt/nomera"
WEB_DIR="/var/www/nomera"
CACHE_DIR="/var/cache/nomera"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "Запустите от root"; exit 1; }

echo "==> Пакеты"
dnf -y install epel-release || true
dnf -y install python3.11 python3.11-pip python3.11-devel gcc \
    libjpeg-turbo-devel zlib-devel freetype-devel dejavu-sans-fonts \
    nginx postgresql-server postgresql-contrib policycoreutils-python-utils rsync openssl

echo "==> Пользователь и каталоги"
id "$APP_USER" &>/dev/null || useradd --system --home "$APP_DIR" --shell /sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$WEB_DIR/static" "$WEB_DIR/media" "$CACHE_DIR"
rsync -a --delete \
    --exclude '.env' --exclude 'venv' --exclude 'db.sqlite3' --exclude '.cache' \
    --exclude 'media' --exclude 'staticfiles' --exclude '__pycache__' \
    "$SRC_DIR/" "$APP_DIR/"

echo "==> PostgreSQL"
if [[ ! -f /var/lib/pgsql/data/PG_VERSION ]]; then
    postgresql-setup --initdb
fi
# локальные подключения по паролю вместо ident
sed -i -E 's/^(host\s+all\s+all\s+(127\.0\.0\.1\/32|::1\/128)\s+)ident/\1scram-sha-256/' /var/lib/pgsql/data/pg_hba.conf
systemctl enable --now postgresql
systemctl reload postgresql

ENV_FILE="$APP_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    echo "==> Найден существующий .env — не перезаписываю"
    DB_PASSWORD="$(grep -E '^DB_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
else
    DB_PASSWORD="$(openssl rand -hex 16)"
    SECRET_KEY="$(openssl rand -base64 48 | tr -d '\n/+=')"
    cat > "$ENV_FILE" <<EOF
DEBUG=0
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$DOMAIN,www.$DOMAIN,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://$DOMAIN,https://www.$DOMAIN,http://$DOMAIN
HTTPS=0
SITE_NAME=$SITE_NAME
WATERMARK_TEXT=$DOMAIN
DB_NAME=nomera
DB_USER=nomera
DB_PASSWORD=$DB_PASSWORD
DB_HOST=127.0.0.1
DB_PORT=5432
STATIC_ROOT=$WEB_DIR/static
MEDIA_ROOT=$WEB_DIR/media
CACHE_DIR=$CACHE_DIR
UPLOADS_PER_DAY=30
MAX_UPLOAD_MB=8
EOF
fi
chmod 640 "$ENV_FILE"

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='nomera'" | grep -q 1; then
    sudo -u postgres psql -c "CREATE ROLE nomera LOGIN PASSWORD '$DB_PASSWORD';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='nomera'" | grep -q 1; then
    sudo -u postgres createdb -O nomera -E UTF8 nomera
fi

echo "==> Python окружение"
python3.11 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$APP_USER":"$APP_USER" "$APP_DIR" "$WEB_DIR" "$CACHE_DIR"

echo "==> Миграции, статика, начальные данные"
sudo -u "$APP_USER" bash -c "cd $APP_DIR && venv/bin/python manage.py migrate --noinput \
    && venv/bin/python manage.py collectstatic --noinput \
    && venv/bin/python manage.py seed_data"

echo "==> systemd"
install -m 644 "$APP_DIR/deploy/nomera.service" /etc/systemd/system/nomera.service
systemctl daemon-reload
systemctl enable --now nomera
systemctl restart nomera

echo "==> Nginx"
sed "s/__DOMAIN__/$DOMAIN/g" "$APP_DIR/deploy/nginx.conf" > /etc/nginx/conf.d/nomera.conf
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> SELinux и firewall"
if command -v getenforce &>/dev/null && [[ "$(getenforce)" != "Disabled" ]]; then
    setsebool -P httpd_can_network_connect 1
    semanage fcontext -a -t httpd_sys_content_t "$WEB_DIR(/.*)?" 2>/dev/null \
        || semanage fcontext -m -t httpd_sys_content_t "$WEB_DIR(/.*)?"
    restorecon -R "$WEB_DIR"
fi
if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-service=http --add-service=https
    firewall-cmd --reload
fi

cat <<EOF

Готово. Сайт: http://$DOMAIN/

Дальше:
  1) создайте администратора:
       sudo -u $APP_USER bash -c "cd $APP_DIR && venv/bin/python manage.py createsuperuser"
  2) включите HTTPS (бесплатный сертификат):
       dnf -y install certbot python3-certbot-nginx
       certbot --nginx -d $DOMAIN -d www.$DOMAIN
     затем в $ENV_FILE поставьте HTTPS=1 и выполните: systemctl restart nomera
  3) логи:  journalctl -u nomera -f     /var/log/nginx/error.log
  4) бэкап: pg_dump (БД nomera) и каталог $WEB_DIR/media
EOF
