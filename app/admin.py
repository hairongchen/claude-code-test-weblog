from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from .extensions import db
from .models import User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@admin_bp.route("/users")
@login_required
def user_list():
    _require_admin()
    users = User.query.order_by(User.id).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/user/<int:user_id>/reset-password", methods=["GET", "POST"])
@login_required
def reset_password(user_id):
    _require_admin()
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_new_password", "")

        errors = []
        if len(new_password) < 6:
            errors.append("Password must be at least 6 characters.")
        if new_password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/reset_password.html", user=user)

        user.set_password(new_password)
        db.session.commit()
        flash(f"Password for {user.username} has been reset.", "success")
        return redirect(url_for("admin.user_list"))

    return render_template("admin/reset_password.html", user=user)
