proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
# Replace any client-supplied forwarding chain. Uvicorn trusts this private
# Nginx peer, so forwarding an untrusted header would weaken vote throttling.
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header Origin $http_origin;
proxy_connect_timeout 5s;
proxy_read_timeout 30s;
proxy_send_timeout 30s;
proxy_hide_header Server;
proxy_hide_header X-Powered-By;
