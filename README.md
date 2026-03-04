# Flask Blog — claude-code-test-weblog

A full-featured blog web application built with Flask, featuring Markdown editing with live preview, user authentication, tagging, comments, and two browser-based mini-games.

## Features

- **Blog** — create, edit, delete posts with Markdown support
- **Live Markdown preview** — split-pane editor with toggle button (powered by [marked.js](https://marked.js.org/))
- **Tags** — comma-separated tagging, tag filter pages, popular-tags sidebar
- **Comments** — authenticated users can post and delete their own comments
- **Authentication** — register / login by username or email, password hashing via Werkzeug
- **Daily quote** — random inspirational quote injected into every page
- **Games** — Snake and 2048 playable at `/games/`
- **Pagination** — configurable posts-per-page (default 10)
- **Database migrations** — Flask-Migrate / Alembic for schema evolution

## Tech Stack

| Layer | Library |
|---|---|
| Web framework | Flask 3.x |
| ORM | Flask-SQLAlchemy 3.x |
| Migrations | Flask-Migrate 4.x (Alembic) |
| Auth | Flask-Login 0.6.x |
| Markdown | mistune 3.x (server-side) + marked.js (client preview) |
| Database | SQLite (development) |
| Password hashing | Werkzeug `generate_password_hash` |
| Testing | pytest |

## Project Structure

```
claude_code_test/
├── run.py                  # Entry point
├── config.py               # Config class (SECRET_KEY, DB URI, pagination)
├── requirements.txt
├── app/
│   ├── __init__.py         # Application factory (create_app)
│   ├── extensions.py       # db, migrate, login_manager instances
│   ├── models.py           # User, Post, Comment, Tag models
│   ├── auth.py             # /auth/register, /auth/login, /auth/logout
│   ├── blog.py             # Blog routes (index, post CRUD, comments, tags)
│   ├── games.py            # /games/, /games/snake, /games/2048
│   ├── quotes.py           # Random quote pool (70+ quotes)
│   ├── utils.py            # slugify, unique_slug, render_markdown
│   ├── static/
│   │   └── style.css
│   └── templates/
│       ├── base.html
│       ├── auth/           # login.html, register.html
│       ├── blog/           # index.html, post.html, editor.html
│       └── games/          # index.html, snake.html, 2048.html
├── migrations/             # Alembic migration history
├── tests/
│   └── test_app.py         # Comprehensive pytest test suite
└── instance/               # Runtime data — NOT committed (gitignored)
    └── blog.db
```

## Getting Started

### 1. Clone and set up a virtual environment

```bash
git clone https://github.com/hairongchen/claude-code-test-weblog.git
cd claude-code-test-weblog
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the development server

```bash
python run.py
```

The app starts at **http://127.0.0.1:5000**.

To listen on all network interfaces (accessible from other devices on the same network):

```bash
flask --app run:app run --host=0.0.0.0 --port=5000
```

> **Warning:** running with `debug=True` on an external interface is a security risk. Use only on trusted local networks.

### 4. Database

The SQLite database is created automatically in `instance/blog.db` on first run. No manual setup is required.

To apply migrations after pulling schema changes:

```bash
flask db upgrade
```

## Configuration

Settings are in `config.py`. Override via environment variables:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-in-production` | Flask session signing key |
| `POSTS_PER_PAGE` | `10` | Number of posts per index page |

For production, always set a strong `SECRET_KEY` via environment variable.

## URL Routes

| Method | URL | Auth required | Description |
|---|---|---|---|
| GET | `/` | No | Blog index (paginated) |
| GET | `/post/<slug>` | No | Read a post |
| GET/POST | `/post/new` | Yes | Create a post |
| GET/POST | `/post/<slug>/edit` | Yes (owner) | Edit a post |
| POST | `/post/<slug>/delete` | Yes (owner) | Delete a post |
| POST | `/post/<slug>/comment` | Yes | Add a comment |
| POST | `/post/<slug>/comment/<id>/delete` | Yes (owner) | Delete a comment |
| GET | `/tag/<slug>` | No | Posts filtered by tag |
| GET/POST | `/auth/register` | No | Register |
| GET/POST | `/auth/login` | No | Login |
| GET | `/auth/logout` | Yes | Logout |
| GET | `/games/` | No | Games lobby |
| GET | `/games/snake` | No | Snake game |
| GET | `/games/2048` | No | 2048 game |

## Running Tests

```bash
pytest tests/
```

The test suite uses an in-memory SQLite database and covers:

- Utility functions (`slugify`, `unique_slug`, `render_markdown`)
- Database models and constraints
- Auth routes (register, login, logout)
- Blog CRUD, ownership enforcement (403), 404 handling
- Comment creation and deletion
- Tag filtering
- Games routes
- Quotes
- Markdown preview editor DOM elements

## Data Models

```
User ──< Post ──< Comment
           │
           └──< post_tags >── Tag
```

- **User**: username (unique), email (unique), bcrypt password hash
- **Post**: title, slug (unique, auto-generated), Markdown body, timestamps, author FK, tags M2M
- **Tag**: name, slug; shared across posts via `post_tags` join table
- **Comment**: body, timestamps, FK to post and author; cascade-deleted with post

## License

MIT
