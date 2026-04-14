# FinRAG Deployment Guide

## 🚀 Production Deployment

### Prerequisites
- Python 3.10+
- PostgreSQL (optional, for production database)
- Redis (optional, for caching)
- SSL certificate (for HTTPS)
- Domain name configured

### Environment Setup

#### 1. Server Setup
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3.10 python3.10-venv python3-pip -y

# Install system dependencies
sudo apt install nginx supervisor postgresql redis-server -y
```

#### 2. Application Setup
```bash
# Clone repository
git clone <repository-url>
cd fin_rag

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
cd backend
pip install -r requirements.txt

# Create environment file
cat > .env << EOF
ANTHROPIC_API_KEY=your_production_api_key
CLAUDE_MODEL=claude-3-sonnet-20240229
ENVIRONMENT=production
EOF

# Create data directories
mkdir -p app/data/documents
mkdir -p app/data/uploads
mkdir -p app/data/faiss_index
```

#### 3. Database Setup (Optional)
```bash
# Create PostgreSQL database
sudo -u postgres psql
CREATE DATABASE finrag;
CREATE USER finrag_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE finrag TO finrag_user;
\q

# Update database connection in .env
echo "DATABASE_URL=postgresql://finrag_user:secure_password@localhost/finrag" >> .env
```

#### 4. Nginx Configuration
```nginx
# /etc/nginx/sites-available/finrag
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Increase upload size
    client_max_body_size 50M;
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/finrag /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 5. Supervisor Configuration
```ini
# /etc/supervisor/conf.d/finrag.conf
[program:finrag]
command=/path/to/fin_rag/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 9000
directory=/path/to/fin_rag/backend
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/finrag.err.log
stdout_logfile=/var/log/finrag.out.log
environment=ENVIRONMENT="production"
```

```bash
# Start service
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start finrag
```

#### 6. SSL Setup (Let's Encrypt)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

## 🔒 Security Configuration

### API Key Management
```bash
# Generate secure API key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update in environment and client applications
echo "API_KEY=your_secure_api_key" >> .env
```

### Firewall Setup
```bash
# Allow necessary ports
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### File Permissions
```bash
# Set appropriate permissions
chmod -R 755 /path/to/fin_rag
chmod -R 644 /path/to/fin_rag/backend/app/data/*.json
chmod -R 700 /path/to/fin_rag/backend/app/data
```

## 📊 Monitoring & Logging

### Log Configuration
```python
# Add to backend/app/main.py
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/finrag/app.log'),
        logging.StreamHandler()
    ]
)
```

### Health Check Endpoint
```python
# Add to backend/app/main.py
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
```

### Monitoring Setup
```bash
# Install monitoring tools
sudo apt install htop iotop -y

# Set up log rotation
sudo cat > /etc/logrotate.d/finrag << EOF
/var/log/finrag/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
}
EOF
```

## 🔄 Backup Strategy

### Data Backup
```bash
# Create backup script
cat > /usr/local/bin/backup_finrag.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/finrag"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup data directory
tar -czf $BACKUP_DIR/data_$DATE.tar.gz /path/to/fin_rag/backend/app/data

# Backup database (if using PostgreSQL)
pg_dump -U finrag_user finrag > $BACKUP_DIR/db_$DATE.sql

# Keep last 7 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
EOF

chmod +x /usr/local/bin/backup_finrag.sh

# Add to crontab
crontab -e
# Add: 0 2 * * * /usr/local/bin/backup_finrag.sh
```

## 🚀 Scaling Considerations

### Horizontal Scaling
- Use load balancer (Nginx/HAProxy)
- Deploy multiple instances behind load balancer
- Use shared storage (NFS/S3) for data directory
- Implement session management with Redis

### Vertical Scaling
- Increase CPU cores
- Add more RAM (recommend 16GB+ for production)
- Use SSD storage for faster I/O
- Optimize database queries

### Caching Strategy
```python
# Add Redis caching for expensive operations
import redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Cache RAG results
def get_cached_query(query):
    cached = redis_client.get(f"query:{query}")
    if cached:
        return json.loads(cached)
    return None

def cache_query(query, result):
    redis_client.setex(f"query:{query}", 3600, json.dumps(result))
```

## 🧪 Pre-Deployment Checklist

- [ ] All environment variables configured
- [ ] API keys secured and rotated
- [ ] Database migrations completed
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Backup strategy implemented
- [ ] Monitoring and logging setup
- [ ] Load testing completed
- [ ] Security audit performed
- [ ] Documentation updated
- [ ] Team trained on deployment process

## 🐛 Troubleshooting

### Common Production Issues

**High Memory Usage**
- Monitor with `htop`
- Limit document upload sizes
- Implement request queuing
- Add memory limits to supervisor config

**Slow Performance**
- Check database query performance
- Implement caching
- Optimize FAISS index
- Scale horizontally if needed

**API Rate Limiting**
- Implement request throttling
- Use mock data fallbacks
- Add CDN for static assets
- Cache external API responses

## 📈 Performance Optimization

### Database Optimization
```sql
-- Add indexes
CREATE INDEX idx_documents_company ON documents(company);
CREATE INDEX idx_documents_type ON documents(type);
CREATE INDEX idx_chat_memory_session ON chat_memory(session_id);
```

### Application Optimization
```python
# Add connection pooling
from sqlalchemy.pool import QueuePool
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)

# Enable compression
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

## 🔧 Maintenance

### Regular Maintenance Tasks
- Weekly: Check logs for errors
- Monthly: Update dependencies
- Quarterly: Security audit
- Annually: Review and update architecture

### Dependency Updates
```bash
# Update requirements
pip list --outdated
pip install --upgrade package_name
pip freeze > requirements.txt
```

---

**FinRAG Production Deployment Guide v1.0**
