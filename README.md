# AGR – Práctica 2: Virtualización de servicios web con Vagrant

`Vagrantfile` despliega una VM Ubuntu 22.04 (VirtualBox) que instala Node.js,
clona [SSR-master-server](https://github.com/gisai/SSR-master-server) y lo
ejecuta como servicio `systemd` en el puerto **3000** de la VM, accesible desde
el anfitrión/exterior en el puerto **8080**.

| Elemento | Valor |
|---|---|
| Box | `bento/ubuntu-22.04` |
| Hostname / nombre VM | `agr-nodeserver` |
| Recursos | 1 CPU (tope 80 %), 1024 MB RAM (`VM_CPUS`, `VM_MEMORY`) |
| NIC 1 | NAT (salida a Internet) + port forwarding `host:8080 → guest:3000` |
| NIC 2 | host-only `192.168.56.10` (servicio web) |
| NIC 3 | host-only `192.168.57.10` (gestión) |
| NIC 4 (opcional) | bridge/pública por DHCP: `BRIDGE_IF=<interfaz> vagrant up` |
| Teclado / locale / TZ | `es` / `es_ES.UTF-8` / `Europe/Madrid` |
| Servicio | `ssr-server.service` (usuario `nodeapp`, `/opt/ssr-master-server`) |
| Firewall | `ufw`: solo 22/tcp y 3000/tcp |
| Login | `/etc/profile.d/99-servidor-info.sh` imprime la configuración |

## 1. Instalación en Ubuntu 22.04 (anfitrión)

Comprobar que la virtualización está activada en la BIOS:

```bash
egrep -c '(vmx|svm)' /proc/cpuinfo   # > 0
```

### VirtualBox (repositorio oficial de Oracle)

```bash
sudo apt update && sudo apt install -y wget gpg build-essential dkms linux-headers-$(uname -r)
wget -O- https://www.virtualbox.org/download/oracle_vbox_2016.asc \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/oracle-virtualbox-2016.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/oracle-virtualbox-2016.gpg] https://download.virtualbox.org/virtualbox/debian $(lsb_release -cs) contrib" \
  | sudo tee /etc/apt/sources.list.d/virtualbox.list
sudo apt update
sudo apt install -y virtualbox-7.1
sudo usermod -aG vboxusers $USER     # cerrar sesión y volver a entrar
VBoxManage --version
```

> Alternativa más simple (VirtualBox 6.1 de Ubuntu): `sudo apt install virtualbox`.
>
> Si `sudo /sbin/vboxconfig` falla por **Secure Boot**, desactívalo en la BIOS o
> firma los módulos (`sudo mokutil --import ...`).
> Si al arrancar sale `VERR_VMX_IN_VMX_ROOT_MODE`, KVM está ocupando VT-x:
> `sudo modprobe -r kvm_intel kvm` (o `kvm_amd`) mientras uses VirtualBox.

### Vagrant (repositorio oficial de HashiCorp)

```bash
wget -O- https://apt.releases.hashicorp.com/gpg \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y vagrant
vagrant --version
```

> Si `vagrant up` dice que la versión de VirtualBox no está soportada, instala
> la última versión de Vagrant o una versión de VirtualBox anterior.

## 2. Desplegar la VM

```bash
git clone <este repositorio> && cd AGR
vagrant up            # descarga la box, crea la VM y la aprovisiona
vagrant ssh           # al entrar se imprime la configuración del servidor
```

Comprobaciones:

```bash
# Dentro de la VM
curl http://localhost:3000
# Desde el anfitrión
curl http://localhost:8080
curl http://192.168.56.10:3000
curl "http://localhost:8080/record?id_nodo=n1&temperatura=24.5&humedad=60&co2=300&volatiles=100"
# Desde otro PC de la LAN
curl http://<IP-del-anfitrión>:8080
```

Otros comandos: `vagrant status`, `vagrant provision`, `vagrant reload`,
`vagrant halt`, `vagrant destroy -f`. Con `VM_GUI=true vagrant up` se abre la
ventana de VirtualBox (usuario/contraseña `vagrant`/`vagrant`, teclado español).

## 3. Consumo de recursos

```bash
VBoxManage list runningvms
VBoxManage metrics setup --period 1 --samples 1 agr-nodeserver
VBoxManage metrics query agr-nodeserver CPU/Load,RAM/Usage
top -p $(pgrep -f VBoxHeadless)
watch "ls -al ~/VirtualBox\ VMs/agr-nodeserver/"
```

Resultados y análisis: [`docs/consumo.md`](docs/consumo.md).

## Nota sobre el servidor

`app.js` ya llama a `app.listen(3000)` y `bin/www` vuelve a escuchar en el
3000, por lo que `npm start` falla con `EADDRINUSE`. Por eso el servicio
ejecuta `node app.js` directamente.
