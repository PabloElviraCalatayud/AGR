#!/usr/bin/env python3
"""
agr_kvm.py - Virtualización de la red del laboratorio 3103 con QEMU-KVM.

AGR - Práctica 2 (parte 2). Despliega, a partir de topologia.json y de la
plantilla XML de libvirt (plantilla_vm.xml):

  * Un bridge Linux en el anfitrión por cada red del plano de numeración.
  * Una imagen base común (Ubuntu 24.04 cloud o la imagen de Moodle) con FRR
    (Software Routing Suite), Node.js y el servidor SSR-master-server.
  * Un disco qcow2 diferencial por máquina, configurado offline con
    virt-customize (hostname, direcciones IP, rutas estáticas de FRR...).
  * Un XML por máquina generado con lxml y definido/arrancado con virsh.
  * El anfitrión hace de "PC Profesor" (10.200.0.2) con rutas hacia el lab.

Uso (como root):
  sudo ./agr_kvm.py crear          # todo: imagen base, bridges, VMs y arranque
  sudo ./agr_kvm.py estado
  sudo ./agr_kvm.py probar         # plan de pruebas de conectividad
  sudo ./agr_kvm.py consola rc     # xterm con 'virsh console agr-rc'
  sudo ./agr_kvm.py parar | arrancar
  sudo ./agr_kvm.py destruir [--todo]

Ejecute './agr_kvm.py -h' o './agr_kvm.py <orden> -h' para más opciones.
"""

import argparse
import base64
import ipaddress
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    sys.exit("Falta lxml: sudo apt install python3-lxml")

AQUI = Path(__file__).resolve().parent
GUEST = AQUI / "guest"
PREFIJO = "agr-"                      # prefijo de los dominios libvirt
URL_IMAGEN = ("https://cloud-images.ubuntu.com/minimal/releases/noble/release/"
              "ubuntu-24.04-minimal-cloudimg-amd64.img")
CONTRASENA_ROOT = "agr"
DIR_TRABAJO = Path("/var/lib/libvirt/images/agr")
TAMANO_DISCO = "6G"

log = logging.getLogger("agr_kvm")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def sh(cmd, check=True, capture=False, env=None):
    """Ejecuta un comando, registrándolo en el log de depuración."""
    log.debug("$ %s", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], check=False, text=True,
                       capture_output=capture, env=env)
    if check and r.returncode != 0:
        err = (r.stderr or "").strip() if capture else ""
        raise RuntimeError(f"Falló ({r.returncode}): {' '.join(map(str, cmd))}\n{err}")
    return r


def virsh(*args, check=True, capture=True):
    return sh(["virsh", "-c", "qemu:///system", *args], check=check, capture=capture)


def info(msg):
    print(f"\033[1;36m>>>\033[0m {msg}", flush=True)


def comprobar_entorno():
    if os.geteuid() != 0:
        sys.exit("Ejecute el script como root (sudo).")
    faltan = [c for c in ("virsh", "qemu-img", "virt-customize", "ip")
              if shutil.which(c) is None]
    if faltan:
        sys.exit("Faltan herramientas: " + ", ".join(faltan) + "\n"
                 "  sudo apt install qemu-system-x86 qemu-utils libvirt-daemon-system "
                 "libvirt-clients libguestfs-tools dhcpcd-base python3-lxml xterm")
    if not Path("/dev/kvm").exists():
        log.warning("/dev/kvm no existe: se usará emulación software (TCG), mucho "
                    "más lenta. Compruebe la virtualización en la BIOS y que el "
                    "módulo kvm_intel/kvm_amd está cargado.")
    if Path("/sys/module/vboxdrv").exists():
        log.warning("VirtualBox (vboxdrv) está cargado; si hay VMs de VirtualBox "
                    "encendidas, KVM puede fallar. Apáguelas (vagrant halt).")
    # libguestfs no necesita libvirt para manipular imágenes
    os.environ.setdefault("LIBGUESTFS_BACKEND", "direct")


def cargar_topologia(ruta):
    with open(ruta) as f:
        topo = json.load(f)
    # Validación básica: cada IP pertenece a la red a la que se conecta
    for nombre, m in topo["maquinas"].items():
        for itf in m["interfaces"]:
            red = ipaddress.ip_network(topo["redes"][itf["red"]]["cidr"])
            if ipaddress.ip_interface(itf["ip"]).network != red:
                raise ValueError(f"{nombre}/{itf['nombre']}: {itf['ip']} no está en {red}")
    return topo


def mac(idx_maquina, idx_itf):
    """MAC determinista: 52:54:00 (rango QEMU) : AA : máquina : interfaz."""
    return f"52:54:00:aa:{idx_maquina:02x}:{idx_itf:02x}"


def dominio(nombre):
    return PREFIJO + nombre


# --------------------------------------------------------------------------
# Red del anfitrión
# --------------------------------------------------------------------------
def crear_bridges(topo):
    info("Creando bridges en el anfitrión")
    for red in topo["redes"].values():
        br = red["bridge"]
        if sh(["ip", "link", "show", br], check=False, capture=True).returncode != 0:
            sh(["ip", "link", "add", "name", br, "type", "bridge"])
        sh(["ip", "link", "set", br, "up"])
        if "anfitrion" in red:
            sh(["ip", "addr", "replace", red["anfitrion"], "dev", br])
        log.info("bridge %-9s %-15s %s", br, red["cidr"], red["descripcion"])

    # Que el tráfico puenteado no pase por iptables (Docker/ufw lo bloquean)
    if Path("/proc/sys/net/bridge/bridge-nf-call-iptables").exists():
        for k in ("bridge-nf-call-iptables", "bridge-nf-call-ip6tables", "bridge-nf-call-arptables"):
            Path(f"/proc/sys/net/bridge/{k}").write_text("0\n")

    # Rutas del anfitrión (PC Profesor) hacia el resto del laboratorio
    red_prof = next(r for r in topo["redes"].values() if "anfitrion" in r)
    gw = next(itf["ip"].split("/")[0] for m in topo["maquinas"].values()
              for itf in m["interfaces"]
              if topo["redes"][itf["red"]] is red_prof)
    for red in topo["redes"].values():
        if red is red_prof:
            continue
        r = sh(["ip", "route", "show", red["cidr"]], capture=True).stdout.strip()
        if r and "via " + gw not in r:
            log.warning("El anfitrión ya tiene una ruta a %s (%s); se reemplaza", red["cidr"], r)
        sh(["ip", "route", "replace", red["cidr"], "via", gw, "dev", red_prof["bridge"]])
    log.info("anfitrión = PC Profesor %s, rutas al laboratorio vía %s",
             red_prof["anfitrion"], gw)


def borrar_bridges(topo):
    info("Eliminando bridges y rutas del anfitrión")
    for red in topo["redes"].values():
        sh(["ip", "route", "del", red["cidr"]], check=False, capture=True)
        sh(["ip", "link", "del", red["bridge"]], check=False, capture=True)


# --------------------------------------------------------------------------
# Imágenes
# --------------------------------------------------------------------------
def imagen_base(args):
    """Crea (una vez) la imagen base con todo el software instalado."""
    base = args.dir / "agr-base.qcow2"
    if base.exists() and not args.reconstruir_base:
        log.info("Imagen base existente: %s", base)
        return base

    if args.imagen_base:
        origen = Path(args.imagen_base).resolve()
        info(f"Usando imagen proporcionada: {origen}")
    else:
        origen = args.dir / Path(URL_IMAGEN).name
        if not origen.exists():
            info(f"Descargando {URL_IMAGEN}")
            sh(["curl", "-fL", "--progress-bar", "-o", origen.with_suffix(".part"), URL_IMAGEN])
            origen.with_suffix(".part").rename(origen)

    info("Construyendo la imagen base (FRR, Node.js, servidor web). Tarda unos minutos...")
    tmp = base.with_suffix(".tmp")
    # Copia independiente (no se modifica la imagen original) y más grande
    sh(["qemu-img", "convert", "-O", "qcow2", origen, tmp])
    sh(["qemu-img", "resize", tmp, TAMANO_DISCO])
    env_proxy = f"AGR_PROXY={args.proxy} " if args.proxy else ""
    cmd = ["virt-customize", "-a", tmp, "--network",
           "--run-command", "growpart /dev/sda 1 && resize2fs /dev/sda1 || true",
           "--root-password", f"password:{CONTRASENA_ROOT}",
           "--timezone", "Europe/Madrid",
           "--upload", f"{GUEST / 'agr-net.sh'}:/usr/local/sbin/agr-net.sh",
           "--chmod", "0755:/usr/local/sbin/agr-net.sh",
           "--upload", f"{GUEST / 'agr-net.service'}:/etc/systemd/system/agr-net.service",
           "--upload", f"{GUEST / 'ssr-server.service'}:/etc/systemd/system/ssr-server.service",
           "--upload", f"{GUEST / 'agr-info.sh'}:/etc/profile.d/agr-info.sh",
           "--upload", f"{GUEST / 'build-base.sh'}:/root/build-base.sh",
           "--run-command", f"{env_proxy}sh /root/build-base.sh",
           "--delete", "/root/build-base.sh"]
    if args.verbose:
        cmd.insert(1, "-v")
    sh(cmd)
    tmp.rename(base)
    log.info("Imagen base creada: %s", base)
    return base


def frr_conf(nombre, m, topo):
    lineas = ["frr defaults traditional",
              f"hostname {nombre.upper()}",
              "log syslog informational",
              "service integrated-vtysh-config",
              "ip forwarding",
              "!"]
    for itf in m["interfaces"]:
        red = topo["redes"][itf["red"]]
        lineas += [f"interface {itf['nombre']}",
                   f" description {red['descripcion']} {red['cidr']}",
                   "exit", "!"]
    for destino, nh in m["rutas"]:
        lineas.append(f"ip route {destino} {nh}")
    lineas += ["!", "line vty", "!", ""]
    return "\n".join(lineas)


def node_conf(nombre, idx, m):
    lineas = [f"# Generado por agr_kvm.py para {nombre}", f"role {m['rol']}"]
    for j, itf in enumerate(m["interfaces"]):
        lineas.append(f"iface {mac(idx, j)} {itf['nombre']} {itf['ip']}")
    for destino, nh in m["rutas"]:
        lineas.append(f"route {destino} {nh}")
    return "\n".join(lineas) + "\n"


def hosts_file(topo):
    lineas = ["127.0.0.1 localhost", "10.200.0.2 profesor anfitrion"]
    for nombre, m in topo["maquinas"].items():
        for itf in m["interfaces"]:
            ip = itf["ip"].split("/")[0]
            lineas.append(f"{ip} {nombre}-{itf['nombre']}" +
                          (f" {nombre}" if itf is m["interfaces"][0] else ""))
    return "\n".join(lineas) + "\n"


def ssh_pubkey():
    """Clave pública del usuario que invoca sudo, para entrar por SSH."""
    usuario = os.environ.get("SUDO_USER")
    home = Path(os.path.expanduser(f"~{usuario}")) if usuario else Path.home()
    for n in ("id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"):
        if (home / ".ssh" / n).exists():
            return home / ".ssh" / n
    return None


def crear_disco(nombre, idx, m, topo, base, args):
    disco = args.dir / f"{nombre}.qcow2"
    if disco.exists():
        disco.unlink()
    # Disco diferencial: sólo guarda los cambios respecto a la imagen base
    sh(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", base, disco])

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "node.conf").write_text(node_conf(nombre, idx, m))
        (td / "hosts").write_text(hosts_file(topo))
        cmd = ["virt-customize", "-q", "-a", disco,
               "--hostname", nombre,
               "--mkdir", "/etc/agr",
               "--upload", f"{td / 'node.conf'}:/etc/agr/node.conf",
               "--upload", f"{td / 'hosts'}:/etc/hosts"]
        if m["rol"] == "router":
            (td / "frr.conf").write_text(frr_conf(nombre, m, topo))
            cmd += ["--upload", f"{td / 'frr.conf'}:/etc/frr/frr.conf",
                    "--run-command", "chown frr:frr /etc/frr/frr.conf && systemctl enable frr.service"]
        if m["rol"] == "server":
            cmd += ["--run-command", "systemctl enable ssr-server.service"]
        clave = ssh_pubkey()
        if clave:
            cmd += ["--ssh-inject", f"root:file:{clave}"]
        sh(cmd)
    return disco


# --------------------------------------------------------------------------
# XML de libvirt
# --------------------------------------------------------------------------
def generar_xml(nombre, idx, m, topo, disco, plantilla):
    arbol = etree.parse(str(plantilla), etree.XMLParser(remove_blank_text=True))
    raiz = arbol.getroot()
    if not Path("/dev/kvm").exists():
        raiz.set("type", "qemu")

    raiz.find("name").text = dominio(nombre)
    desc = etree.SubElement(raiz, "description")
    desc.text = (f"AGR lab 3103 - {nombre.upper()} ({m['rol']}): " +
                 ", ".join(f"{i['nombre']}={i['ip']}" for i in m["interfaces"]))
    raiz.insert(1, desc)
    kib = str(m["memoria_mb"] * 1024)
    raiz.find("memory").text = kib
    raiz.find("currentMemory").text = kib
    raiz.find("vcpu").text = str(m["vcpus"])

    dev = raiz.find("devices")
    emu = dev.find("emulator")
    if not Path(emu.text).exists():
        emu.text = shutil.which("qemu-system-x86_64") or "/usr/bin/qemu-system-x86_64"
    dev.find("disk/source").set("file", str(disco))

    # Una <interface> por cada conexión, con MAC fija y nombre de tap legible
    plantilla_itf = dev.find("interface")
    pos = list(dev).index(plantilla_itf)
    dev.remove(plantilla_itf)
    for j, itf in enumerate(m["interfaces"]):
        e = etree.Element("interface", type="bridge")
        etree.SubElement(e, "mac", address=mac(idx, j))
        etree.SubElement(e, "source", bridge=topo["redes"][itf["red"]]["bridge"])
        etree.SubElement(e, "target", dev=f"{nombre}-{itf['nombre']}"[:15])
        etree.SubElement(e, "model", type="virtio")
        dev.insert(pos + j, e)

    # Canal para el agente QEMU (lo usa la orden 'probar')
    canal = etree.SubElement(dev, "channel", type="unix")
    etree.SubElement(canal, "target", type="virtio", name="org.qemu.guest_agent.0")
    # Consola VNC con teclado español
    dev.find("graphics").set("keymap", "es")
    return etree.tostring(arbol, pretty_print=True, encoding="unicode")


# --------------------------------------------------------------------------
# Órdenes
# --------------------------------------------------------------------------
def maquinas_sel(topo, args):
    sel = getattr(args, "maquinas", None) or list(topo["maquinas"])
    for n in sel:
        if n not in topo["maquinas"]:
            sys.exit(f"Máquina desconocida: {n}. Disponibles: {', '.join(topo['maquinas'])}")
    return sel


def cmd_xml(topo, args):
    """Sólo genera los XML (no necesita root)."""
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    for idx, (nombre, m) in enumerate(topo["maquinas"].items(), 1):
        xml = generar_xml(nombre, idx, m, topo, args.dir / f"{nombre}.qcow2", args.plantilla)
        (salida / f"{dominio(nombre)}.xml").write_text(xml)
        if m["rol"] == "router":
            (salida / f"{nombre}-frr.conf").write_text(frr_conf(nombre, m, topo))
        (salida / f"{nombre}-node.conf").write_text(node_conf(nombre, idx, m))
    print(f"Ficheros generados en {salida}")


def cmd_crear(topo, args):
    comprobar_entorno()
    sh(["systemctl", "start", "libvirtd"], check=False, capture=True)
    args.dir.mkdir(parents=True, exist_ok=True)
    base = imagen_base(args)
    crear_bridges(topo)
    for idx, (nombre, m) in enumerate(topo["maquinas"].items(), 1):
        if nombre not in maquinas_sel(topo, args):
            continue
        info(f"Máquina {dominio(nombre)} ({m['rol']})")
        if virsh("dominfo", dominio(nombre), check=False).returncode == 0:
            virsh("destroy", dominio(nombre), check=False)
            virsh("undefine", dominio(nombre), check=False)
        disco = crear_disco(nombre, idx, m, topo, base, args)
        xml = generar_xml(nombre, idx, m, topo, disco, args.plantilla)
        ruta_xml = args.dir / f"{dominio(nombre)}.xml"
        ruta_xml.write_text(xml)
        virsh("define", ruta_xml)
        virsh("start", dominio(nombre))
    info("Esperando a que arranquen las máquinas...")
    esperar_agentes(topo, maquinas_sel(topo, args), args.espera)
    cmd_estado(topo, args)
    print("\nSiguiente paso: sudo ./agr_kvm.py probar")


def cmd_arrancar(topo, args):
    comprobar_entorno()
    crear_bridges(topo)
    for n in maquinas_sel(topo, args):
        r = virsh("start", dominio(n), check=False)
        print(f"{dominio(n)}: {'arrancada' if r.returncode == 0 else r.stderr.strip()}")


def cmd_parar(topo, args):
    for n in maquinas_sel(topo, args):
        virsh("shutdown", dominio(n), check=False)
        print(f"{dominio(n)}: apagando")


def cmd_destruir(topo, args):
    comprobar_entorno()
    for n in maquinas_sel(topo, args):
        virsh("destroy", dominio(n), check=False)
        virsh("undefine", dominio(n), check=False)
        for f in (args.dir / f"{n}.qcow2", args.dir / f"{dominio(n)}.xml"):
            f.unlink(missing_ok=True)
        print(f"{dominio(n)}: eliminada")
    if not getattr(args, "maquinas", None):
        borrar_bridges(topo)
    if args.todo:
        shutil.rmtree(args.dir, ignore_errors=True)
        print(f"Eliminado {args.dir} (imagen base incluida)")


def cmd_estado(topo, args):
    print(f"\n{'MÁQUINA':<10}{'ESTADO':<14}{'ROL':<8}{'MEM':>6}  INTERFACES")
    for n, m in topo["maquinas"].items():
        r = virsh("domstate", dominio(n), check=False)
        estado = r.stdout.strip() if r.returncode == 0 else "no definida"
        itfs = "  ".join(f"{i['nombre']}={i['ip']}" for i in m["interfaces"])
        print(f"{n.upper():<10}{estado:<14}{m['rol']:<8}{m['memoria_mb']:>4}MB  {itfs}")


def cmd_consola(topo, args):
    for n in maquinas_sel(topo, args):
        c = ["xterm", "-T", f"Consola {n.upper()}", "-e",
             f"virsh -c qemu:///system console {dominio(n)}"]
        if shutil.which("xterm"):
            subprocess.Popen(c, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"xterm abierto para {dominio(n)} (usuario root / contraseña {CONTRASENA_ROOT}, salir: Ctrl+])")
        else:
            print(f"xterm no instalado; ejecute: sudo virsh console {dominio(n)}")


# --- Agente QEMU: ejecutar órdenes dentro de las VMs ----------------------
def qga(dom, comando, argumentos=None):
    msg = {"execute": comando}
    if argumentos is not None:
        msg["arguments"] = argumentos
    r = virsh("qemu-agent-command", dom, json.dumps(msg), check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)["return"]


def guest_exec(nombre, orden, timeout=60):
    """Ejecuta 'sh -c orden' en la VM; devuelve (código, salida)."""
    dom = dominio(nombre)
    pid = qga(dom, "guest-exec", {"path": "/bin/sh", "arg": ["-c", orden],
                                  "capture-output": True})["pid"]
    fin = time.time() + timeout
    while time.time() < fin:
        st = qga(dom, "guest-exec-status", {"pid": pid})
        if st.get("exited"):
            out = base64.b64decode(st.get("out-data", "")).decode(errors="replace")
            err = base64.b64decode(st.get("err-data", "")).decode(errors="replace")
            return st.get("exitcode", -1), out + err
        time.sleep(0.5)
    return -1, "timeout"


def esperar_agentes(topo, nombres, timeout):
    pendientes = set(nombres)
    fin = time.time() + timeout
    while pendientes and time.time() < fin:
        for n in sorted(pendientes):
            try:
                qga(dominio(n), "guest-ping")
                # agr-net.service debe haber terminado
                code, _ = guest_exec(n, "systemctl is-active agr-net.service", 10)
                if code == 0:
                    log.info("%s lista", n)
                    pendientes.discard(n)
            except RuntimeError:
                pass
        if pendientes:
            time.sleep(3)
    if pendientes:
        log.warning("No responden tras %ss: %s", timeout, ", ".join(sorted(pendientes)))


def cmd_probar(topo, args):
    """Plan de pruebas de conectividad global."""
    comprobar_entorno()
    web = topo["servicio_web"]
    url = f"http://{web['ip']}:{web['puerto']}/"
    resultados = []
    informe = []

    def anotar(origen, prueba, ok, detalle=""):
        resultados.append(ok)
        marca = "\033[32mOK  \033[0m" if ok else "\033[31mFALLO\033[0m"
        print(f"  {marca} {origen:<10} {prueba}")
        informe.append(f"[{'OK' if ok else 'FALLO'}] {origen:<10} {prueba}")
        if detalle:
            informe.append("\n".join("      " + l for l in detalle.rstrip().splitlines()))

    esperar_agentes(topo, list(topo["maquinas"]), args.espera)

    # 1. Desde el anfitrión (PC Profesor): ping a todas las interfaces y web
    print("\n1) Anfitrión (PC Profesor) -> todas las interfaces del laboratorio")
    for n, m in topo["maquinas"].items():
        for itf in m["interfaces"]:
            ip = itf["ip"].split("/")[0]
            r = sh(["ping", "-c", "2", "-W", "2", ip], check=False, capture=True)
            anotar("anfitrion", f"ping {ip:<12} ({n.upper()} {itf['nombre']})", r.returncode == 0)
    r = sh(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", url],
           check=False, capture=True)
    anotar("anfitrion", f"HTTP GET {url} -> {r.stdout}", r.stdout == "200")

    # 2. Desde cada PC de las redes inferiores: ping, web, traceroute
    pcs = [n for n, m in topo["maquinas"].items() if m["rol"] == "pc"]
    print("\n2) PCs de las redes inferiores -> servidor web")
    for n in pcs:
        c, o = guest_exec(n, f"ping -c 2 -W 2 {web['ip']}")
        anotar(n, f"ping {web['ip']}", c == 0, o if args.detalle else "")
        c, o = guest_exec(n, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 {url}")
        anotar(n, f"HTTP GET {url} -> {o.strip()}", o.strip() == "200")
        c, o = guest_exec(n, f"curl -s --max-time 5 '{url}record?id_nodo={n}&temperatura=21.5"
                             f"&humedad=40&co2=400&volatiles=10'")
        anotar(n, "HTTP GET /record (escritura de datos)", c == 0 and "Saving" in o)
        c, o = guest_exec(n, f"traceroute -n -w 1 -q 1 {web['ip']}")
        anotar(n, f"traceroute {web['ip']}", c == 0 and web["ip"] in o, o)

    # 3. Conectividad entre las redes inferiores
    print("\n3) Conectividad entre PCs de distintas redes")
    for a in pcs:
        for b in pcs:
            if a != b:
                ip = topo["maquinas"][b]["interfaces"][0]["ip"].split("/")[0]
                c, _ = guest_exec(a, f"ping -c 1 -W 2 {ip}")
                anotar(a, f"ping {ip} ({b})", c == 0)

    # 4. Tablas de enrutamiento de los routers (FRR)
    print("\n4) Tablas de enrutamiento de los routers")
    for n, m in topo["maquinas"].items():
        if m["rol"] == "router":
            c, o = guest_exec(n, "vtysh -c 'show ip route' 2>/dev/null || ip route")
            anotar(n, "tabla de rutas (vtysh -c 'show ip route')", c == 0, o)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} pruebas correctas")
    if args.informe:
        cab = [f"Plan de pruebas - {datetime.now():%Y-%m-%d %H:%M:%S}",
               f"Resultado: {ok}/{total} pruebas correctas", ""]
        Path(args.informe).write_text("\n".join(cab + informe) + "\n")
        print(f"Informe guardado en {args.informe}")
    return 0 if ok == total else 1


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description="Despliega la red del laboratorio 3103 con QEMU-KVM (AGR).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("-v", "--verbose", action="store_true", help="trazas de depuración")
    p.add_argument("--topologia", default=AQUI / "topologia.json", type=Path)
    p.add_argument("--plantilla", default=AQUI / "plantilla_vm.xml", type=Path)
    p.add_argument("--dir", default=DIR_TRABAJO, type=Path,
                   help=f"directorio de imágenes y XML (por defecto {DIR_TRABAJO})")
    sub = p.add_subparsers(dest="orden", required=True)

    s = sub.add_parser("crear", help="crea imagen base, bridges y máquinas, y las arranca")
    s.add_argument("maquinas", nargs="*", help="sólo estas máquinas (por defecto todas)")
    s.add_argument("--imagen-base", help="qcow2 de partida (p. ej. la imagen de Moodle)")
    s.add_argument("--reconstruir-base", action="store_true", help="rehace la imagen base")
    s.add_argument("--proxy", help="proxy HTTP(S) para descargar paquetes en la imagen base")
    s.add_argument("--espera", type=int, default=300, help="segundos de espera al arranque")
    s.set_defaults(func=cmd_crear)

    s = sub.add_parser("arrancar", help="arranca las máquinas (y recrea los bridges)")
    s.add_argument("maquinas", nargs="*")
    s.set_defaults(func=cmd_arrancar)

    s = sub.add_parser("parar", help="apaga las máquinas ordenadamente")
    s.add_argument("maquinas", nargs="*")
    s.set_defaults(func=cmd_parar)

    s = sub.add_parser("destruir", help="elimina máquinas, discos, bridges y rutas")
    s.add_argument("maquinas", nargs="*")
    s.add_argument("--todo", action="store_true", help="borra también la imagen base")
    s.set_defaults(func=cmd_destruir)

    s = sub.add_parser("estado", help="estado de las máquinas")
    s.set_defaults(func=cmd_estado)

    s = sub.add_parser("consola", help="abre un xterm con la consola serie")
    s.add_argument("maquinas", nargs="*")
    s.set_defaults(func=cmd_consola)

    s = sub.add_parser("probar", help="ejecuta el plan de pruebas de conectividad")
    s.add_argument("--informe", help="guarda el resultado en este fichero")
    s.add_argument("--detalle", action="store_true", help="incluye la salida de cada ping")
    s.add_argument("--espera", type=int, default=120)
    s.set_defaults(func=cmd_probar)

    s = sub.add_parser("xml", help="sólo genera XML y configuraciones (no requiere root)")
    s.add_argument("--salida", default="xml_generados")
    s.set_defaults(func=cmd_xml)

    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")
    topo = cargar_topologia(args.topologia)
    try:
        sys.exit(args.func(topo, args) or 0)
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
