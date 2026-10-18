#!/bin/sh
# agr-net.sh - Configuración de red de un nodo de la red virtual del lab. 3103
#
# Lo ejecuta el servicio agr-net.service en cada arranque. Lee
# /etc/agr/node.conf (generado por agr_kvm.py) con líneas:
#
#   role   <router|server|pc>
#   iface  <mac> <nombre> <ip/prefijo>
#   route  <destino/prefijo> <next-hop>
#
# Las interfaces se identifican por su MAC (fijada en el XML de libvirt), se
# renombran como en el plano (ge0-0-3, ...) y se les asigna su dirección.
# En los routers las rutas estáticas las instala FRR; si FRR no está
# disponible se instalan aquí con iproute2.

CONF=/etc/agr/node.conf
[ -r "$CONF" ] || { echo "agr-net: falta $CONF" >&2; exit 1; }

log() { echo "agr-net: $*"; }

ip link set lo up

ROLE=$(awk '$1 == "role" {print $2}' "$CONF")

# Espera (máx. 30 s) a que aparezcan todas las interfaces esperadas
dev_by_mac() {
    for d in /sys/class/net/*; do
        [ "$(cat "$d/address" 2>/dev/null)" = "$1" ] && { basename "$d"; return 0; }
    done
    return 1
}
for i in $(seq 1 30); do
    missing=0
    for mac in $(awk '$1 == "iface" {print $2}' "$CONF"); do
        dev_by_mac "$mac" >/dev/null || missing=1
    done
    [ $missing -eq 0 ] && break
    sleep 1
done

# Interfaces: renombrar y direccionar
awk '$1 == "iface" {print $2, $3, $4}' "$CONF" | while read -r mac name addr; do
    dev=$(dev_by_mac "$mac") || { log "no existe interfaz con MAC $mac"; continue; }
    if [ "$dev" != "$name" ]; then
        ip link set dev "$dev" down
        ip link set dev "$dev" name "$name" && dev=$name
    fi
    ip addr flush dev "$dev"
    ip addr add "$addr" dev "$dev"
    ip link set dev "$dev" up
    log "$dev ($mac) -> $addr"
done

# Reenvío IP sólo en los routers
if [ "$ROLE" = "router" ]; then
    echo 1 > /proc/sys/net/ipv4/ip_forward
else
    echo 0 > /proc/sys/net/ipv4/ip_forward
fi

# Rutas estáticas (en routers con FRR las gestiona staticd)
if [ "$ROLE" = "router" ] && [ -x /usr/lib/frr/zebra ] && [ -s /etc/frr/frr.conf ]; then
    log "rutas estáticas delegadas en FRR"
else
    awk '$1 == "route" {print $2, $3}' "$CONF" | while read -r dst via; do
        [ "$dst" = "0.0.0.0/0" ] && dst=default
        ip route replace "$dst" via "$via" && log "ruta $dst via $via"
    done
fi
exit 0
