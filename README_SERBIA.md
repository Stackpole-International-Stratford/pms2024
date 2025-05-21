# PMS Project — Setup & Usage Guide

This document covers project structure, prerequisites, configuration, and both local‐ and Docker‐based setup.

---

## Table of Contents

1. [Project Overview](#project-overview)  
2. [Prerequisites](#prerequisites)  
3. [Quick Start (Local)](#quick-start-local)  
4. [Environment Variables](#environment-variables)  
5. [Database Setup](#database-setup)  
6. [LDAP Configuration](#ldap-configuration)  
7. [Docker Setup](#docker-setup)  
8. [Running the App](#running-the-app)  
9. [Admin & Debug Tools](#admin--debug-tools)  
10. [Static & Media Files](#static--media-files)  
11. [Testing](#testing)  
12. [Contributing](#contributing)  
13. [License](#license)  

---

## Project Overview

**pms** is a Django-based Process Management System that lets operators:
- Define **Form Types** (OIS, TPM, LPA, …), although for our purposes this app for now is just for LPAs.
- Dynamically create and edit **Forms** and their **Questions** (stored as JSON).
- Capture operator **Answers** (with metadata like operator number, timestamps, machine, close-out info, etc.).
- Bulk-import questions, tag expired items, “soft” delete forms via metadata, and view historical records.

Built with Django 4.1.2, Python 3.9-Alpine (via Docker), MariaDB, and LDAP for authentication.

---

## Prerequisites

- **Python 3.9+** (if running locally)  
- **MariaDB** server (10.x+)  
- **OpenLDAP** (for corporate SSO)  
- **Docker** & **docker-compose** (optional but recommended)  
- `git` (to clone / update the repo)

---

## Quick Start (Local)

1. **Clone the repo**  
   ```bash
   git clone https://your.git.host/johnsonelectric/pms.git
   cd pms
