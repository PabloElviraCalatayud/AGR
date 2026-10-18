# /etc/profile.d/agr-info.sh - resumen del nodo al iniciar sesión
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac

_agr_info() {
  local role
  role=$(awk '$1 == "role" {print $2}' /etc/agr/node.conf 2>/dev/null)
  echo "=================================================================="
  echo " AGR - Laboratorio 3103 virtualizado | nodo: $(hostname) | rol: ${role:-?}"
  echo "=================================================================="
  echo "Interfaces:"
  ip -br -4 addr show | grep -v '^lo' | sed 's/^/  /'
  echo "Tabla de rutas:"
  ip route | sed 's/^/  /'
  case "$role" in
    router)
      echo "IP forwarding: $(cat /proc/sys/net/ipv4/ip_forward)"
      systemctl is-active --quiet frr && echo "FRR: activo  (vtysh -c 'show ip route')" \
                                      || echo "FRR: inactivo (rutas instaladas con iproute2)"
      ;;
    server)
      systemctl is-active --quiet ssr-server && st=ACTIVO || st=DETENIDO
      echo "Servidor web SSR-master-server: $st en el puerto 3000"
      echo "  curl http://localhost:3000/"
      ;;
    pc)
      echo "Prueba: curl http://10.100.0.11:3000/   |   traceroute -n 10.100.0.11"
      ;;
  esac
  echo "=================================================================="
}
_agr_info
unset -f _agr_info
