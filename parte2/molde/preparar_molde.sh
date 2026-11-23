#!/bin/bash
# preparar_molde.sh - Software común de las 9 VMs (pasos 2 y 3 de la guía)
#
# Se ejecuta DENTRO de la imagen molde, con acceso a Internet:
#   - a mano, en la consola de la VM "molde" (red NAT "default"), o
#   - automáticamente, con "despliegue.py molde" (virt-customize --network).
# Por eso no depende de que systemd esté en marcha.
set -e
export DEBIAN_FRONTEND=noninteractive

# --- 2A. Software Routing Suite (FRR) y herramientas de red -------------------
apt-get update
apt-get install -y frr traceroute tcpdump curl git openssh-server
systemctl disable frr                  # sólo se activará en los 4 routers
systemctl stop frr 2>/dev/null || true

# --- 2B. Node.js 22 y servidor web SSR-master-server ------------------------
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
id -u nodeapp >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin nodeapp
rm -rf /opt/ssr-master-server
git clone --depth 1 https://github.com/gisai/SSR-master-server.git /opt/ssr-master-server
mkdir -p /opt/ssr-master-server/public/logs
(cd /opt/ssr-master-server && npm install --omit=dev --no-audit --no-fund)
chown -R nodeapp:nodeapp /opt/ssr-master-server
if [ -f "$(dirname "$0")/ssr-server.service" ]; then
    cp "$(dirname "$0")/ssr-server.service" /etc/systemd/system/ssr-server.service
fi
systemctl disable ssr-server 2>/dev/null || true   # creado, pero SIN activar
systemctl daemon-reload 2>/dev/null || true

# --- 3. Red limpia: en el laboratorio cada VM tendrá IPs fijas ---------------
rm -f /etc/netplan/50-cloud-init.yaml
cat > /etc/network/interfaces <<'EOT'
auto lo
iface lo inet loopback
EOT
apt-get clean
truncate -s 0 /etc/machine-id          # cada VM generará el suyo
echo "Molde listo."
