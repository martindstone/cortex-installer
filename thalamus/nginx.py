def make_nginx_config(path, frontend_name, frontend_ip, backend_name, backend_ip):
    config = f"""
server {{
    listen 80;
    server_name {frontend_name};
    location / {{
        proxy_pass http://{frontend_ip};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}

server {{
    listen 80;
    server_name {backend_name};
    location / {{
        proxy_pass http://{backend_ip};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    with open(path, "w") as f:
        f.write(config)
