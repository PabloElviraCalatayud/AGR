# -*- mode: ruby -*-
# vi: set ft=ruby :
#
# AGR - Práctica 2 (parte 1): Virtualización de servicios web con Vagrant
#
# Despliega una VM Ubuntu 22.04 en VirtualBox que:
#   - Instala Node.js y descarga de GitHub el servidor SSR-master-server.
#   - Lo ejecuta como servicio systemd escuchando en el puerto 3000 de la VM.
#   - Redirige el puerto 8080 del anfitrión al 3000 de la VM (acceso exterior).
#   - Tiene varias interfaces de red (NAT + 2 host-only + bridge opcional).
#   - Usa teclado español y zona horaria de Madrid.
#   - Muestra la configuración del servidor al iniciar sesión.
#
# Uso:
#   vagrant up                    # crear y aprovisionar la VM
#   vagrant ssh                   # entrar (se imprime la configuración)
#   vagrant provision             # volver a aprovisionar
#   vagrant halt / vagrant destroy -f
#
# Variables de entorno opcionales:
#   VM_GUI=true        abre la ventana de VirtualBox (consola con teclado ES)
#   VM_MEMORY=1024     memoria RAM en MB
#   VM_CPUS=1          número de CPUs
#   BRIDGE_IF=enp3s0   añade una interfaz en modo puente (red pública) sobre
#                      esa interfaz física del anfitrión, con IP por DHCP

# ---------------------------------------------------------------------------
# Parámetros de la práctica
# ---------------------------------------------------------------------------
VM_NAME      = "agr-nodeserver"
VM_BOX       = "bento/ubuntu-22.04"
VM_MEMORY    = (ENV["VM_MEMORY"] || 1024).to_i
VM_CPUS      = (ENV["VM_CPUS"] || 1).to_i
VM_GUI       = ENV["VM_GUI"] == "true"

IP_SERVICIO  = "192.168.56.10"   # red privada host-only (servicio web)
IP_GESTION   = "192.168.57.10"   # segunda red privada host-only (gestión)
BRIDGE_IF    = ENV["BRIDGE_IF"]  # red pública opcional (bridge)

PUERTO_GUEST = 3000              # puerto del servidor dentro de la VM
PUERTO_HOST  = 8080              # puerto expuesto en el anfitrión

REPO_URL     = "https://github.com/gisai/SSR-master-server.git"
APP_DIR      = "/opt/ssr-master-server"
APP_USER     = "nodeapp"
NODE_MAJOR   = 22

# ---------------------------------------------------------------------------
# Scripts de aprovisionamiento (Bash)
# ---------------------------------------------------------------------------

# 1) Sistema base: teclado español, locale, zona horaria, paquetes y firewall
SCRIPT_SISTEMA = <<-SHELL
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive

  echo ">>> [1/4] Configurando teclado español, locale y zona horaria"
  # Teclado de consola y X11 en español
  cat > /etc/default/keyboard <<'EOF'
XKBMODEL="pc105"
XKBLAYOUT="es"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
EOF
  apt-get update -qq
  apt-get install -y -qq keyboard-configuration console-setup kbd locales >/dev/null
  dpkg-reconfigure -f noninteractive keyboard-configuration
  setupcon --force --save-only || true
  localectl set-keymap es || true
  localectl set-x11-keymap es pc105 || true
  # Aplica el mapa en la consola actual si existe (ventana de VirtualBox)
  loadkeys es 2>/dev/null || true

  # Locale español y zona horaria
  sed -i 's/^# *es_ES.UTF-8 UTF-8/es_ES.UTF-8 UTF-8/' /etc/locale.gen
  locale-gen es_ES.UTF-8 >/dev/null
  update-locale LANG=es_ES.UTF-8
  timedatectl set-timezone Europe/Madrid

  echo ">>> [2/4] Instalando paquetes base"
  apt-get install -y -qq git curl ca-certificates gnupg ufw net-tools htop sysstat >/dev/null

  # Firewall: solo SSH y el puerto del servidor web
  ufw --force reset >/dev/null
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow 22/tcp >/dev/null
  ufw allow #{PUERTO_GUEST}/tcp >/dev/null
  ufw --force enable >/dev/null
SHELL

# 2) Node.js (repositorio oficial de NodeSource)
SCRIPT_NODE = <<-SHELL
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive

  echo ">>> [3/4] Instalando Node.js #{NODE_MAJOR}.x"
  if ! command -v node >/dev/null || ! node -v | grep -q "^v#{NODE_MAJOR}\\."; then
    curl -fsSL https://deb.nodesource.com/setup_#{NODE_MAJOR}.x | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
  fi
  echo "    node $(node -v) / npm $(npm -v)"
SHELL

# 3) Descarga del servidor desde GitHub y servicio systemd
SCRIPT_SERVIDOR = <<-SHELL
  set -euo pipefail

  echo ">>> [4/4] Desplegando SSR-master-server desde GitHub"
  id -u #{APP_USER} >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin #{APP_USER}

  if [ -d #{APP_DIR}/.git ]; then
    git -C #{APP_DIR} pull --ff-only
  else
    git clone --depth 1 #{REPO_URL} #{APP_DIR}
  fi
  mkdir -p #{APP_DIR}/public/logs
  chown -R #{APP_USER}:#{APP_USER} #{APP_DIR}

  cd #{APP_DIR}
  sudo -u #{APP_USER} -H npm install --omit=dev --no-audit --no-fund

  # Nota: se arranca con "node app.js" y no con "npm start": app.js ya hace
  # app.listen(3000) y bin/www vuelve a escuchar en el 3000, por lo que
  # "npm start" termina con EADDRINUSE.
  cat > /etc/systemd/system/ssr-server.service <<'EOF'
[Unit]
Description=SSR-master-server (Node.js Data-Logger)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=#{APP_USER}
WorkingDirectory=#{APP_DIR}
Environment=NODE_ENV=production
Environment=PORT=#{PUERTO_GUEST}
ExecStart=/usr/bin/node app.js
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable ssr-server.service >/dev/null 2>&1
  systemctl restart ssr-server.service

  # Espera a que el servidor responda dentro de la VM
  for i in $(seq 1 20); do
    if curl -fs -o /dev/null http://localhost:#{PUERTO_GUEST}/; then
      echo "    Servidor OK en http://localhost:#{PUERTO_GUEST}"
      break
    fi
    sleep 1
  done
SHELL

# 4) Información del servidor al iniciar sesión (/etc/profile.d)
SCRIPT_LOGIN_INFO = <<-SHELL
  set -euo pipefail

  # Quita el MOTD por defecto de Ubuntu para que se vea nuestra información
  chmod -x /etc/update-motd.d/* 2>/dev/null || true

  cat > /etc/profile.d/99-servidor-info.sh <<'EOF'
# Muestra la configuración del servidor en cada inicio de sesión interactivo
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac

_info_servidor() {
  local B="\\033[1m" V="\\033[32m" R="\\033[31m" C="\\033[36m" N="\\033[0m"
  local estado
  if systemctl is-active --quiet ssr-server; then estado="${V}ACTIVO${N}"; else estado="${R}DETENIDO${N}"; fi

  echo -e "${C}==================================================================${N}"
  echo -e "${B}  AGR - Servidor web Node.js (SSR-master-server) desplegado con Vagrant${N}"
  echo -e "${C}==================================================================${N}"
  echo -e "${B}Sistema${N}"
  echo "  Hostname ........ $(hostname)"
  echo "  SO .............. $(. /etc/os-release; echo "$PRETTY_NAME")"
  echo "  Kernel .......... $(uname -r)"
  echo "  CPUs ............ $(nproc)"
  echo "  Memoria ......... $(free -h | awk '/^Mem:/ {print $3" usados / "$2" totales"}')"
  echo "  Disco (/) ....... $(df -h / | awk 'NR==2 {print $3" usados / "$2" ("$5")"}')"
  echo "  Carga ........... $(cut -d' ' -f1-3 /proc/loadavg)"
  echo "  Teclado ......... $(grep XKBLAYOUT /etc/default/keyboard | cut -d'"' -f2)"
  echo "  Zona horaria .... $(timedatectl show -p Timezone --value)"
  echo
  echo -e "${B}Red${N}"
  ip -4 -o addr show scope global | awk '{printf "  %-15s %s\\n", $2, $4}'
  echo "  Gateway ......... $(ip route | awk '/^default/ {print $3" ("$5")"; exit}')"
  echo "  DNS ............. $(resolvectl dns 2>/dev/null | awk -F': ' 'NF>1 && $2!="" {print $2}' | xargs)"
  echo
  echo -e "${B}Servidor web${N}"
  echo -e "  Servicio ........ ssr-server ($estado)"
  echo "  Código .......... #{APP_DIR}  (#{REPO_URL})"
  echo "  Node.js ......... $(node -v 2>/dev/null) / npm $(npm -v 2>/dev/null)"
  echo "  Puerto en VM .... #{PUERTO_GUEST}"
  echo "  Desde la VM ..... http://localhost:#{PUERTO_GUEST}"
  echo "  Red privada ..... http://#{IP_SERVICIO}:#{PUERTO_GUEST}"
  echo "  Desde anfitrión . http://localhost:#{PUERTO_HOST}  (port forwarding #{PUERTO_HOST} -> #{PUERTO_GUEST})"
  echo "  Logs CSV ........ #{APP_DIR}/public/logs  (http://localhost:#{PUERTO_GUEST}/logs)"
  echo "  Puertos en escucha:"
  ss -tln | awk 'NR>1 {print "    "$4}' | sort -u
  echo
  echo -e "${B}Firewall (ufw)${N}"
  sudo -n ufw status 2>/dev/null | sed '/^$/d; s/^/  /'
  echo -e "${C}==================================================================${N}"
  echo "  Comandos útiles: systemctl status ssr-server | journalctl -u ssr-server -f"
  echo "  Probar:  curl 'http://localhost:#{PUERTO_GUEST}/record?id_nodo=n1&temperatura=24.5&humedad=60&co2=300&volatiles=100'"
  echo -e "${C}==================================================================${N}"
}
_info_servidor
unset -f _info_servidor
EOF
  chmod 644 /etc/profile.d/99-servidor-info.sh
SHELL

# ---------------------------------------------------------------------------
# Definición de la máquina virtual
# ---------------------------------------------------------------------------
Vagrant.configure("2") do |config|
  config.vm.box      = VM_BOX
  config.vm.hostname = VM_NAME
  config.vm.box_check_update = false

  # --- Redirección de puertos: anfitrión:8080 -> VM:3000 -----------------
  # Sin host_ip, VirtualBox escucha en todas las interfaces del anfitrión,
  # por lo que el servicio también es accesible desde otros equipos de la LAN.
  config.vm.network "forwarded_port", guest: PUERTO_GUEST, host: PUERTO_HOST,
                    protocol: "tcp", id: "nodeserver"

  # --- Interfaces de red --------------------------------------------------
  # eth0/enp0s3: NAT (la crea Vagrant siempre; da salida a Internet)
  # Red privada host-only del servicio web
  config.vm.network "private_network", ip: IP_SERVICIO
  # Segunda red privada host-only (gestión), ejemplo de VM multi-interfaz
  config.vm.network "private_network", ip: IP_GESTION
  # Red pública (bridge) opcional, IP asignada por el DHCP de la LAN
  config.vm.network "public_network", bridge: BRIDGE_IF if BRIDGE_IF

  # --- Proveedor VirtualBox ----------------------------------------------
  config.vm.provider "virtualbox" do |vb|
    vb.name   = VM_NAME
    vb.gui    = VM_GUI
    vb.memory = VM_MEMORY
    vb.cpus   = VM_CPUS
    vb.linked_clone = true
    # Limita el uso de CPU del anfitrión y usa el DNS del anfitrión
    vb.customize ["modifyvm", :id, "--cpuexecutioncap", "80"]
    vb.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
    vb.customize ["modifyvm", :id, "--description",
                  "AGR - Servidor Node.js SSR-master-server (#{IP_SERVICIO}, #{PUERTO_HOST}->#{PUERTO_GUEST})"]
  end

  # --- Aprovisionamiento --------------------------------------------------
  config.vm.provision "sistema",    type: "shell", inline: SCRIPT_SISTEMA
  config.vm.provision "node",       type: "shell", inline: SCRIPT_NODE
  config.vm.provision "servidor",   type: "shell", inline: SCRIPT_SERVIDOR
  config.vm.provision "login-info", type: "shell", inline: SCRIPT_LOGIN_INFO

  config.vm.post_up_message = <<~MSG
    VM #{VM_NAME} lista.
      - Desde el anfitrión:   http://localhost:#{PUERTO_HOST}
      - Por la red privada:   http://#{IP_SERVICIO}:#{PUERTO_GUEST}
      - Dentro de la VM:      http://localhost:#{PUERTO_GUEST}
    Entre con "vagrant ssh" para ver la configuración del servidor.
  MSG
end
