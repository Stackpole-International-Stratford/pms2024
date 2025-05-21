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
- **OpenLDAP** (for corporate SSO)  
- **Docker** & **docker-compose**
- `git` (to clone / update the repo)

---

## Quick Start (Local)

1. **Clone the repo**  
   ```bash
   git clone https://your.git.host/johnsonelectric/pms.git
   cd pms


2. **Create & activate virtual environment**  
   ```bash
    python3.9 -m venv venv
    source venv/bin/activate

3. **Install Python dependencies**
    '''bash
    pip install --upgrade pip
    pip install -r requirements.txt



4. **Configure environment**
Copy .env.example to .env and fill in your values (see Environment Variables).

5. **Run migrations & collect static**
    '''bash
    python manage.py migrate
    python manage.py collectstatic --no-input


6. **Start development server**
python manage.py runserver 0.0.0.0:8000


## Environment Variables

| Name                      | Description                           | Default                |
|---------------------------|---------------------------------------|------------------------|
| `SECRET_KEY`              | Django secret key                     | `changeme`             |
| `DB_PMS_NAME`             | MySQL database name                   | `django_pms`           |
| `DB_PMS_USER`             | MySQL user                            | `muser`                |
| `DB_PMS_PASSWORD`         | MySQL password                        | `wsj.231.kql`          |
| `DB_PMS_HOST`             | MySQL host IP                         | `10.4.1.245`           |
| `DB_PMS_PORT`             | MySQL port                            | `6601`                 |
| `ALLOWED_HOSTS`           | Comma-separated allowed hosts         | `pmdsdata12, ...`      |
| `AUTH_LDAP_SERVER_URI`    | LDAP server URI                       | `ldap://10.4.131.200`  |
| `AUTH_LDAP_BIND_DN`       | *(Optional)* LDAP bind DN             | *(empty)*              |
| `AUTH_LDAP_BIND_PASSWORD` | *(Optional)* LDAP bind password       | *(empty)*              |

**Tip:** the settings file also reads `ALLOWED_HOSTS_ENV` to extend `ALLOWED_HOSTS` at runtime.


## Database Setup

Ensure your DB server is running and accessible.

Create the database and grant privileges:

<!-- 
```sql
    CREATE DATABASE django_pms;
    CREATE USER 'username'@'%' IDENTIFIED BY 'pwd';
    GRANT ALL PRIVILEGES ON django_pms.* TO 'muser'@'%';
    FLUSH PRIVILEGES; -->




## LDAP Configuration

- **Primary server URI:** `ldap://10.4.131.200`  
- **User DN template:** `{user}@johnsonelectric.com`  
- **Base DN:** `DC=JEHLI,DC=INTERNAL`  

> If your AD is locked down, set `AUTH_LDAP_BIND_DN` and `AUTH_LDAP_BIND_PASSWORD`.



## Docker Setup

### Build the Image

```bash
docker build -t pms-app .



Run a Container
docker run -d \
  --name pms \
  --restart unless-stopped \
  -p 8000:8000 \
  -e SECRET_KEY="your-secret" \
  -e DB_PMS_HOST="db.host" \
  # Add other environment variables as needed
  pms-app
