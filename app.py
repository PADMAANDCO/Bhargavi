"""
Padmavati & Co - Document Vault
A web-based document management app for auditors and clients.

Features
--------
- Two roles: Admin (auditor) and Client.
- Admin can create/manage client accounts and upload documents for each
  client into a category (IT Returns, Computations, GST Returns,
  Statutory Returns, Other).
- Each client's documents are stored in an isolated folder on the server
  ("separate cloud space" per client).
- Clients log in with their own username/password and can only see and
  download their own documents.
- SQLite database stores users, clients and document metadata.

Run
---
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000 in a browser.

Default admin credentials (change after first login):
    username: admin
    password: admin123
"""

import os
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, abort, session
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, "client_vault")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt",
    "png", "jpg", "jpeg", "zip", "rar", "json", "xml",
}
MAX_CONTENT_MB = 50

CATEGORIES = [
    "IT Returns",
    "Computations",
    "GST Returns",
    "Statutory Returns",
    "Other",
]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "vault.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # "admin" or "client"
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(32))
    company = db.Column(db.String(120))
    vault_folder = db.Column(db.String(120), unique=True)  # only for clients
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    documents = db.relationship("Document", backref="client", lazy=True,
                                cascade="all, delete-orphan")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_admin(self):
        return self.role == "admin"


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category = db.Column(db.String(64), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)  # uuid + ext
    size_bytes = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(64))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.Text)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "error")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def client_vault_path(client):
    path = os.path.join(UPLOAD_ROOT, client.vault_folder)
    os.makedirs(path, exist_ok=True)
    return path


def human_size(num_bytes):
    size = float(num_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


app.jinja_env.filters["humansize"] = human_size


# ---------------------------------------------------------------------------
# Routes - public
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.is_admin
                                else "client_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.full_name}.", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes - admin
# ---------------------------------------------------------------------------

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    clients = User.query.filter_by(role="client").order_by(User.full_name).all()
    total_docs = Document.query.count()
    return render_template("admin_dashboard.html",
                           clients=clients, total_docs=total_docs)


@app.route("/admin/clients/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_client():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()

        if not username or not password or not full_name:
            flash("Username, password and full name are required.", "error")
            return render_template("create_client.html")

        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
            return render_template("create_client.html")

        folder = secure_filename(username) + "_" + uuid.uuid4().hex[:8]
        client = User(
            username=username,
            role="client",
            full_name=full_name,
            email=email,
            phone=phone,
            company=company,
            vault_folder=folder,
        )
        client.set_password(password)
        db.session.add(client)
        db.session.commit()

        os.makedirs(os.path.join(UPLOAD_ROOT, folder), exist_ok=True)
        flash(f"Client '{full_name}' created successfully.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("create_client.html")


@app.route("/admin/clients/<int:client_id>")
@login_required
@admin_required
def view_client(client_id):
    client = User.query.filter_by(id=client_id, role="client").first_or_404()
    docs_by_category = {cat: [] for cat in CATEGORIES}
    for doc in sorted(client.documents, key=lambda d: d.uploaded_at, reverse=True):
        docs_by_category.setdefault(doc.category, []).append(doc)
    return render_template("view_client.html",
                           client=client,
                           docs_by_category=docs_by_category,
                           categories=CATEGORIES)


@app.route("/admin/clients/<int:client_id>/upload", methods=["POST"])
@login_required
@admin_required
def upload_document(client_id):
    client = User.query.filter_by(id=client_id, role="client").first_or_404()
    category = request.form.get("category", "Other")
    note = request.form.get("note", "").strip()
    files = request.files.getlist("file")

    if category not in CATEGORIES:
        category = "Other"

    if not files or all(f.filename == "" for f in files):
        flash("Please choose at least one file to upload.", "error")
        return redirect(url_for("view_client", client_id=client.id))

    saved = 0
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            orig = secure_filename(f.filename)
            ext = orig.rsplit(".", 1)[1].lower()
            stored = f"{uuid.uuid4().hex}.{ext}"
            full_path = os.path.join(client_vault_path(client), stored)
            f.save(full_path)
            size = os.path.getsize(full_path)
            doc = Document(
                client_id=client.id,
                category=category,
                original_name=orig,
                stored_name=stored,
                size_bytes=size,
                uploaded_by=current_user.username,
                note=note,
            )
            db.session.add(doc)
            saved += 1
        else:
            flash(f"Skipped unsupported file: {f.filename}", "error")

    db.session.commit()
    if saved:
        flash(f"Uploaded {saved} file(s) to '{category}'.", "success")
    return redirect(url_for("view_client", client_id=client.id))


@app.route("/admin/clients/<int:client_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_client(client_id):
    client = User.query.filter_by(id=client_id, role="client").first_or_404()
    # Remove files from disk
    folder = os.path.join(UPLOAD_ROOT, client.vault_folder)
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass
        try:
            os.rmdir(folder)
        except OSError:
            pass
    db.session.delete(client)
    db.session.commit()
    flash(f"Client '{client.full_name}' removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/clients/<int:client_id>/reset", methods=["POST"])
@login_required
@admin_required
def reset_client_password(client_id):
    client = User.query.filter_by(id=client_id, role="client").first_or_404()
    new_pw = request.form.get("new_password", "").strip()
    if len(new_pw) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(url_for("view_client", client_id=client.id))
    client.set_password(new_pw)
    db.session.commit()
    flash("Password updated.", "success")
    return redirect(url_for("view_client", client_id=client.id))


@app.route("/document/<int:doc_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    client = doc.client
    path = os.path.join(client_vault_path(client), doc.stored_name)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    db.session.delete(doc)
    db.session.commit()
    flash(f"Deleted '{doc.original_name}'.", "success")
    return redirect(url_for("view_client", client_id=client.id))


# ---------------------------------------------------------------------------
# Routes - client
# ---------------------------------------------------------------------------

@app.route("/my")
@login_required
def client_dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    docs_by_category = {cat: [] for cat in CATEGORIES}
    for doc in sorted(current_user.documents, key=lambda d: d.uploaded_at, reverse=True):
        docs_by_category.setdefault(doc.category, []).append(doc)
    return render_template("client_dashboard.html",
                           docs_by_category=docs_by_category,
                           categories=CATEGORIES)


@app.route("/document/<int:doc_id>/download")
@login_required
def download_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    # A client may only download their own documents; admins may download any.
    if not current_user.is_admin and doc.client_id != current_user.id:
        abort(403)
    folder = os.path.join(UPLOAD_ROOT, doc.client.vault_folder)
    return send_from_directory(folder, doc.stored_name,
                               as_attachment=True,
                               download_name=doc.original_name)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(413)
def too_large(e):
    flash(f"File too large. Limit is {MAX_CONTENT_MB} MB.", "error")
    return redirect(request.referrer or url_for("index"))


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def bootstrap():
    """Create tables and a default admin if missing."""
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role="admin").first():
            admin = User(
                username="admin",
                role="admin",
                full_name="Padmavati & Co Admin",
                email="admin@padmavatiandco.local",
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            print("[bootstrap] Default admin created: admin / admin123")


if __name__ == "__main__":
    bootstrap()
    app.run(host="0.0.0.0", port=5000, debug=False)
