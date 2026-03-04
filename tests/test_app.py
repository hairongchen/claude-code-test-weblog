"""
Comprehensive test suite for the Flask Blog Application.

Covers:
- Utility functions (slugify, unique_slug, render_markdown)
- Database models (User, Post, Comment, Tag)
- Auth routes (register, login, logout)
- Blog routes (index, post CRUD, comments, tags)
- Games routes
- Quotes
"""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models import User, Post, Comment, Tag


# ---------------------------------------------------------------------------
# App / DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Create application configured for testing (in-memory SQLite)."""
    test_app = create_app()
    test_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="test-secret",
        POSTS_PER_PAGE=5,
    )
    with test_app.app_context():
        _db.create_all()
        yield test_app
        _db.drop_all()


@pytest.fixture()
def db(app):
    """Wrap each test in a transaction that rolls back afterwards."""
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        # Bind session to the connection so it shares the transaction
        _db.session.bind = connection
        yield _db
        _db.session.remove()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(app, db):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper: register + login a user via HTTP
# ---------------------------------------------------------------------------

def _register(client, username="alice", email="alice@example.com", password="secret123"):
    return client.post("/auth/register", data={
        "username": username,
        "email": email,
        "password": password,
        "confirm": password,
    }, follow_redirects=True)


def _login(client, identifier="alice", password="secret123"):
    return client.post("/auth/login", data={
        "identifier": identifier,
        "password": password,
    }, follow_redirects=True)


def _logout(client):
    return client.get("/auth/logout", follow_redirects=True)


# ===========================================================================
# 1. Utility Functions
# ===========================================================================

class TestSlugify:
    def test_basic(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("Hello World") == "hello-world"

    def test_special_chars_removed(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("Hello, World!") == "hello-world"

    def test_multiple_spaces_collapsed(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("a   b") == "a-b"

    def test_underscores_become_hyphens(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("hello_world") == "hello-world"

    def test_leading_trailing_stripped(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("  hello  ") == "hello"

    def test_all_lowercase(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("UPPER CASE") == "upper-case"

    def test_numbers_preserved(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("Python 3.12") == "python-312"

    def test_already_slug(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("already-slug") == "already-slug"

    def test_empty_string(self, app):
        from app.utils import slugify
        with app.app_context():
            assert slugify("") == ""

    def test_hyphens_not_doubled(self, app):
        from app.utils import slugify
        with app.app_context():
            result = slugify("a--b")
            assert "--" not in result


class TestUniqueSlug:
    def test_returns_base_slug_when_no_conflict(self, db, app):
        from app.utils import unique_slug
        with app.app_context():
            slug = unique_slug("My First Post")
            assert slug == "my-first-post"

    def test_appends_counter_on_conflict(self, db, app):
        from app.utils import unique_slug
        with app.app_context():
            # Create a post that occupies the base slug
            user = User(username="u1", email="u1@x.com")
            user.set_password("pw12345")
            _db.session.add(user)
            _db.session.flush()

            p = Post(title="Conflict", slug="conflict", body="body", user_id=user.id)
            _db.session.add(p)
            _db.session.flush()

            new_slug = unique_slug("Conflict")
            assert new_slug == "conflict-1"

    def test_existing_slug_preserved_on_edit(self, db, app):
        from app.utils import unique_slug
        with app.app_context():
            user = User(username="u2", email="u2@x.com")
            user.set_password("pw12345")
            _db.session.add(user)
            _db.session.flush()

            p = Post(title="Same Title", slug="same-title", body="body", user_id=user.id)
            _db.session.add(p)
            _db.session.flush()

            # Editing same post — existing slug should be returned unchanged
            slug = unique_slug("Same Title", existing_slug="same-title")
            assert slug == "same-title"


class TestRenderMarkdown:
    def test_basic_bold(self, app):
        from app.utils import render_markdown
        with app.app_context():
            result = render_markdown("**bold**")
            assert "<strong>" in result

    def test_italic(self, app):
        from app.utils import render_markdown
        with app.app_context():
            result = render_markdown("*italic*")
            assert "<em>" in result

    def test_strikethrough(self, app):
        from app.utils import render_markdown
        with app.app_context():
            result = render_markdown("~~strike~~")
            assert "<del>" in result

    def test_heading(self, app):
        from app.utils import render_markdown
        with app.app_context():
            result = render_markdown("# H1")
            assert "<h1>" in result

    def test_link(self, app):
        from app.utils import render_markdown
        with app.app_context():
            result = render_markdown("[click](https://example.com)")
            assert "<a " in result and "https://example.com" in result

    def test_table(self, app):
        from app.utils import render_markdown
        with app.app_context():
            md = "| A | B |\n|---|---|\n| 1 | 2 |"
            result = render_markdown(md)
            assert "<table>" in result

    def test_returns_string(self, app):
        from app.utils import render_markdown
        with app.app_context():
            assert isinstance(render_markdown("hello"), str)


# ===========================================================================
# 2. Models
# ===========================================================================

class TestUserModel:
    def test_password_hashing(self, db, app):
        with app.app_context():
            u = User(username="bob", email="bob@example.com")
            u.set_password("mypassword")
            assert u.password_hash != "mypassword"
            assert u.check_password("mypassword") is True
            assert u.check_password("wrongpassword") is False

    def test_repr(self, db, app):
        with app.app_context():
            u = User(username="carol", email="carol@example.com")
            u.set_password("pw12345")
            assert "carol" in repr(u)

    def test_unique_username_constraint(self, db, app):
        with app.app_context():
            u1 = User(username="dave", email="dave@example.com")
            u1.set_password("pw12345")
            u2 = User(username="dave", email="dave2@example.com")
            u2.set_password("pw12345")
            _db.session.add_all([u1, u2])
            with pytest.raises(Exception):
                _db.session.flush()

    def test_unique_email_constraint(self, db, app):
        with app.app_context():
            u1 = User(username="eve1", email="shared@example.com")
            u1.set_password("pw12345")
            u2 = User(username="eve2", email="shared@example.com")
            u2.set_password("pw12345")
            _db.session.add_all([u1, u2])
            with pytest.raises(Exception):
                _db.session.flush()


class TestPostModel:
    def _make_user(self, name="poster"):
        u = User(username=name, email=f"{name}@x.com")
        u.set_password("pw12345")
        _db.session.add(u)
        _db.session.flush()
        return u

    def test_create_post(self, db, app):
        with app.app_context():
            u = self._make_user()
            p = Post(title="Hello", slug="hello", body="World", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()
            assert Post.query.filter_by(slug="hello").first() is not None

    def test_post_author_relationship(self, db, app):
        with app.app_context():
            u = self._make_user("rel_user")
            p = Post(title="Rel", slug="rel", body="body", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()
            assert p.author.username == "rel_user"

    def test_post_repr(self, db, app):
        with app.app_context():
            u = self._make_user("repr_user")
            p = Post(title="Repr", slug="repr-test", body="body", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()
            assert "repr-test" in repr(p)

    def test_cascade_delete_comments(self, db, app):
        with app.app_context():
            u = self._make_user("cascade_user")
            p = Post(title="Cascade", slug="cascade", body="body", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()
            c = Comment(body="hi", post_id=p.id, user_id=u.id)
            _db.session.add(c)
            _db.session.flush()
            comment_id = c.id
            _db.session.delete(p)
            _db.session.flush()
            assert Comment.query.get(comment_id) is None


class TestTagModel:
    def test_create_tag(self, db, app):
        with app.app_context():
            t = Tag(name="python", slug="python")
            _db.session.add(t)
            _db.session.flush()
            assert Tag.query.filter_by(slug="python").first() is not None

    def test_tag_repr(self, db, app):
        with app.app_context():
            t = Tag(name="flask", slug="flask")
            assert "flask" in repr(t)

    def test_tag_post_association(self, db, app):
        with app.app_context():
            u = User(username="tag_user", email="tag@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()

            p = Post(title="Tagged", slug="tagged", body="body", user_id=u.id)
            t = Tag(name="web", slug="web")
            p.tags.append(t)
            _db.session.add(p)
            _db.session.flush()

            fetched = Post.query.filter_by(slug="tagged").first()
            assert any(tag.name == "web" for tag in fetched.tags)


class TestCommentModel:
    def test_create_comment(self, db, app):
        with app.app_context():
            u = User(username="commenter", email="c@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()

            p = Post(title="P", slug="p-test", body="b", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()

            c = Comment(body="Great post!", post_id=p.id, user_id=u.id)
            _db.session.add(c)
            _db.session.flush()

            assert c.id is not None
            assert c.author.username == "commenter"
            assert c.post.title == "P"


# ===========================================================================
# 3. Auth Routes
# ===========================================================================

class TestRegister:
    def test_get_register_page(self, client):
        resp = client.get("/auth/register")
        assert resp.status_code == 200
        assert b"Register" in resp.data

    def test_successful_registration(self, client):
        resp = _register(client)
        assert resp.status_code == 200
        assert b"log in" in resp.data.lower() or b"login" in resp.data.lower()

    def test_username_too_short(self, client):
        resp = client.post("/auth/register", data={
            "username": "a",
            "email": "a@example.com",
            "password": "secret123",
            "confirm": "secret123",
        }, follow_redirects=True)
        assert b"at least 2 characters" in resp.data

    def test_invalid_email(self, client):
        resp = client.post("/auth/register", data={
            "username": "alice",
            "email": "not-an-email",
            "password": "secret123",
            "confirm": "secret123",
        }, follow_redirects=True)
        assert b"valid email" in resp.data

    def test_password_too_short(self, client):
        resp = client.post("/auth/register", data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "abc",
            "confirm": "abc",
        }, follow_redirects=True)
        assert b"at least 6 characters" in resp.data

    def test_passwords_mismatch(self, client):
        resp = client.post("/auth/register", data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
            "confirm": "different",
        }, follow_redirects=True)
        assert b"do not match" in resp.data

    def test_duplicate_username(self, client):
        _register(client, username="dupuser", email="dup1@example.com")
        resp = client.post("/auth/register", data={
            "username": "dupuser",
            "email": "dup2@example.com",
            "password": "secret123",
            "confirm": "secret123",
        }, follow_redirects=True)
        assert b"already taken" in resp.data

    def test_duplicate_email(self, client):
        _register(client, username="user1", email="dup@example.com")
        resp = client.post("/auth/register", data={
            "username": "user2",
            "email": "dup@example.com",
            "password": "secret123",
            "confirm": "secret123",
        }, follow_redirects=True)
        assert b"already registered" in resp.data

    def test_authenticated_user_redirected(self, client):
        _register(client)
        _login(client)
        resp = client.get("/auth/register", follow_redirects=False)
        assert resp.status_code == 302


class TestLogin:
    def setup_method(self):
        pass

    def test_get_login_page(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data

    def test_login_with_username(self, client):
        _register(client, username="loginuser", email="lu@example.com")
        _logout(client)
        resp = _login(client, identifier="loginuser")
        assert resp.status_code == 200
        assert b"loginuser" in resp.data or b"logout" in resp.data.lower()

    def test_login_with_email(self, client):
        _register(client, username="emailuser", email="eu@example.com")
        _logout(client)
        resp = _login(client, identifier="eu@example.com")
        assert resp.status_code == 200

    def test_wrong_password(self, client):
        _register(client, username="wrongpw", email="wpw@example.com")
        _logout(client)
        resp = client.post("/auth/login", data={
            "identifier": "wrongpw",
            "password": "notthepassword",
        }, follow_redirects=True)
        assert b"Invalid" in resp.data

    def test_nonexistent_user(self, client):
        resp = client.post("/auth/login", data={
            "identifier": "nobody",
            "password": "secret123",
        }, follow_redirects=True)
        assert b"Invalid" in resp.data

    def test_authenticated_user_redirected_from_login(self, client):
        _register(client, username="redir_user", email="redir@example.com")
        _login(client, identifier="redir_user")
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302


class TestLogout:
    def test_logout_redirects(self, client):
        _register(client, username="logoutuser", email="lo@example.com")
        _login(client, identifier="logoutuser")
        resp = client.get("/auth/logout", follow_redirects=True)
        assert b"logged out" in resp.data

    def test_logout_requires_login(self, client):
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


# ===========================================================================
# 4. Blog Routes
# ===========================================================================

class TestBlogIndex:
    def test_index_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_shows_posts(self, client, db, app):
        with app.app_context():
            u = User(username="idx_user", email="idx@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()
            p = Post(title="Index Post", slug="index-post", body="hello", user_id=u.id)
            _db.session.add(p)
            _db.session.commit()

        resp = client.get("/")
        assert b"Index Post" in resp.data

    def test_pagination_param(self, client):
        resp = client.get("/?page=1")
        assert resp.status_code == 200


class TestPostView:
    def test_nonexistent_post_404(self, client):
        resp = client.get("/post/does-not-exist")
        assert resp.status_code == 404

    def test_existing_post_200(self, client, db, app):
        with app.app_context():
            u = User(username="pv_user", email="pv@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()
            p = Post(title="View Post", slug="view-post", body="content here", user_id=u.id)
            _db.session.add(p)
            _db.session.commit()

        resp = client.get("/post/view-post")
        assert resp.status_code == 200
        assert b"View Post" in resp.data


class TestNewPost:
    def test_new_post_requires_login(self, client):
        resp = client.get("/post/new", follow_redirects=False)
        assert resp.status_code == 302

    def test_new_post_get_authenticated(self, client):
        _register(client, username="np_user", email="np@example.com")
        _login(client, identifier="np_user")
        resp = client.get("/post/new")
        assert resp.status_code == 200

    def test_create_post_success(self, client):
        _register(client, username="creator", email="creator@example.com")
        _login(client, identifier="creator")
        resp = client.post("/post/new", data={
            "title": "My New Post",
            "body": "This is the body text.",
            "tags": "python, flask",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"My New Post" in resp.data

    def test_create_post_empty_title(self, client):
        _register(client, username="no_title", email="nt@example.com")
        _login(client, identifier="no_title")
        resp = client.post("/post/new", data={
            "title": "",
            "body": "Some body",
            "tags": "",
        }, follow_redirects=True)
        assert b"Title is required" in resp.data

    def test_create_post_empty_body(self, client):
        _register(client, username="no_body", email="nb@example.com")
        _login(client, identifier="no_body")
        resp = client.post("/post/new", data={
            "title": "Title Only",
            "body": "",
            "tags": "",
        }, follow_redirects=True)
        assert b"Body is required" in resp.data


class TestEditPost:
    def _create_post_as(self, client, username, email, title, body):
        _register(client, username=username, email=email)
        _login(client, identifier=username)
        client.post("/post/new", data={
            "title": title, "body": body, "tags": "",
        }, follow_redirects=True)
        _logout(client)

    def test_edit_post_by_owner(self, client):
        self._create_post_as(client, "edit_owner", "eo@example.com", "Edit Me", "original")
        _login(client, identifier="edit_owner")

        from app.utils import slugify
        slug = slugify("Edit Me")
        resp = client.post(f"/post/{slug}/edit", data={
            "title": "Edited Title",
            "body": "updated body",
            "tags": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Edited Title" in resp.data

    def test_edit_post_forbidden_for_other_user(self, client):
        self._create_post_as(client, "ep_owner", "ep_owner@x.com", "Owners Post", "body")
        _register(client, username="ep_intruder", email="ep_intruder@x.com")
        _login(client, identifier="ep_intruder")

        from app.utils import slugify
        slug = slugify("Owners Post")
        resp = client.post(f"/post/{slug}/edit", data={
            "title": "Hacked", "body": "hacked", "tags": "",
        })
        assert resp.status_code == 403

    def test_edit_nonexistent_post_404(self, client):
        _register(client, username="edit_404", email="e404@x.com")
        _login(client, identifier="edit_404")
        resp = client.post("/post/ghost-post/edit", data={
            "title": "T", "body": "B", "tags": "",
        })
        assert resp.status_code == 404


class TestDeletePost:
    def _create_post_as(self, client, username, email, title, body):
        _register(client, username=username, email=email)
        _login(client, identifier=username)
        client.post("/post/new", data={
            "title": title, "body": body, "tags": "",
        }, follow_redirects=True)
        _logout(client)

    def test_delete_post_by_owner(self, client):
        self._create_post_as(client, "del_owner", "do@example.com", "Delete Me Post", "body")
        _login(client, identifier="del_owner")

        from app.utils import slugify
        slug = slugify("Delete Me Post")
        resp = client.post(f"/post/{slug}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert client.get(f"/post/{slug}").status_code == 404

    def test_delete_post_forbidden_for_other_user(self, client):
        self._create_post_as(client, "del_op2", "do2@example.com", "Protected Post Two", "body")
        _register(client, username="del_intruder2", email="di2@x.com")
        _login(client, identifier="del_intruder2")

        from app.utils import slugify
        slug = slugify("Protected Post Two")
        resp = client.post(f"/post/{slug}/delete")
        assert resp.status_code == 403


class TestComments:
    def _setup(self, client, username, email, title, body):
        _register(client, username=username, email=email)
        _login(client, identifier=username)
        client.post("/post/new", data={
            "title": title, "body": body, "tags": "",
        }, follow_redirects=True)
        return username

    def test_add_comment(self, client):
        self._setup(client, "commentor1", "cm1@x.com", "Comment Post One", "body")
        from app.utils import slugify
        slug = slugify("Comment Post One")
        resp = client.post(f"/post/{slug}/comment", data={
            "body": "Great post!"
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Great post!" in resp.data

    def test_empty_comment_rejected(self, client):
        self._setup(client, "commentor2", "cm2@x.com", "Comment Post Two", "body")
        from app.utils import slugify
        slug = slugify("Comment Post Two")
        resp = client.post(f"/post/{slug}/comment", data={
            "body": ""
        }, follow_redirects=True)
        assert b"cannot be empty" in resp.data

    def test_comment_requires_login(self, client, db, app):
        with app.app_context():
            u = User(username="noauth_cm", email="noauth_cm@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()
            p = Post(title="NoAuth Comment", slug="noauth-comment", body="body", user_id=u.id)
            _db.session.add(p)
            _db.session.commit()

        resp = client.post("/post/noauth-comment/comment", data={"body": "hi"})
        assert resp.status_code == 302

    def test_delete_own_comment(self, client, db, app):
        with app.app_context():
            u = User(username="del_cm_user", email="dcm@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()
            p = Post(title="Del Cm Post", slug="del-cm-post", body="body", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()
            c = Comment(body="to be deleted", post_id=p.id, user_id=u.id)
            _db.session.add(c)
            _db.session.commit()
            comment_id = c.id

        _login(client, identifier="del_cm_user")
        resp = client.post(f"/post/del-cm-post/comment/{comment_id}/delete",
                           follow_redirects=True)
        assert resp.status_code == 200

    def test_delete_other_users_comment_forbidden(self, client):
        # Register owner, create post + comment via HTTP
        _register(client, username="cm_owner2", email="cm_owner2@x.com")
        _login(client, identifier="cm_owner2")
        client.post("/post/new", data={
            "title": "Cm Forbidden Post", "body": "body", "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("Cm Forbidden Post")
        client.post(f"/post/{slug}/comment", data={"body": "owner's comment"},
                    follow_redirects=True)

        # Find the comment id from the DB through the app context
        with client.application.app_context():
            p = Post.query.filter_by(slug=slug).first()
            comment_id = p.comments[0].id

        _logout(client)

        # Register and login as stranger
        _register(client, username="cm_stranger2", email="cm_stranger2@x.com")
        _login(client, identifier="cm_stranger2")

        resp = client.post(f"/post/{slug}/comment/{comment_id}/delete")
        assert resp.status_code == 403


class TestTagRoutes:
    def test_tag_page_404_for_unknown(self, client):
        resp = client.get("/tag/no-such-tag")
        assert resp.status_code == 404

    def test_tag_page_shows_posts(self, client, db, app):
        with app.app_context():
            u = User(username="tag_route_user", email="tru@x.com")
            u.set_password("pw12345")
            _db.session.add(u)
            _db.session.flush()
            t = Tag(name="testing", slug="testing")
            _db.session.add(t)
            p = Post(title="Tagged Post", slug="tagged-post", body="body", user_id=u.id)
            p.tags.append(t)
            _db.session.add(p)
            _db.session.commit()

        resp = client.get("/tag/testing")
        assert resp.status_code == 200
        assert b"Tagged Post" in resp.data


# ===========================================================================
# 5. Games Routes
# ===========================================================================

class TestGamesRoutes:
    def test_games_index(self, client):
        resp = client.get("/games/")
        assert resp.status_code == 200

    def test_snake_game_page(self, client):
        resp = client.get("/games/snake")
        assert resp.status_code == 200

    def test_2048_game_page(self, client):
        resp = client.get("/games/2048")
        assert resp.status_code == 200


# ===========================================================================
# 6. Quotes
# ===========================================================================

class TestQuotes:
    def test_get_daily_quote_returns_dict(self):
        from app.quotes import get_daily_quote
        q = get_daily_quote()
        assert isinstance(q, dict)

    def test_quote_has_text_and_author(self):
        from app.quotes import get_daily_quote
        q = get_daily_quote()
        assert "text" in q
        assert "author" in q

    def test_quote_text_is_nonempty(self):
        from app.quotes import get_daily_quote
        q = get_daily_quote()
        assert len(q["text"]) > 0

    def test_quote_author_is_nonempty(self):
        from app.quotes import get_daily_quote
        q = get_daily_quote()
        assert len(q["author"]) > 0

    def test_quotes_list_nonempty(self):
        from app.quotes import QUOTES
        assert len(QUOTES) > 0

    def test_quotes_all_tuples(self):
        from app.quotes import QUOTES
        for item in QUOTES:
            assert isinstance(item, tuple)
            assert len(item) == 2


# ===========================================================================
# TestEditorPreviewFeature
# ===========================================================================

class TestEditorPreviewFeature:
    """Verify the Markdown split-preview DOM elements are present in the editor."""

    def _get_new_editor(self, client):
        """Return the GET /post/new response (authenticated)."""
        _register(client, username="preview_user", email="preview@example.com")
        _login(client, identifier="preview_user")
        return client.get("/post/new")

    def _create_and_get_edit(self, client):
        """Create a post then return the GET /post/<slug>/edit response."""
        _register(client, username="preview_edit_user", email="preview_edit@example.com")
        _login(client, identifier="preview_edit_user")
        client.post("/post/new", data={
            "title": "Preview Edit Test",
            "body": "some body",
            "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("Preview Edit Test")
        return client.get(f"/post/{slug}/edit")

    def test_editor_loads_marked_js_cdn(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b"marked" in resp.data

    def test_editor_has_preview_toggle_button(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b'id="preview-toggle"' in resp.data

    def test_editor_has_preview_pane(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b'id="preview-pane"' in resp.data

    def test_editor_body_textarea_has_name_attribute(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b'id="body"' in resp.data
        assert b'name="body"' in resp.data

    def test_editor_has_aria_attributes_on_toggle(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b'aria-pressed' in resp.data

    def test_editor_has_editor_body_wrap(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b"editor-body-wrap" in resp.data

    def test_create_post_still_works_with_preview_dom(self, client):
        _register(client, username="preview_create", email="preview_create@example.com")
        _login(client, identifier="preview_create")
        resp = client.post("/post/new", data={
            "title": "Preview Create Post",
            "body": "Hello from preview create test",
            "tags": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Preview Create Post" in resp.data

    def test_edit_post_still_works_with_preview_dom(self, client):
        _register(client, username="preview_edit2", email="preview_edit2@example.com")
        _login(client, identifier="preview_edit2")
        client.post("/post/new", data={
            "title": "Preview Edit Post",
            "body": "original body",
            "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("Preview Edit Post")
        resp = client.post(f"/post/{slug}/edit", data={
            "title": "Preview Edit Post Updated",
            "body": "updated body",
            "tags": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Preview Edit Post Updated" in resp.data

    def test_editor_page_has_preview_toolbar_class(self, client):
        resp = self._get_new_editor(client)
        assert resp.status_code == 200
        assert b"preview-toolbar" in resp.data

    def test_edit_page_also_has_preview_feature(self, client):
        resp = self._create_and_get_edit(client)
        assert resp.status_code == 200
        assert b'id="preview-toggle"' in resp.data
        assert b'id="preview-pane"' in resp.data
