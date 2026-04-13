# Padmavati & Co — Document Vault

A simple, secure web app for auditors to share per-client documents
(IT Returns, Computations, GST Returns, Statutory Returns, etc.) with
their clients. Each client gets their own login and can only see their
own documents.

## Features

- **Single web login** for auditors (admins) and clients.
- **Per-client isolated vault** — each client's files are stored in a
  dedicated folder and are downloadable only by that client.
- **Document categories**: IT Returns, Computations, GST Returns,
  Statutory Returns, Other.
- **Admin tools**: create clients, upload one or many files at a time,
  reset a client's password, delete documents/clients.
- **Client view**: clean dashboard grouped by category with one-click
  download.
- **Tech**: Python + Flask + SQLite + Flask-Login. Zero external
  services required.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open in a browser
#    http://localhost:5000
```

On first run the app creates:

- `vault.db`       — SQLite database (users, documents).
- `client_vault/`  — top-level folder that holds one sub-folder per
  client. This is the "separate cloud space" for each client.
- A default admin account:

      username: admin
      password: admin123

**Change the admin password immediately** (log in, then the admin can
create a new admin user via the database or by editing the script).

## How it maps to your requirement

| Requirement                                             | In the app                                                    |
| ------------------------------------------------------- | ------------------------------------------------------------- |
| Auditors upload docs (IT, GST, Statutory, etc.)         | Admin → Open client vault → choose category → upload          |
| Each client has a separate "cloud" space                | `client_vault/<client>_xxxx/` folder, isolated & per-client   |
| Client accesses using their username                    | Client logs in at `/login`, sees only their own docs          |
| Web login                                               | `/login` route, Flask-Login session based auth                |

## Deploying to the Web

For a production deployment, run behind a proper WSGI server (gunicorn
or waitress) and put it behind HTTPS (nginx / Caddy / your hosting
platform). Recommended environment variables:

```bash
export SECRET_KEY="a-long-random-string"
gunicorn -w 3 -b 0.0.0.0:5000 app:app
```

You can host this on any VPS, on AWS (EC2 / Elastic Beanstalk),
DigitalOcean App Platform, Render, Railway, PythonAnywhere, Heroku-like
platforms, or an in-office server. The app is self-contained; just
point a domain at it and enable HTTPS.

## Security Notes

- Passwords are hashed with Werkzeug's PBKDF2.
- File access is authorized on every download (admin can access all,
  client only their own).
- File extensions are whitelisted (pdf, doc/x, xls/x, csv, txt, images,
  zip). Change `ALLOWED_EXTENSIONS` in `app.py` as needed.
- Max upload size is 50 MB per request (`MAX_CONTENT_MB`).
- `vault.db` and `client_vault/` should be excluded from git and backed
  up regularly.

## Files

```
app.py                  # Flask application
requirements.txt        # Python dependencies
templates/              # Jinja2 HTML templates
  base.html
  login.html
  admin_dashboard.html
  create_client.html
  view_client.html
  client_dashboard.html
static/style.css        # Styling (matches Padmavati & Co brand colors)
```
