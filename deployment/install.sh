#!/bin/bash
#
# Production Installation Script for MustafaCLI
# Usage: sudo ./install.sh
#

set -e  # Exit on error

echo "=== MustafaCLI Production Installation ==="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}[1/8]${NC} Creating user and directories..."
# Create dedicated user
useradd -r -s /bin/false -m -d /opt/mustafacli mustafacli || echo "User already exists"

# Create directories
mkdir -p /opt/mustafacli/workspace
mkdir -p /var/log/mustafacli
chown -R mustafacli:mustafacli /opt/mustafacli
chown -R mustafacli:mustafacli /var/log/mustafacli
chmod 700 /opt/mustafacli/workspace

echo -e "${GREEN}[2/8]${NC} Installing system dependencies..."
apt-get update
apt-get install -y python3.10 python3.10-venv python3-pip git

echo -e "${GREEN}[3/8]${NC} Cloning repository..."
cd /opt/mustafacli
if [ ! -d "local-agent-cli" ]; then
    sudo -u mustafacli git clone https://github.com/kardelenyazilim/local-agent-cli.git
fi
cd local-agent-cli

echo -e "${GREEN}[4/8]${NC} Creating virtual environment..."
sudo -u mustafacli python3.10 -m venv /opt/mustafacli/venv

echo -e "${GREEN}[5/8]${NC} Installing Python dependencies..."
sudo -u mustafacli /opt/mustafacli/venv/bin/pip install --upgrade pip
sudo -u mustafacli /opt/mustafacli/venv/bin/pip install -r requirements.txt

echo -e "${GREEN}[6/8]${NC} Configuring environment..."
if [ ! -f "/opt/mustafacli/.env" ]; then
    cp deployment/production.env /opt/mustafacli/.env
    chown mustafacli:mustafacli /opt/mustafacli/.env
    chmod 600 /opt/mustafacli/.env
    echo -e "${YELLOW}⚠️  Please edit /opt/mustafacli/.env with your settings${NC}"
fi

echo -e "${GREEN}[7/8]${NC} Installing systemd service..."
cp deployment/systemd/mustafacli.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mustafacli.service

echo -e "${GREEN}[8/8]${NC} Setting up log rotation..."
cat > /etc/logrotate.d/mustafacli << EOF
/var/log/mustafacli/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 mustafacli mustafacli
    sharedscripts
    postrotate
        systemctl reload mustafacli > /dev/null 2>&1 || true
    endscript
}
EOF

echo ""
echo -e "${GREEN}✅ Installation completed!${NC}"
echo ""
echo "Next steps:"
echo "1. Edit configuration: sudo nano /opt/mustafacli/.env"
echo "2. Start service: sudo systemctl start mustafacli"
echo "3. Check status: sudo systemctl status mustafacli"
echo "4. View logs: sudo journalctl -u mustafacli -f"
echo "5. Check metrics: curl http://localhost:8000/metrics"
echo ""
echo "Security checklist:"
echo "- [ ] Update /opt/mustafacli/.env with production settings"
echo "- [ ] Ensure AGENT_ALLOW_DANGEROUS_COMMANDS=false"
echo "- [ ] Set up firewall rules"
echo "- [ ] Configure monitoring and alerting"
echo "- [ ] Set up backup for /opt/mustafacli/workspace"
echo ""
