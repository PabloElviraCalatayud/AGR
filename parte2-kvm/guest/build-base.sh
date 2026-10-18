#!/bin/sh
# build-base.sh - Prepara la imagen base común a todos los nodos.
#
# Se ejecuta UNA vez dentro de la imagen (virt-customize --run) con acceso a
# Internet. Instala FRR (Software Routing Suite), Node.js y el servidor web,
# y deja la red en manos de agr-net.service. Los servicios específicos de
# cada rol (frr, ssr-server) quedan deshabilitados y se activan por nodo.
#
# Variables opcionales: AGR_PROXY (proxy HTTP/HTTPS), AGR_NODE_VERSION.
set -eu
export DEBIAN_FRONTEND=noninteractive

REPO_URL=https://github.com/gisai/SSR-master-server.git
APP_DIR=/opt/ssr-master-server

if [ -n "${AGR_PROXY:-}" ]; then
    export http_proxy="$AGR_PROXY" https_proxy="$AGR_PROXY"
    # Proxies con inspección TLS: Node/npm deben confiar en las CA del sistema
    export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
    printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' \
        "$AGR_PROXY" "$AGR_PROXY" > /etc/apt/apt.conf.d/99agr-proxy
fi

echo ">>> Paquetes: FRR, agente QEMU y herramientas de red"
apt-get update -q
apt-get install -y -q --no-install-recommends \
    frr frr-pythontools qemu-guest-agent \
    iproute2 iputils-ping traceroute tcpdump curl ca-certificates git xz-utils \
    procps less nano kbd keyboard-configuration console-setup

# staticd es el demonio de FRR que gestiona las rutas estáticas
sed -i 's/^staticd=no/staticd=yes/' /etc/frr/daemons || true
# watchfrr reinicia un demonio que tarda >10 s en responder y, al reiniciarlo
# por separado, no le reaplica la configuración: en una máquina cargada se
# pierden las rutas. Se amplían los plazos y se reaplica la configuración
# (vtysh -b) una vez arrancado FRR.
sed -i 's/^#*watchfrr_options=.*/watchfrr_options="-t 60 -T 90"/' /etc/frr/daemons
mkdir -p /etc/systemd/system/frr.service.d
cat > /etc/systemd/system/frr.service.d/agr.conf <<'EOF'
[Service]
ExecStartPost=/bin/sh -c 'for i in $(seq 1 30); do vtysh -c "show version" >/dev/null 2>&1 && break; sleep 2; done; sleep 3; vtysh -b >/dev/null 2>&1 || true'
EOF
systemctl disable frr.service

echo ">>> Node.js (binarios oficiales)"
# Node 22 necesita glibc >= 2.28; para imágenes antiguas se usa Node 16
GLIBC=$(ldd --version | head -n1 | awk '{print $NF}')
if [ "$(printf '%s\n' 2.28 "$GLIBC" | sort -V | head -n1)" = "2.28" ]; then
    NODE_VERSION=${AGR_NODE_VERSION:-v22.12.0}
else
    NODE_VERSION=${AGR_NODE_VERSION:-v16.20.2}
fi
curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" \
    | tar -xJ -C /opt
ln -sfn "/opt/node-$NODE_VERSION-linux-x64" /opt/node
ln -sf /opt/node/bin/node /usr/local/bin/node
/opt/node/bin/node -v

echo ">>> Servidor web SSR-master-server"
id -u nodeapp >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin nodeapp
rm -rf "$APP_DIR"
git clone --depth 1 "$REPO_URL" "$APP_DIR"
mkdir -p "$APP_DIR/public/logs"
(cd "$APP_DIR" && PATH=/opt/node/bin:$PATH npm install --omit=dev --no-audit --no-fund)
chown -R nodeapp:nodeapp "$APP_DIR"
systemctl disable ssr-server.service 2>/dev/null || true

echo ">>> Red gestionada sólo por agr-net.service"
mkdir -p /etc/cloud && touch /etc/cloud/cloud-init.disabled
rm -f /etc/netplan/*.yaml
if [ -f /etc/network/interfaces ]; then
    printf 'auto lo\niface lo inet loopback\n' > /etc/network/interfaces
    rm -f /etc/network/interfaces.d/* 2>/dev/null || true
fi
for u in systemd-networkd.service systemd-networkd.socket NetworkManager.service; do
    systemctl disable "$u" 2>/dev/null || true
done
systemctl mask systemd-networkd-wait-online.service NetworkManager-wait-online.service 2>/dev/null || true
systemctl enable agr-net.service

echo ">>> Teclado español en la consola"
cat > /etc/default/keyboard <<'EOF'
XKBMODEL="pc105"
XKBLAYOUT="es"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
EOF

# Limpieza: sin proxy, sin cachés y machine-id regenerado en cada VM
rm -f /etc/apt/apt.conf.d/99agr-proxy
apt-get clean
rm -rf /var/lib/apt/lists/*
truncate -s 0 /etc/machine-id
echo ">>> Imagen base lista"
