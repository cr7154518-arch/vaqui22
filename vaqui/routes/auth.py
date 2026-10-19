from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db, bcrypt
from models import User, Account, Category, DEFAULT_CATEGORIES

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/registro", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("finance.dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not all([full_name, email, password]) or len(password) < 6:
            flash("Completa todos los campos. La contraseña debe tener al menos 6 caracteres.", "danger")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("Ya existe una cuenta con ese correo.", "danger")
            return redirect(url_for("auth.register"))

        user = User(
            full_name=full_name,
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
        )
        db.session.add(user)
        db.session.flush()

        # Datos iniciales: una cuenta y categorías por defecto
        db.session.add(Account(user_id=user.id, name="Efectivo", kind="cash", initial_balance=0))
        for name, ctype in DEFAULT_CATEGORIES:
            db.session.add(Category(user_id=user.id, name=name, type=ctype))
        db.session.commit()

        login_user(user)
        flash(f"¡Bienvenido, {user.full_name.split()[0]}! Empieza registrando tu primer movimiento.", "success")
        return redirect(url_for("finance.dashboard"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("finance.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            return redirect(url_for("finance.dashboard"))

        flash("Credenciales incorrectas. Intenta de nuevo.", "danger")
        return redirect(url_for("auth.login"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
