# Genera el diagrama de red anotado con las órdenes de creación (SVG)
import sys
from xml.sax.saxutils import escape as esc

W, H = 1800, 1660
LH = 15          # alto de línea del texto monoespaciado
out = []
def add(s): out.append(s)

add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
add('''<style>
 .bg{fill:#ffffff}
 .lnk{stroke:#2a6496;stroke-width:2.4;fill:none}
 .card{fill:#ffffff;stroke-width:1.8;rx:10}
 .rtr{fill:#eef4f9;stroke:#2a6496} .srv{fill:#eff7ec;stroke:#3b7a2a}
 .pc{fill:#fff8ea;stroke:#b07a12} .hst{fill:#f5eefa;stroke:#6b3d8f}
 .mld{fill:#f4f4f4;stroke:#666} .br{fill:#2a6496;rx:14}
 .h{font:bold 15px "DejaVu Sans",Arial,sans-serif;fill:#1d1d1f}
 .s{font:bold 11px "DejaVu Sans",Arial,sans-serif;fill:#8a3b12}
 .c{font:11px "DejaVu Sans Mono",monospace;fill:#222}
 .k{font:11px "DejaVu Sans Mono",monospace;fill:#777}
 .bh{font:bold 12px "DejaVu Sans",Arial,sans-serif;fill:#fff}
 .bc{font:10.5px "DejaVu Sans Mono",monospace;fill:#e8f0f7}
 .t{font:bold 20px "DejaVu Sans",Arial,sans-serif;fill:#1d1d1f}
 .n{font:12px "DejaVu Sans",Arial,sans-serif;fill:#555}
</style>''')
add(f'<rect class="bg" width="{W}" height="{H}"/>')
add('<text class="t" x="900" y="32" text-anchor="middle">Laboratorio 3103 en KVM: cómo se creó cada enlace y cada equipo</text>')
add('<text class="n" x="900" y="52" text-anchor="middle">Órdenes del anfitrión con sudo · "Dentro" = en la consola de la VM (sudo virsh console &lt;vm&gt;, root/agr) · "a$ " = disco en /var/lib/libvirt/images/lab3103</text>')

def card(x, y, w, cls, title, lines):
    """Caja con título y líneas; las que empiezan por '#' son secciones."""
    h = 34 + LH * len(lines) + 10
    add(f'<rect class="card {cls}" x="{x}" y="{y}" width="{w}" height="{h}"/>')
    add(f'<text class="h" x="{x+12}" y="{y+22}">{esc(title)}</text>')
    yy = y + 22 + LH + 4
    for l in lines:
        if l.startswith('#'):
            add(f'<text class="s" x="{x+12}" y="{yy}">{esc(l[1:].strip())}</text>')
        else:
            add(f'<text class="c" xml:space="preserve" x="{x+12}" y="{yy}">{esc(l)}</text>')
        yy += LH
    return h

def bridge(cx, cy, name, net):
    w, h = 300, 48
    x, y = cx - w/2, cy - h/2
    add(f'<rect class="br" x="{x}" y="{y}" width="{w}" height="{h}"/>')
    add(f'<text class="bh" x="{cx}" y="{y+15}" text-anchor="middle">{esc(name)} · {esc(net)}</text>')
    add(f'<text class="bc" x="{cx}" y="{y+29}" text-anchor="middle">ip link add {name} type bridge</text>')
    add(f'<text class="bc" x="{cx}" y="{y+42}" text-anchor="middle">ip link set {name} up</text>')

def line(x1, y1, x2, y2):
    add(f'<line class="lnk" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')

def vm(name, ifs):
    """Bloque de creación común a todas las VMs."""
    return ['# Disco y definición (anfitrión)',
            f'a$ qemu-img create -f qcow2 -F qcow2 \\',
            f'       -b molde.qcow2 {name}.qcow2',
            f'xml/{name}.xml = plantilla + <name>{name}</name>',
            f'   + disco {name}.qcow2 + ' + ifs,
            f'virsh define xml/{name}.xml; virsh start {name}']

CW = 430                     # ancho de las cajas de VM
# ---- posiciones
SRV = (900, 70); RA = (900, 380); RB = (900, 760)
RC = (450, 1140); RD = (1350, 1140)
PCS = [(225, 1470), (675, 1470), (1125, 1470), (1575, 1470)]

# ---- enlaces (se dibujan primero, debajo de cajas y bridges)
line(900, 70, 900, 760)                    # SRV-RA-RB
line(1100, 470, 1360, 470)                 # RA-anfitrión
line(900, 1040, 450, 1140); line(900, 1040, 1350, 1140)
for (px, py), rx in zip(PCS, (450, 450, 1350, 1350)):
    line(rx, 1379, px, py)

# ---- cajas de VM
card(SRV[0]-CW/2, SRV[1], CW, 'srv', 'SRV · servidor web · 10.100.0.11',
     vm('srv', 'eth0→br-srv') + [
     '# Dentro',
     'hostnamectl set-hostname srv',
     'interfaces: eth0 10.100.0.11/24 gateway 10.100.0.1',
     'systemctl enable --now ssr-server   (puerto 3000)'])
card(RA[0]-CW/2, RA[1], CW, 'rtr', 'RA · router',
     vm('ra', 'eth0→br-srv') + [
     '   eth1→br-ab  eth2→br-prof',
     '# Dentro',
     'hostnamectl set-hostname ra',
     'interfaces: eth0 10.100.0.1/24  eth1 10.1.0.1/30',
     '            eth2 10.200.0.1/30',
     'echo net.ipv4.ip_forward=1 > /etc/sysctl.d/99-router.conf',
     'systemctl enable --now frr',
     'vtysh: ip route 0.0.0.0/0 10.1.0.2 · write memory'])
card(RB[0]-CW/2, RB[1]-20, CW, 'rtr', 'RB · router',
     vm('rb', 'eth0→br-ab') + [
     '   eth1→br-bc  eth2→br-bd',
     '# Dentro',
     'hostnamectl set-hostname rb',
     'interfaces: eth0 10.1.0.2/30  eth1 10.2.0.1/30',
     '            eth2 10.3.0.1/30',
     'ip_forward=1 · systemctl enable --now frr',
     'vtysh: ip route 0.0.0.0/0   10.1.0.1',
     '       ip route 10.0.1.0/24 10.2.0.2',
     '       ip route 10.0.2.0/24 10.2.0.2',
     '       ip route 10.0.3.0/24 10.3.0.2',
     '       ip route 10.0.4.0/24 10.3.0.2 · write memory'])
for (cx, cy), nm, a, b, ips, gw in (
        (RC, 'rc', 'br-red1', 'br-red2', ('10.2.0.2/30', '10.0.1.1/24', '10.0.2.1/24'), '10.2.0.1'),
        (RD, 'rd', 'br-red3', 'br-red4', ('10.3.0.2/30', '10.0.3.1/24', '10.0.4.1/24'), '10.3.0.1')):
    first = 'br-bc' if nm == 'rc' else 'br-bd'
    card(cx-CW/2, cy, CW, 'rtr', f'{nm.upper()} · router',
         vm(nm, f'eth0→{first}') + [
         f'   eth1→{a}  eth2→{b}',
         '# Dentro',
         f'hostnamectl set-hostname {nm}',
         f'interfaces: eth0 {ips[0]}  eth1 {ips[1]}',
         f'            eth2 {ips[2]}',
         'ip_forward=1 · systemctl enable --now frr',
         f'vtysh: ip route 0.0.0.0/0 {gw} · write memory'])
for i, (cx, cy) in enumerate(PCS, 1):
    card(cx-200, cy, 400, 'pc', f'PC{i} · RED {i} · 10.0.{i}.10', [
         '# Disco y definición (anfitrión)',
         f'a$ qemu-img create -f qcow2 -F qcow2 \\',
         f'       -b molde.qcow2 pc{i}.qcow2',
         f'xml/pc{i}.xml: <name>pc{i}</name>, eth0→br-red{i}',
         f'virsh define xml/pc{i}.xml; virsh start pc{i}',
         '# Dentro',
         f'hostnamectl set-hostname pc{i}',
         f'interfaces: eth0 10.0.{i}.10/24 gateway 10.0.{i}.1'])

# ---- bridges (encima de las líneas)
bridge(900, 335, 'br-srv', '10.100.0.0/24')
bridge(900, 715, 'br-ab', '10.1.0.0/30')
bridge(1230, 470, 'br-prof', '10.200.0.0/30')
bridge(560, 1104, 'br-bc', '10.2.0.0/30')
bridge(1240, 1104, 'br-bd', '10.3.0.0/30')
for (cx, cy), i in zip(PCS, range(1, 5)):
    bridge(cx, cy - 45, f'br-red{i}', f'10.0.{i}.0/24')

# ---- anfitrión
card(1360, 400, 425, 'hst', 'Anfitrión = PC Profesor · 10.200.0.2', [
     '# Preparación (parte2/red.sh, tras cada reinicio)',
     'modprobe -r vboxnetadp vboxnetflt vboxdrv',
     'modprobe kvm_amd',
     'ip link add br-… type bridge; ip link set br-… up',
     '   (los 9 bridges de este diagrama)',
     'sysctl -w net.bridge.bridge-nf-call-iptables=0',
     '# Su conexión al laboratorio',
     'ip addr add 10.200.0.2/30 dev br-prof',
     'ip route add <red> via 10.200.0.1   para:',
     '  10.100.0.0/24  10.1.0.0/30  10.2.0.0/30',
     '  10.3.0.0/30    10.0.1.0/24 … 10.0.4.0/24'])

# ---- base común
card(20, 70, 640, 'mld', 'Base común de las 9 VMs (pasos 0–3)', [
     '# Imagen de Moodle',
     'mkdir -p /var/lib/libvirt/images/lab3103',
     'cp agr-vm-base.qcow2 …/lab3103/base.qcow2; chmod 444 base.qcow2',
     '# Máquina molde (con Internet por la red NAT "default")',
     'a$ qemu-img create -f qcow2 -F qcow2 -b base.qcow2 molde.qcow2',
     "xml/molde.xml: <interface type='network'><source network='default'/>",
     'virsh net-start default; virsh define xml/molde.xml; virsh start molde',
     '# Dentro del molde',
     'apt install frr traceroute tcpdump curl git; systemctl disable --now frr',
     'NodeSource 22: apt install nodejs',
     'git clone SSR-master-server /opt/…; npm install --omit=dev',
     'ssr-server.service  (creado, sin activar)',
     'rm /etc/netplan/*.yaml; interfaces sólo con lo; truncate machine-id',
     'poweroff',
     '# Congelar',
     'virsh undefine molde; chmod 444 molde.qcow2',
     '# Cadena de discos',
     'base.qcow2 ← molde.qcow2 ← srv, ra, rb, rc, rd, pc1…pc4 .qcow2'])

# ---- plantilla
card(20, 405, 640, 'mld', 'XML de cada VM = plantilla de Moodle + 3 cambios', [
     "sed -e 's|<name>XXX</name>|<name>VM</name>|' \\",
     "    -e 's|/mnt/tmp/XXX/XXX.qcow2|/var/lib/libvirt/images/lab3103/VM.qcow2|' \\",
     "    -e 's|<source bridge=\"XXX\"/>|<source bridge=\"BRIDGE\"/>|' \\",
     '    plantilla.xml > xml/VM.xml',
     '# Varias tarjetas: un bloque <interface> por bridge, en orden (eth0, eth1…)',
     'Cambiar el XML de una VM existente:',
     '  virsh shutdown VM → undefine VM → define xml/VM.xml → start VM'])

add('</svg>')
open(sys.argv[1], 'w').write('\n'.join(out))
