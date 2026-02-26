# Hack The Box — Writeups

![HTB](https://img.shields.io/badge/Hack%20The%20Box-Writeups-9FEF00?style=flat&logo=hackthebox&logoColor=black)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat)
![Difficulty](https://img.shields.io/badge/Organized%20By-Difficulty-blue?style=flat)
![License](https://img.shields.io/badge/License-MIT-lightgrey?style=flat)

---

## Overview

This repository contains structured writeups for challenges from Hack The Box, including Machines and Academy labs.

The objective is to document methodology, tooling, exploitation paths, and privilege escalation techniques in a clear and reproducible format. Writeups emphasize analytical workflow rather than step-by-step solutions, and are designed to reflect real-world penetration testing practices.

All content is based on retired machines or authorized lab environments and is intended strictly for educational purposes.

---

## Repository Structure

```
HTB-writeups/
│
├── machines/
│   ├── starting-point/
│   ├── easy/
│   ├── medium/
│   ├── hard/
│   └── insane/
│
└──academy/
    └── module-name/
```

- **machines/** — Individual machine writeups categorized by official HTB difficulty
- **academy/** — Academy module labs and exercises
- **templates/** — Standardized writeup templates for consistency

Each machine directory typically includes enumeration notes, service analysis, exploitation steps, privilege escalation path, lessons learned, and supporting screenshots where relevant.

---

## Methodology

Writeups follow a structured offensive security workflow:

- Reconnaissance and service enumeration
- Attack surface analysis
- Exploitation and initial access
- Post-exploitation and privilege escalation
- Defensive considerations and remediation notes

The goal is to build disciplined documentation habits aligned with real-world penetration testing practices.

---

## Difficulty Classification

Machines are organized according to their official Hack The Box difficulty rating:

| Level | Description |
|---|---|
| Starting Point | Guided introductory machines |
| Easy | Fundamental exploitation techniques |
| Medium | Chained vulnerabilities and deeper enumeration |
| Hard | Complex attack paths and custom exploitation |
| Insane | Advanced techniques requiring deep specialization |

---

## Completed Machines

| Machine | Difficulty | OS |
|---|---|---|
| Cap | Easy | Linux |
| Facts | Easy | Linux |
| WingData | Easy | Linux |
| Expressway | Easy | Linux |
| Conversor | Easy | Linux |
| MonitorsFour | Easy | Windows |


---

## Tools Frequently Referenced

Nmap, Gobuster, Feroxbuster, Burp Suite, Metasploit, LinPEAS, WinPEAS, BloodHound, Impacket, CrackMapExec, Evil-WinRM.

Tool usage is documented with context and rationale rather than default command execution.

---

## Disclaimer

This repository is for educational purposes only. All techniques described here must be used exclusively in environments where explicit authorization has been granted. Unauthorized testing against systems is illegal and unethical. All machines covered are retired or part of authorized lab environments provided by Hack The Box.

---

## License

This repository is licensed under the [MIT License](https://opensource.org/licenses/MIT).

You are free to use, copy, modify, and distribute this content, provided the original author is credited.\
