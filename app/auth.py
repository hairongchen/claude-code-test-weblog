from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from .extensions import db
from .models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("blog.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        errors = []
        if not username or len(username) < 2:
            errors.append("Username must be at least 2 characters.")
        if not email or "@" not in email:
            errors.append("A valid email is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if User.query.filter_by(username=username).first():
            errors.append("Username already taken.")
        if User.query.filter_by(email=email).first():
            errors.append("Email already registered.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html", username=username, email=email)

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("blog.index"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user is None or not user.check_password(password):
            flash("Invalid username/email or password.", "error")
            return render_template("auth/login.html", identifier=identifier)

        login_user(user, remember=remember)
        next_page = request.args.get("next")
        return redirect(next_page or url_for("blog.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("blog.index"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_new_password", "")

        errors = []
        if not current_user.check_password(current_password):
            errors.append("Current password is incorrect.")
        if len(new_password) < 6:
            errors.append("New password must be at least 6 characters.")
        if new_password != confirm:
            errors.append("New passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/settings.html")

        current_user.set_password(new_password)
        db.session.commit()
        flash("Password updated successfully.", "success")
        return redirect(url_for("auth.settings"))

    return render_template("auth/settings.html")
