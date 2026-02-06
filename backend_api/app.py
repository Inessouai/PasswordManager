# -*- coding: utf-8 -*-
"""backend_api/app.py

Unified backend (Flask) using the shared SQLAlchemy models in /database.

Implements:
- CRUD for passwords (list/add/update/trash/restore/delete/favorite)
- Simple reveal (returns stored encrypted_password as-is; client-side decrypt if you use zero-knowledge)
- Stats endpoint (weak/medium/strong + favorites + trashed + security score)
- Profile endpoint (get/update username/email)
- Sessions + devices listing + revoke (optional, for 'pro' feel)
- Export/Import JSON (for backups / portability)
"""

from __future__ import annotations

from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from database.engine import SessionLocal, init_db
from database.models import Password, User, Session, UserDevice, ActivityLog

app = Flask(__name__)
CORS(app)
init_db()


def _log(db, user_id: int | None, action: str) -> None:
    try:
        db.add(ActivityLog(user_id=user_id or 0, action=action))
        db.commit()
    except Exception:
        db.rollback()


@app.get("/health")
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat()})


# --------------------------- PASSWORDS ---------------------------

@app.get("/passwords/<int:user_id>")
def list_passwords(user_id: int):
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Password).where(Password.user_id == user_id).order_by(Password.last_updated.desc())
        ).scalars().all()

        return jsonify([
            {
                "id": p.id,
                "user_id": p.user_id,
                "site_name": p.site_name,
                "site_url": p.site_url or "",
                "site_icon": p.site_icon or "🔒",
                "username": p.username,
                "encrypted_password": p.encrypted_password,
                "category": p.category,
                "strength": p.strength,
                "favorite": bool(p.favorite),
                "trashed_at": p.trashed_at.isoformat() if p.trashed_at else None,
                "last_updated": p.last_updated.isoformat() if p.last_updated else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ])
    finally:
        db.close()


@app.post("/passwords")
def add_password():
    data = request.get_json(force=True) or {}
    required = ["user_id", "site_name", "username", "encrypted_password"]
    miss = [k for k in required if not data.get(k)]
    if miss:
        return jsonify({"ok": False, "error": f"Missing fields: {', '.join(miss)}"}), 400

    db = SessionLocal()
    try:
        p = Password(
            user_id=int(data["user_id"]),
            site_name=str(data["site_name"]),
            site_url=str(data.get("site_url") or "") or None,
            site_icon=str(data.get("site_icon") or "🔒"),
            username=str(data["username"]),
            encrypted_password=str(data["encrypted_password"]),
            category=str(data.get("category") or "personal"),
            strength=str(data.get("strength") or "medium"),
            favorite=bool(data.get("favorite") or False),
            trashed_at=None,
        )
        db.add(p)
        db.commit()
        _log(db, p.user_id, f"password:add:{p.site_name}")
        return jsonify({"ok": True, "id": p.id})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@app.put("/passwords/<int:pid>")
def update_password(pid: int):
    data = request.get_json(force=True) or {}
    db = SessionLocal()
    try:
        p = db.get(Password, pid)
        if not p:
            return jsonify({"ok": False, "error": "Not found"}), 404

        for field in ["site_name", "site_url", "site_icon", "username", "encrypted_password", "category", "strength"]:
            if field in data and data[field] is not None:
                setattr(p, field, data[field])

        if "favorite" in data and data["favorite"] is not None:
            p.favorite = bool(data["favorite"])

        db.commit()
        _log(db, p.user_id, f"password:update:{p.site_name}")
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@app.post("/passwords/<int:pid>/trash")
def trash_password(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Password, pid)
        if not p:
            return jsonify({"ok": False, "error": "Not found"}), 404
        p.trashed_at = datetime.utcnow()
        db.commit()
        _log(db, p.user_id, f"password:trash:{p.site_name}")
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@app.post("/passwords/<int:pid>/restore")
def restore_password(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Password, pid)
        if not p:
            return jsonify({"ok": False, "error": "Not found"}), 404
        p.trashed_at = None
        db.commit()
        _log(db, p.user_id, f"password:restore:{p.site_name}")
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@app.delete("/passwords/<int:pid>")
def delete_password(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Password, pid)
        if not p:
            return jsonify({"ok": False, "error": "Not found"}), 404
        uid = p.user_id
        name = p.site_name
        db.delete(p)
        db.commit()
        _log(db, uid, f"password:delete:{name}")
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@app.get("/passwords/<int:pid>/reveal")
def reveal_password(pid: int):
    """Return encrypted_password as stored (server never decrypts)."""
    db = SessionLocal()
    try:
        p = db.get(Password, pid)
        if not p:
            return jsonify({"ok": False, "error": "Not found"}), 404
        _log(db, p.user_id, f"password:reveal:{p.site_name}")
        return jsonify({"ok": True, "encrypted_password": p.encrypted_password})
    finally:
        db.close()


@app.post("/passwords/<int:pid>/favorite")
def toggle_favorite(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Password, pid)
        if not p:
            return jsonify({"ok": False, "error": "Not found"}), 404
        p.favorite = not bool(p.favorite)
        db.commit()
        _log(db, p.user_id, f"password:favorite:{p.site_name}:{int(p.favorite)}")
        return jsonify({"ok": True, "favorite": bool(p.favorite)})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


# --------------------------- STATS / DASHBOARD ---------------------------

@app.get("/stats/<int:user_id>")
def stats(user_id: int):
    db = SessionLocal()
    try:
        rows = db.execute(select(Password).where(Password.user_id == user_id)).scalars().all()
        total = len(rows)
        weak = sum(1 for p in rows if (p.strength or "").lower() == "weak")
        medium = sum(1 for p in rows if (p.strength or "").lower() == "medium")
        strong = sum(1 for p in rows if (p.strength or "").lower() == "strong")
        favorites = sum(1 for p in rows if p.favorite)
        trashed = sum(1 for p in rows if p.trashed_at is not None)

        # simple score: strong=2, medium=1, weak=0 (ignore trashed)
        active = [p for p in rows if p.trashed_at is None]
        denom = max(1, len(active) * 2)
        score = int(100 * (sum(2 if (p.strength or "").lower()=="strong" else 1 if (p.strength or "").lower()=="medium" else 0 for p in active) / denom))

        return jsonify({
            "ok": True,
            "total": total,
            "active": len(active),
            "weak": weak,
            "medium": medium,
            "strong": strong,
            "favorites": favorites,
            "trashed": trashed,
            "score": score,
        })
    finally:
        db.close()


# --------------------------- PROFILE ---------------------------

@app.get("/profile/<int:user_id>")
def get_profile(user_id: int):
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if not u:
            return jsonify({"ok": False, "error": "Not found"}), 404
        return jsonify({"ok": True, "user": {"id": u.id, "username": u.username, "email": u.email}})
    finally:
        db.close()


@app.put("/profile/<int:user_id>")
def update_profile(user_id: int):
    data = request.get_json(force=True) or {}
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if not u:
            return jsonify({"ok": False, "error": "Not found"}), 404

        if "username" in data and data["username"]:
            u.username = str(data["username"]).strip()
        if "email" in data and data["email"]:
            u.email = str(data["email"]).strip()

        db.commit()
        _log(db, u.id, "profile:update")
        return jsonify({"ok": True})
    except IntegrityError:
        db.rollback()
        return jsonify({"ok": False, "error": "Email already used"}), 400
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


# --------------------------- DEVICES / SESSIONS ---------------------------

@app.get("/devices/<int:user_id>")
def list_devices(user_id: int):
    db = SessionLocal()
    try:
        devs = db.execute(select(UserDevice).where(UserDevice.user_id == user_id).order_by(UserDevice.last_used.desc())).scalars().all()
        return jsonify({"ok": True, "devices": [
            {
                "id": d.id,
                "device_name": d.device_name,
                "ip_address": d.ip_address,
                "last_used": d.last_used.isoformat() if d.last_used else None,
            } for d in devs
        ]})
    finally:
        db.close()


@app.get("/sessions/<int:user_id>")
def list_sessions(user_id: int):
    db = SessionLocal()
    try:
        sess = db.execute(select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())).scalars().all()
        return jsonify({"ok": True, "sessions": [
            {
                "id": s.id,
                "device_info": s.device_info or "",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            } for s in sess
        ]})
    finally:
        db.close()


@app.delete("/sessions/<int:session_id>")
def revoke_session(session_id: int):
    db = SessionLocal()
    try:
        s = db.get(Session, session_id)
        if not s:
            return jsonify({"ok": False, "error": "Not found"}), 404
        uid = s.user_id
        db.delete(s)
        db.commit()
        _log(db, uid, f"session:revoke:{session_id}")
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@app.delete("/devices/<int:user_id>/revoke")
def revoke_device_sessions(user_id: int):
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        device_name = (data.get("device_name") or "").strip()
        if not device_name:
            return jsonify({"ok": False, "error": "device_name required"}), 400
        sess = db.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.device_info == device_name
            )
        ).scalars().all()
        count = len(sess)
        for s in sess:
            db.delete(s)
        db.commit()
        _log(db, user_id, f"session:revoke_device:{device_name}:{count}")
        return jsonify({"ok": True, "revoked": count})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


# --------------------------- EXPORT / IMPORT ---------------------------

@app.get("/export/<int:user_id>")
def export_vault(user_id: int):
    """Export JSON. Recommend encrypting client-side before saving to disk."""
    db = SessionLocal()
    try:
        rows = db.execute(select(Password).where(Password.user_id == user_id)).scalars().all()
        payload = {
            "version": 1,
            "exported_at": datetime.utcnow().isoformat(),
            "passwords": [
                {
                    "site_name": p.site_name,
                    "site_url": p.site_url or "",
                    "site_icon": p.site_icon or "🔒",
                    "username": p.username,
                    "encrypted_password": p.encrypted_password,
                    "category": p.category,
                    "strength": p.strength,
                    "favorite": bool(p.favorite),
                    "trashed_at": p.trashed_at.isoformat() if p.trashed_at else None,
                    "last_updated": p.last_updated.isoformat() if p.last_updated else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in rows
            ],
        }
        _log(db, user_id, "vault:export")
        return jsonify({"ok": True, "vault": payload})
    finally:
        db.close()


@app.post("/import/<int:user_id>")
def import_vault(user_id: int):
    data = request.get_json(force=True) or {}
    vault = data.get("vault") or {}
    items = vault.get("passwords") or []
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "Invalid vault format"}), 400

    db = SessionLocal()
    try:
        imported = 0
        for it in items:
            if not it.get("site_name") or not it.get("username") or not it.get("encrypted_password"):
                continue
            p = Password(
                user_id=user_id,
                site_name=str(it.get("site_name")),
                site_url=str(it.get("site_url") or "") or None,
                site_icon=str(it.get("site_icon") or "🔒"),
                username=str(it.get("username")),
                encrypted_password=str(it.get("encrypted_password")),
                category=str(it.get("category") or "personal"),
                strength=str(it.get("strength") or "medium"),
                favorite=bool(it.get("favorite") or False),
                trashed_at=None,
            )
            db.add(p)
            imported += 1
        db.commit()
        _log(db, user_id, f"vault:import:{imported}")
        return jsonify({"ok": True, "imported": imported})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


if __name__ == "__main__":
    # Always bind localhost for safety
    app.run(host="127.0.0.1", port=5000, debug=True)
