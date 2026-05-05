# Runbook — Harbor Container Registry Installation
# Target: apac-plm-ops.srxglobal.local (Ubuntu 24.04 LTS, VMware)
# Owner: Infrastructure (Manal) + Lead Engineer (hsalazar)
# Last updated: 2026-05-04

---

## Overview

Harbor is the self-hosted container registry for the OSKAR platform. It runs on the OSKAR
Linux VM alongside the OSKAR Docker Compose stack. All OSKAR container images are pushed to
and pulled from `apac-plm-ops.srxglobal.local`.

**Harbor version:** 2.11.x (offline installer)
**Registry URL:** `apac-plm-ops.srxglobal.local`
**Data volume:** `/data/harbor`
**Config:** `/opt/harbor/harbor.yml`
**TLS certs:** `/etc/harbor/certs/`

---

## Prerequisites

- Ubuntu 24.04 LTS VM with sudo access
- Static IP assigned and DNS record `apac-plm-ops.srxglobal.local` → VM IP added by Manal
- Ports 80 and 443 open on the VM firewall

---

## 1. Install Docker Engine

Use Docker's official install script — handles Ubuntu 24.04 correctly and installs the
Compose plugin in one step:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

Verify:

```bash
docker compose version   # must be v2.x
```

> **Do not use `apt install docker.io`** — Ubuntu's default repo does not include
> `docker-compose-plugin`. Only Docker's own apt repo has it.

---

## 2. Generate TLS Certificates

Harbor requires HTTPS. Generate a self-signed cert for `apac-plm-ops.srxglobal.local`.
Replace `<VM-IP>` with the actual static IP of the VM.

```bash
sudo mkdir -p /etc/harbor/certs
cd /etc/harbor/certs

# Generate CA key and certificate
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -sha512 -days 3650 \
  -subj "/C=AU/ST=Victoria/L=Melbourne/O=Scanfil APAC/CN=apac-plm-ops.srxglobal.local" \
  -key ca.key -out ca.crt

# Generate server key and CSR
openssl genrsa -out apac-plm-ops.srxglobal.local.key 4096
openssl req -sha512 -new \
  -subj "/C=AU/ST=Victoria/L=Melbourne/O=Scanfil APAC/CN=apac-plm-ops.srxglobal.local" \
  -key apac-plm-ops.srxglobal.local.key \
  -out apac-plm-ops.srxglobal.local.csr

# Write SAN extension file — tee required (sudo redirect won't work — see Troubleshooting)
sudo tee /etc/harbor/certs/v3.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1=apac-plm-ops.srxglobal.local
DNS.2=apac-plm-ops
IP.1=<VM-IP>
EOF

# Sign the certificate
openssl x509 -req -sha512 -days 3650 \
  -extfile v3.ext \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -in apac-plm-ops.srxglobal.local.csr \
  -out apac-plm-ops.srxglobal.local.crt
```

### Trust the cert so Docker can push/pull

```bash
sudo mkdir -p /etc/docker/certs.d/apac-plm-ops.srxglobal.local
sudo cp /etc/harbor/certs/ca.crt \
  /etc/docker/certs.d/apac-plm-ops.srxglobal.local/ca.crt
sudo systemctl restart docker
```

Distribute `ca.crt` to any other machine that will push images (dev machines, SRXWEBAPP1).

---

## 3. Download Harbor Offline Installer

```bash
cd /tmp
HARBOR_VERSION=v2.11.1
wget https://github.com/goharbor/harbor/releases/download/${HARBOR_VERSION}/harbor-offline-installer-${HARBOR_VERSION}.tgz
tar xzvf harbor-offline-installer-${HARBOR_VERSION}.tgz
sudo mv harbor /opt/harbor
```

---

## 4. Configure harbor.yml

```bash
cd /opt/harbor
sudo cp harbor.yml.tmpl harbor.yml
sudo nano harbor.yml
```

Required changes:

```yaml
hostname: apac-plm-ops.srxglobal.local

https:
  port: 443
  certificate: /etc/harbor/certs/apac-plm-ops.srxglobal.local.crt
  private_key: /etc/harbor/certs/apac-plm-ops.srxglobal.local.key

harbor_admin_password: '<strong-password>'   # must be quoted — see Troubleshooting

database:
  password: '<strong-db-password>'

data_volume: /data/harbor
```

Generate safe passwords (no YAML-special characters):

```bash
openssl rand -base64 32 | tr -d '/+=' | cut -c1-32
```

---

## 5. Run the Installer

```bash
sudo mkdir -p /data/harbor
cd /opt/harbor
sudo ./install.sh
```

Expected final output:

```
✔ ----Harbor has been installed and started successfully.----
```

The `RX variable is not set` warning is harmless — ignore it.

---

## 6. Verify

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

All 10 containers should show `Up`:
`harbor-log`, `registry`, `harbor-portal`, `redis`, `registryctl`,
`harbor-db`, `harbor-core`, `nginx`, `harbor-jobservice`, `harbor-proxy`

---

## 7. First Login and Password Change

```bash
docker login apac-plm-ops.srxglobal.local
# Username: admin
# Password: <harbor_admin_password from harbor.yml>
```

Immediately change the password via the UI:
`https://apac-plm-ops.srxglobal.local` → avatar (top right) → **Change Password**

Store the final password in `/etc/oskar/secrets.env`.

---

## 8. Create the OSKAR Project

```bash
curl -u admin:<password> -k \
  -X POST https://apac-plm-ops.srxglobal.local/api/v2.0/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name":"oskar","public":false}'
```

Image tags will be: `apac-plm-ops.srxglobal.local/oskar/oskar-app:latest`

Update `REGISTRY` in `/etc/oskar/secrets.env`:

```bash
REGISTRY=apac-plm-ops.srxglobal.local/oskar
```

---

## 9. Enable Auto-Start on Reboot

```bash
sudo tee /etc/systemd/system/harbor.service <<EOF
[Unit]
Description=Harbor Registry
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/harbor
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable harbor
```

---

## 10. Push OSKAR Images

Once Harbor is up and the project exists:

```bash
cd /opt/oskar
REGISTRY=apac-plm-ops.srxglobal.local/oskar ./scripts/push-image.sh latest
```

---

## Troubleshooting

### T-01 — `docker-compose-plugin`: unable to locate package

**Symptom:** `apt install docker-compose-plugin` fails with "unable to locate package"

**Cause:** Ubuntu 24.04's default apt repo does not include Docker's compose plugin.
Only Docker's own apt repo has it.

**Fix:** Use Docker's official install script which adds the correct repo automatically:
```bash
curl -fsSL https://get.docker.com | sudo sh
```

---

### T-02 — `sudo cat > file` fails with Permission denied

**Symptom:** Running `sudo cat > /etc/harbor/certs/v3.ext <<EOF` returns Permission denied

**Cause:** `sudo` elevates the `cat` command only. The shell redirection (`>`) runs as
the current user who does not have write access to the target directory. The redirect
happens before sudo takes effect.

**Fix:** Use `tee` instead — it is the command being elevated:
```bash
sudo tee /etc/harbor/certs/v3.ext <<EOF
...content...
EOF
```

---

### T-03 — `./install.sh` fails: `yaml.scanner.ScannerError: found character '@'`

**Symptom:** Harbor installer exits with a YAML parse error on `harbor.yml` pointing to `@`

**Cause:** YAML treats `@` as a special character when it starts an unquoted value.
Passwords containing `@` (and other special chars: `: # { } [ ] , & * ? | > ! %`)
must be quoted.

**Fix:** Wrap the password in single quotes in `harbor.yml`:
```yaml
harbor_admin_password: 'your@password'
```

**Best practice:** Generate passwords without special characters to avoid this entirely:
```bash
openssl rand -base64 32 | tr -d '/+=' | cut -c1-32
```

---

### T-04 — `./install.sh` fails: `Please specify hostname`

**Symptom:** Harbor installer exits at config validation with "Please specify hostname"

**Cause:** The `hostname` field in `harbor.yml` is blank or still set to the template
placeholder value.

**Fix:** Set the hostname explicitly in `harbor.yml`:
```yaml
hostname: apac-plm-ops.srxglobal.local
```

---

### T-05 — `docker login` fails: `dial tcp: lookup apac-plm-ops.srxglobal.local: Temporary failure in name resolution`

**Symptom:** Docker cannot resolve the Harbor hostname

**Cause:** DNS record for `apac-plm-ops.srxglobal.local` does not exist yet.

**Immediate fix** (on the VM itself):
```bash
# Find the VM IP
ip addr show | grep 'inet ' | grep -v 127.0.0.1

sudo tee -a /etc/hosts <<EOF
<VM-IP>    apac-plm-ops.srxglobal.local
EOF
```

**Permanent fix:** Ask Manal to add an A record in DNS:
```
apac-plm-ops.srxglobal.local  →  <VM-IP>
```

The `/etc/hosts` entry only works on the VM itself. Every other machine (dev, SRXWEBAPP1)
needs the DNS record or its own `/etc/hosts` entry.

---

### T-06 — `docker login` fails: `unauthorized`

**Symptom:** Hostname resolves correctly but login returns `unauthorized`

**Cause:** Password entered does not match what is stored in Harbor's database.
Harbor only reads `harbor_admin_password` from `harbor.yml` on **first install** —
subsequent restarts do not re-apply it.

**Diagnosis:** Check the password hash format in use:
```bash
docker exec -it harbor-db psql -U postgres -d registry
SELECT username, password_version, salt FROM harbor_user WHERE username='admin';
```

**Fix for SHA-256 with empty salt** (confirmed on this installation):
```bash
# Generate hash in shell
echo -n 'Harbor12345' | sha256sum | awk '{print $1}'
```

Then in psql:
```sql
UPDATE harbor_user
SET password='<hash-from-above>'
WHERE username='admin';
```

Then log in with `Harbor12345` and immediately change the password via the UI.

**Note:** Harbor cannot store passwords in plain text — only the hash is stored.
You cannot retrieve the original password, only reset it.

---

### T-07 — MD5 password reset has no effect (still unauthorized)

**Symptom:** After updating the `password` column with an MD5 hash, login still fails

**Cause:** This Harbor version uses SHA-256 (not MD5 and not bcrypt). An MD5 hash
will never match.

**Fix:** Verify `password_version` with:
```sql
SELECT password_version FROM harbor_user WHERE username='admin';
```
Then use the matching hash algorithm. See T-06 for the SHA-256 reset procedure.

---

## Post-Installation Checklist

- [ ] All 10 Harbor containers showing `Up` (`docker ps`)
- [ ] `docker login apac-plm-ops.srxglobal.local` succeeds
- [ ] Admin password changed via UI from the install default
- [ ] New password stored in `/etc/oskar/secrets.env`
- [ ] `oskar` project created in Harbor (private)
- [ ] `ca.crt` distributed to dev machines and SRXWEBAPP1
- [ ] DNS A record added by Manal
- [ ] `harbor.service` systemd unit enabled (`systemctl is-enabled harbor`)
- [ ] Harbor UI accessible at `https://apac-plm-ops.srxglobal.local`
