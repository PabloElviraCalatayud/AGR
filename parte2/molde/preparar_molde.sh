#!/bin/bash
# preparar_molde.sh - Órdenes ejecutadas DENTRO de la VM "molde" (pasos 2 y 3)
# La VM molde tiene Internet por la red NAT "default" de libvirt.
set -e

# --- 2A. Software Routing Suite (FRR) y herramientas de red -------------------
apt update
apt install -y frr traceroute tcpdump curl git
systemctl disable --now frr            # sólo se activará en los 4 routers

# --- 2B. Node.js 22 y servidor web SSR-master-server ------------------------
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs
id -u nodeapp >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin nodeapp
rm -rf /opt/ssr-master-server
git clone --depth 1 https://github.com/gisai/SSR-master-server.git /opt/ssr-master-server
mkdir -p /opt/ssr-master-server/public/logs
(cd /opt/ssr-master-server && npm install --omit=dev)
chown -R nodeapp:nodeapp /opt/ssr-master-server
cp "$(dirname "$0")/ssr-server.service" /etc/systemd/system/ssr-server.service 2>/dev/null || true
systemctl daemon-reload                # el servicio queda creado pero SIN activar

# --- 3. Red limpia: en el laboratorio cada VM tendrá IPs fijas ---------------
rm -f /etc/netplan/50-cloud-init.yaml
cat > /etc/network/interfaces <<'EOT'
auto lo
iface lo inet loopback
EOT
apt clean
truncate -s 0 /etc/machine-id          # cada VM generará el suyo
echo "Molde listo. Apágalo con: poweroff"
