# Password Guardian

Password Guardian is a desktop password manager built with a PyQt5 GUI and a Flask backend API.
It combines local database storage, account authentication, password health analytics, and optional MFA/security tooling in one project.

## What This Project Includes

- Desktop GUI for daily password management
- Flask REST API used by the GUI
- SQLAlchemy data layer (SQLite by default, MySQL supported)
- Authentication system with email verification + 2FA/TOTP support
- Security features: password strength checks, HIBP breach check, audit logs, device/session controls
- Import/export vault flows (including encrypted vault format)

## Core Features

### Password Vault
- Add, edit, view, copy, delete, and restore passwords
- Categories (personal/work/finance/study/game/custom)
- Favorites toggle
- Trash workflow with restore/permanent delete
- Search + filter by category, strength, favorites, etc.

### Security & Quality Checks
- Password strength analysis (`weak`, `medium`, `strong`)
- Strong password generation tools
- Have I Been Pwned (HIBP) lookup via k-anonymity (`/range/{prefix}`)
- Reuse/age/pwned indicators in analytics/dashboard

### Authentication & Account Security
- Registration + email verification code
- Login with optional email 2FA
- TOTP support (authenticator apps) with recovery codes
- Trusted device/session handling
- Forgot-password flow with verification code
- Edit profile (username/email/password update)

### Analytics & Monitoring
- Security dashboard cards and bars (weak/medium/strong split, risk metrics)
- Stats endpoint with security score
- Audit journal UI + backend logging for key actions
- Device/session list and revoke actions

### Import / Export
- Export vault data from backend
- Import vault data into user account
- Encrypted vault file support (`.pgvault`)
- Merge/skip/overwrite conflict modes in GUI import flow

### Auto-fill & Productivity
- Auto-open site URL from saved credential
- Auto-fill helpers (depending on available local automation environment)

## Tech Stack

- Frontend: PyQt5
- Backend: Flask + Flask-CORS
- ORM: SQLAlchemy
- Database: SQLite (default local) or MySQL (`DATABASE_URL` or legacy DB env vars)
- Security libs: `cryptography`, `pycryptodome`, `argon2-cffi`, `pyotp`

## Project Structure

```text
backend_api/                 Flask API
database/                    SQLAlchemy engine + models
src/
  auth/                      AuthManager and auth flows
  backend/                   API client used by GUI
  gui/                       Main window, components, modals, styles
  security/                  Encryption, password tools, audit utilities
tests/                       Unit tests
main.py                      Starts backend + GUI together
start_PasswordGuardian.py    Starts GUI app
```

## Setup

### 1) Create environment

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
```

### 2) Configure `.env` (recommended)

Create a `.env` in project root.

```env
# Database (optional: defaults to sqlite:///password_guardian.db)
DATABASE_URL=
# or legacy MySQL style:
DB_HOST=
DB_PORT=3306
DB_USER=
DB_PASS=
DB_NAME=

# SMTP (needed for email verification/reset/2FA mail)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_NAME=Password Guardian
SMTP_FROM_EMAIL=
SMTP_REPLY_TO=
SMTP_USE_SSL=false
SMTP_USE_STARTTLS=true
SMTP_TIMEOUT=20
```

## Running the App

### Option A: Start full app (backend + GUI)

```bash
python main.py
```

### Option B: Start GUI only

```bash
python start_PasswordGuardian.py
```

### Option C: Start backend only

```bash
python -m backend_api.app
```

Backend default URL: `http://127.0.0.1:5000`

## Key API Endpoints (high-level)

- `GET /health`
- `GET /passwords/<user_id>`
- `POST /passwords`
- `PUT /passwords/<pid>`
- `POST /passwords/<pid>/trash`
- `POST /passwords/<pid>/restore`
- `DELETE /passwords/<pid>`
- `GET /stats/<user_id>`
- `GET /profile/<user_id>`
- `PUT /profile/<user_id>`
- `GET /devices/<user_id>`
- `GET /sessions/<user_id>`
- `DELETE /sessions/<session_id>`
- `DELETE /devices/<user_id>/revoke`
- `GET /export/<user_id>`
- `POST /import/<user_id>`

## Testing

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Current tests include coverage for:
- pwned-password checks
- email sending behavior
- TOTP auth flows

## Security Notes

- Passwords are handled through the backend data layer and security helpers.
- HIBP checks use k-anonymity: only SHA1 prefix is sent, full hash remains local.
- Keep `.env`, DB files, and exported vault files private.
- Recovery codes should be stored securely offline.

## Troubleshooting

- SMTP features not working: verify `SMTP_*` values and provider rules (app passwords, TLS/SSL mode, port).
- DB issues: verify `DATABASE_URL` or delete local SQLite file and restart for clean schema.
- GUI import issues: ensure dependencies installed in the same virtual environment.
- Auto-fill limitations: behavior depends on OS permissions and installed automation dependencies.

## Development Notes

- Main UI controller: `src/gui/main_window.py`
- Dialogs and major user flows: `src/gui/components/modals.py`
- Auth layer: `src/auth/auth_manager.py`
- Security utilities: `src/security/password_tools.py`, `src/security/encryption.py`
- API bridge for GUI: `src/backend/api_client.py`

---

If you want, I can also generate:
- a short user manual (`docs/USER_GUIDE.md`)
- an API reference table with request/response examples
- a deployment README for packaging into an executable.
