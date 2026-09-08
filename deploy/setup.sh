#!/usr/bin/env bash
# deploy/setup.sh — roda NO SERVIDOR (via SSH) para preparar o ambiente
set -euo pipefail

APP_DIR="$HOME/sniper-deals"
PYTHON="/usr/bin/python3"

echo "=== Atualizando sistema ==="
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

echo "=== Instalando dependências ==="
sudo apt-get install -y -qq python3 python3-venv git

echo "=== Criando diretório da aplicação ==="
mkdir -p "$APP_DIR/docs"

echo "=== Configurando git ==="
cd "$APP_DIR"
git config --global init.defaultBranch main
git config --global user.name "SniperDeals Bot"
git config --global user.email "bot@sniperdeals.local"

echo "=== Criando serviço systemd ==="
sudo tee /etc/systemd/system/sniperdeals.service > /dev/null <<EOF
[Unit]
Description=SniperDeals CSSDeals Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON sniper_deals.py
Restart=on-failure
RestartSec=30
StandardOutput=append:$APP_DIR/bot.log
StandardError=append:$APP_DIR/bot.log

[Install]
WantedBy=multi-user.target
EOF

echo "=== Habilitando serviço (mas não iniciando — precisa do .env) ==="
sudo systemctl daemon-reload
sudo systemctl enable sniperdeals.service

echo "=== Configurando logrotate ==="
sudo tee /etc/logrotate.d/sniperdeals > /dev/null <<EOF
$APP_DIR/bot.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF

echo ""
echo "✅ Servidor pronto!"
echo "   Próximo passo: copiar os arquivos do bot e criar o .env"
echo "   Depois: sudo systemctl start sniperdeals"
