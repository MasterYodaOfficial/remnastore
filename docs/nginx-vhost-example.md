# Пример главного nginx на сервере

Этот вариант нужен, если:

- у сервера один IP
- вы хотите свои домены и свои сертификаты
- CloudPub не используется

Пример ниже рассчитан на такую схему:

- `api.mydomen.net` -> `127.0.0.1:8000`
- `web.mydomen.net` -> `127.0.0.1:5173`
- `admin.mydomen.net` -> `127.0.0.1:5174`
- `bot.mydomen.net` -> `127.0.0.1:8080`

Это совпадает с дефолтами из [deploy/compose.yml](/home/yoda/PycharmProjects/remnastore/deploy/compose.yml): standalone-стек сразу слушает эти порты только на `127.0.0.1`.

## Что нужно до настройки

1. Указать `A` записи доменов на IP сервера.
2. Поднять Docker-стек.
3. Получить сертификаты `Let's Encrypt` или положить свои.
4. Открыть наружу `80` и `443`.
5. Порты `8000`, `5173`, `5174`, `8080` лучше закрыть firewall'ом снаружи.

## Пример конфига

```nginx
server {
    listen 80;
    server_name api.mydomen.net web.mydomen.net admin.mydomen.net bot.mydomen.net;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.mydomen.net;

    ssl_certificate     /etc/letsencrypt/live/api.mydomen.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.mydomen.net/privkey.pem;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}

server {
    listen 443 ssl http2;
    server_name web.mydomen.net;

    ssl_certificate     /etc/letsencrypt/live/web.mydomen.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/web.mydomen.net/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}

server {
    listen 443 ssl http2;
    server_name admin.mydomen.net;

    ssl_certificate     /etc/letsencrypt/live/admin.mydomen.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.mydomen.net/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5174;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}

server {
    listen 443 ssl http2;
    server_name bot.mydomen.net;

    ssl_certificate     /etc/letsencrypt/live/bot.mydomen.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.mydomen.net/privkey.pem;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

## Какие env тогда ставить

```env
WEBAPP_URL=https://web.mydomen.net
VITE_API_BASE_URL=https://api.mydomen.net
BOT_WEBHOOK_BASE_URL=https://bot.mydomen.net
BOT_WEBHOOK_PATH=/bot/webhook
```

## Если нужен один IP и несколько сервисов

Это нормальная схема. Главное:

- отдельный `server_name` на каждый сервис
- отдельный сертификат или SAN/wildcard сертификат
- `api`, `web`, `admin`, `bot` разведены на разные локальные порты
