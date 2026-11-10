#!/bin/bash
# red.sh - Prepara el anfitrión para el laboratorio 3103 (tras cada reinicio)
set -e

# 1. KVM sí, VirtualBox no (no pueden usar la virtualización a la vez)
sudo modprobe -r vboxnetadp vboxnetflt vboxdrv 2>/dev/null || true
sudo modprobe kvm_amd

# 2. Un bridge (switch virtual) por cada red del plano
BRIDGES="br-srv br-prof br-ab br-bc br-bd br-red1 br-red2 br-red3 br-red4"
for br in $BRIDGES; do
    if ! ip link show "$br" >/dev/null 2>&1; then
        sudo ip link add "$br" type bridge
    fi
    sudo ip link set "$br" up
done

# 3. Que el cortafuegos (Docker) no filtre el tráfico entre máquinas
sudo sysctl -qw net.bridge.bridge-nf-call-iptables=0 2>/dev/null || true

# 4. El anfitrión es el PC Profesor (10.200.0.2) con rutas al laboratorio vía RA
sudo ip addr replace 10.200.0.2/30 dev br-prof
for net in 10.100.0.0/24 10.1.0.0/30 10.2.0.0/30 10.3.0.0/30 \
           10.0.1.0/24 10.0.2.0/24 10.0.3.0/24 10.0.4.0/24; do
    sudo ip route replace $net via 10.200.0.1
done

echo "Bridges listos:"
ip -br link show type bridge | grep '^br-'
