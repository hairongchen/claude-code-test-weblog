import re
import mistune


def slugify(text):
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text


def unique_slug(title, existing_slug=None):
    """Generate a unique slug, appending a counter if needed."""
    from .models import Post

    base = slugify(title)
    slug = base
    counter = 1
    while True:
        post = Post.query.filter_by(slug=slug).first()
        if post is None or (existing_slug and slug == existing_slug):
            return slug
        slug = f"{base}-{counter}"
        counter += 1


_md = mistune.create_markdown(
    plugins=["strikethrough", "table", "url"],
)


def render_markdown(text):
    return _md(text)


def markdown_excerpt(text, length=240):
    """Render Markdown to HTML, strip tags, return plain-text excerpt."""
    html = _md(text)
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= length:
        return plain
    return plain[:length].rsplit(" ", 1)[0] + "…"
