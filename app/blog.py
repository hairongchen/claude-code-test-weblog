from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    current_app,
)
from flask_login import login_required, current_user
from .extensions import db
from .models import Post, Comment, Tag
from .utils import unique_slug, slugify

blog_bp = Blueprint("blog", __name__)


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
