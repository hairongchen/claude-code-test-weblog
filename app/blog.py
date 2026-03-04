import os
import uuid
import io
from datetime import datetime, timezone
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    current_app,
    jsonify,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from .extensions import db
from .models import Post, Comment, Tag, PostImage
from .utils import unique_slug, slugify

blog_bp = Blueprint("blog", __name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_IMGHDR_TYPES = {"jpeg", "png", "gif", "webp"}


def _sync_tags(tag_string):
    """Parse comma-separated tag input, return list of Tag objects (create if needed)."""
    seen, result = set(), []
    for raw in tag_string.split(","):
        name = raw.strip()[:40]
        if not name:
            continue
        sl = slugify(name)
        if sl in seen:
            continue
        seen.add(sl)
        tag = Tag.query.filter_by(slug=sl).first()
        if not tag:
            tag = Tag(name=name.lower(), slug=sl)
            db.session.add(tag)
        result.append(tag)
    return result


def _save_upload(file_storage):
    if not file_storage or file_storage.filename == "":
        raise ValueError("No file provided.")
    safe_name = secure_filename(file_storage.filename)
    if not safe_name:
        raise ValueError("Invalid filename.")
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("File type not allowed.")
    file_bytes = file_storage.read()
    # Detect image type via Pillow (imghdr was removed in Python 3.13)
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        detected = img.format.lower() if img.format else None
        # Pillow uses "JPEG" not "jpeg" — normalise and map to imghdr-style names
        FORMAT_MAP = {"jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}
        detected = FORMAT_MAP.get(detected, detected)
    except Exception:
        detected = None
    if detected is None or detected not in ALLOWED_IMGHDR_TYPES:
        raise ValueError("File type not allowed.")
    now = datetime.now(timezone.utc)
    sub_dir = os.path.join(
        current_app.config["UPLOAD_FOLDER"],
        str(now.year),
        f"{now.month:02d}",
    )
    os.makedirs(sub_dir, exist_ok=True)
    disk_name = f"{uuid.uuid4().hex}.{ext}"
    abs_path = os.path.join(sub_dir, disk_name)
    with open(abs_path, "wb") as fh:
        fh.write(file_bytes)
    static_root = os.path.join(current_app.root_path, "static")
    rel = os.path.relpath(abs_path, static_root).replace("\\", "/")
    public_url = f"/static/{rel}"
    record = PostImage(
        filename=disk_name,
        original_name=safe_name,
        post_id=None,
        size_bytes=len(file_bytes),
    )
    db.session.add(record)
    db.session.commit()
    return {
        "url": public_url,
        "filename": disk_name,
        "original_name": safe_name,
        "size_bytes": len(file_bytes),
    }


@blog_bp.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("POSTS_PER_PAGE", 10)
    pagination = Post.query.order_by(Post.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    popular_tags = (
        db.session.query(Tag)
        .join(Tag.posts)
        .group_by(Tag.id)
        .order_by(db.func.count(Post.id).desc())
        .limit(20)
        .all()
    )
    return render_template("blog/index.html", pagination=pagination, popular_tags=popular_tags)


@blog_bp.route("/tag/<slug>")
def tag(slug):
    t = Tag.query.filter_by(slug=slug).first_or_404()
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("POSTS_PER_PAGE", 10)
    pagination = (
        Post.query
        .filter(Post.tags.any(Tag.slug == slug))
        .order_by(Post.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    popular_tags = (
        db.session.query(Tag)
        .join(Tag.posts)
        .group_by(Tag.id)
        .order_by(db.func.count(Post.id).desc())
        .limit(20)
        .all()
    )
    return render_template(
        "blog/index.html",
        pagination=pagination,
        popular_tags=popular_tags,
        active_tag=t,
    )


@blog_bp.route("/post/<slug>")
def post(slug):
    p = Post.query.filter_by(slug=slug).first_or_404()
    return render_template("blog/post.html", post=p)


@blog_bp.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        title    = request.form.get("title", "").strip()
        body     = request.form.get("body",  "").strip()
        tag_str  = request.form.get("tags",  "").strip()

        errors = []
        if not title:
            errors.append("Title is required.")
        if not body:
            errors.append("Body is required.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("blog/editor.html", title=title, body=body, tags=tag_str)

        slug = unique_slug(title)
        p = Post(title=title, slug=slug, body=body, user_id=current_user.id)
        p.tags = _sync_tags(tag_str)
        db.session.add(p)
        db.session.commit()
        flash("🎉 Post published!", "success")
        return redirect(url_for("blog.post", slug=p.slug))

    return render_template("blog/editor.html")


@blog_bp.route("/post/<slug>/edit", methods=["GET", "POST"])
@login_required
def edit_post(slug):
    p = Post.query.filter_by(slug=slug).first_or_404()
    if p.user_id != current_user.id:
        abort(403)

    if request.method == "POST":
        title   = request.form.get("title", "").strip()
        body    = request.form.get("body",  "").strip()
        tag_str = request.form.get("tags",  "").strip()

        errors = []
        if not title:
            errors.append("Title is required.")
        if not body:
            errors.append("Body is required.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("blog/editor.html", post=p, title=title, body=body, tags=tag_str)

        p.title = title
        p.body  = body
        p.slug  = unique_slug(title, existing_slug=p.slug)
        p.tags  = _sync_tags(tag_str)
        db.session.commit()
        flash("✅ Post updated!", "success")
        return redirect(url_for("blog.post", slug=p.slug))

    tag_str = ", ".join(t.name for t in p.tags)
    return render_template("blog/editor.html", post=p, title=p.title, body=p.body, tags=tag_str)


@blog_bp.route("/post/<slug>/delete", methods=["POST"])
@login_required
def delete_post(slug):
    p = Post.query.filter_by(slug=slug).first_or_404()
    if p.user_id != current_user.id:
        abort(403)
    db.session.delete(p)
    db.session.commit()
    flash("🗑️ Post deleted.", "success")
    return redirect(url_for("blog.index"))


@blog_bp.route("/post/<slug>/comment", methods=["POST"])
@login_required
def add_comment(slug):
    p = Post.query.filter_by(slug=slug).first_or_404()
    body = request.form.get("body", "").strip()
    if not body:
        flash("💬 Comment cannot be empty.", "error")
        return redirect(url_for("blog.post", slug=slug))
    c = Comment(body=body, post_id=p.id, user_id=current_user.id)
    db.session.add(c)
    db.session.commit()
    flash("💬 Comment posted!", "success")
    return redirect(url_for("blog.post", slug=slug) + "#comments")


@blog_bp.route("/post/<slug>/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(slug, comment_id):
    c = Comment.query.get_or_404(comment_id)
    if c.user_id != current_user.id:
        abort(403)
    db.session.delete(c)
    db.session.commit()
    flash("🗑️ Comment deleted.", "success")
    return redirect(url_for("blog.post", slug=slug) + "#comments")


@blog_bp.route("/upload-image", methods=["POST"])
@login_required
def upload_image():
    try:
        result = _save_upload(request.files.get("image"))
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@blog_bp.app_errorhandler(413)
def handle_too_large(e):
    return jsonify({"error": "File too large. Max 5 MB."}), 413
