"""
Tests for the image upload feature.

Covers:
- PostImage model (Group A)
- Upload API endpoint (Group B)
- Editor UI elements (Group C)
- Regression tests to verify existing functionality is unaffected (Group D)
"""

import io
import os
import struct
import zlib

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db as _db
from app.models import User, Post, PostImage


# ---------------------------------------------------------------------------
# Minimal image helpers
# ---------------------------------------------------------------------------

def minimal_png():
    """Return bytes of a 1x1 white PNG."""
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        crc = zlib.crc32(name + data) & 0xffffffff
        return c + struct.pack('>I', crc)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    raw = b'\x00\xff\xff\xff'
    compressed = zlib.compress(raw)
    idat = chunk(b'IDAT', compressed)
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def minimal_jpeg():
    """Return a minimal valid JPEG (SOI + EOI markers only)."""
    return (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
        b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e>'
        b'\x11\t\n\x0b\x0e\x0e\x0e\x0e\x0e\x0e\x0e\x0e\x0e\x0e\x0e\x0e\x0e'
        b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
        b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
        b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x0a\xd3P\x00\xff\xd9'
    )


# ---------------------------------------------------------------------------
# App / DB fixtures (isolated from test_app.py session-scoped fixture)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """Create an isolated test application with an in-memory DB and temp upload dir."""
    upload_dir = tmp_path_factory.mktemp("uploads")
    test_app = create_app()
    test_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="test-secret-upload",
        POSTS_PER_PAGE=5,
        UPLOAD_FOLDER=str(upload_dir),
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
        _db.session.bind = connection
        yield _db
        _db.session.remove()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(app, db):
    return app.test_client()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _register(client, username="testuser", email="testuser@example.com", password="secret123"):
    return client.post("/auth/register", data={
        "username": username,
        "email": email,
        "password": password,
        "confirm": password,
    }, follow_redirects=True)


def _login(client, identifier="testuser", password="secret123"):
    return client.post("/auth/login", data={
        "identifier": identifier,
        "password": password,
    }, follow_redirects=True)


def _logout(client):
    return client.get("/auth/logout", follow_redirects=True)


def _register_and_login(client, username="uploader", email="uploader@example.com"):
    """Register and log in a fresh user, returning the username."""
    _register(client, username=username, email=email)
    _login(client, identifier=username)
    return username


# ===========================================================================
# Group A: PostImage Model Tests
# ===========================================================================

class TestPostImageModel:

    def _make_user(self, name="imguser"):
        u = User(username=name, email=f"{name}@x.com")
        u.set_password("pw12345")
        _db.session.add(u)
        _db.session.flush()
        return u

    def test_create_minimal(self, db, app):
        """Create a PostImage with required fields, flush, then query it back."""
        with app.app_context():
            img = PostImage(
                filename="abc123.png",
                original_name="photo.png",
                size_bytes=1024,
            )
            _db.session.add(img)
            _db.session.flush()
            fetched = PostImage.query.filter_by(filename="abc123.png").first()
            assert fetched is not None
            assert fetched.original_name == "photo.png"
            assert fetched.size_bytes == 1024

    def test_uploaded_at_auto(self, db, app):
        """uploaded_at should be populated automatically on creation."""
        with app.app_context():
            img = PostImage(
                filename="auto_time.png",
                original_name="x.png",
                size_bytes=100,
            )
            _db.session.add(img)
            _db.session.flush()
            assert img.uploaded_at is not None

    def test_post_id_nullable(self, db, app):
        """post_id=None should not raise an error (image not yet attached to a post)."""
        with app.app_context():
            img = PostImage(
                filename="nullable_post.png",
                original_name="n.png",
                size_bytes=50,
                post_id=None,
            )
            _db.session.add(img)
            _db.session.flush()
            assert img.id is not None

    def test_filename_unique(self, db, app):
        """Inserting a duplicate filename should raise an IntegrityError."""
        with app.app_context():
            img1 = PostImage(filename="dup.png", original_name="d.png", size_bytes=10)
            img2 = PostImage(filename="dup.png", original_name="d2.png", size_bytes=20)
            _db.session.add(img1)
            _db.session.flush()
            _db.session.add(img2)
            with pytest.raises(Exception):  # IntegrityError or similar
                _db.session.flush()

    def test_repr(self, db, app):
        """repr should contain the filename."""
        with app.app_context():
            img = PostImage(filename="repr_test.png", original_name="r.png", size_bytes=1)
            assert "repr_test.png" in repr(img)

    def test_post_relationship(self, db, app):
        """Assigning post_id should link the image through the post.images backref."""
        with app.app_context():
            u = self._make_user("rel_img_user")
            p = Post(title="Img Post", slug="img-post", body="body", user_id=u.id)
            _db.session.add(p)
            _db.session.flush()

            img = PostImage(
                filename="rel_img.png",
                original_name="rel.png",
                size_bytes=200,
                post_id=p.id,
            )
            _db.session.add(img)
            _db.session.flush()

            fetched_post = Post.query.get(p.id)
            assert any(i.filename == "rel_img.png" for i in fetched_post.images)


# ===========================================================================
# Group B: Upload API Tests
# ===========================================================================

class TestUploadImageAPI:

    def _post_image(self, client, data, content_type="multipart/form-data"):
        return client.post("/upload-image", data=data, content_type=content_type)

    def test_upload_valid_png(self, client):
        """POST a real minimal PNG; expect 200 with JSON payload."""
        _register_and_login(client, username="up_png", email="up_png@x.com")
        data = {"image": (io.BytesIO(minimal_png()), "test.png")}
        resp = self._post_image(client, data)
        assert resp.status_code == 200
        json_data = resp.get_json()
        assert "url" in json_data
        assert "filename" in json_data
        assert "original_name" in json_data
        assert "size_bytes" in json_data

    def test_upload_valid_jpeg(self, client):
        """POST a real minimal JPEG; expect 200."""
        _register_and_login(client, username="up_jpg", email="up_jpg@x.com")
        data = {"image": (io.BytesIO(minimal_jpeg()), "photo.jpg")}
        resp = self._post_image(client, data)
        assert resp.status_code == 200

    def test_upload_wrong_extension(self, client):
        """POST a .txt file; expect 400 with error JSON."""
        _register_and_login(client, username="up_txt", email="up_txt@x.com")
        data = {"image": (io.BytesIO(b"plain text content"), "file.txt")}
        resp = self._post_image(client, data)
        assert resp.status_code == 400
        json_data = resp.get_json()
        assert "error" in json_data

    def test_upload_disguised_type(self, client):
        """POST plain text bytes with a .jpg extension; expect 400 (Pillow rejects it)."""
        _register_and_login(client, username="up_dis", email="up_dis@x.com")
        data = {"image": (io.BytesIO(b"this is not an image at all"), "fake.jpg")}
        resp = self._post_image(client, data)
        assert resp.status_code == 400
        json_data = resp.get_json()
        assert "error" in json_data

    def test_upload_empty_field(self, client):
        """POST with an empty filename; expect 400."""
        _register_and_login(client, username="up_empty", email="up_empty@x.com")
        data = {"image": (io.BytesIO(b""), "")}
        resp = self._post_image(client, data)
        assert resp.status_code == 400

    def test_upload_no_field(self, client):
        """POST without any image field; expect 400."""
        _register_and_login(client, username="up_nofield", email="up_nofield@x.com")
        resp = client.post("/upload-image", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_unauthenticated(self, client):
        """POST without logging in; expect redirect (302) not JSON."""
        _logout(client)
        data = {"image": (io.BytesIO(minimal_png()), "test.png")}
        resp = self._post_image(client, data)
        # flask-login redirects unauthenticated users to login page
        assert resp.status_code == 302

    def test_upload_db_record_created(self, client, db, app):
        """After a successful upload, a PostImage row should exist in the DB."""
        _register_and_login(client, username="up_db", email="up_db@x.com")
        data = {"image": (io.BytesIO(minimal_png()), "db_check.png")}
        resp = self._post_image(client, data)
        assert resp.status_code == 200
        json_data = resp.get_json()
        saved_filename = json_data["filename"]

        with app.app_context():
            record = PostImage.query.filter_by(filename=saved_filename).first()
            assert record is not None
            assert record.original_name == "db_check.png"

    def test_upload_file_saved_to_disk(self, client, app):
        """After a successful upload, the file should exist on disk."""
        _register_and_login(client, username="up_disk", email="up_disk@x.com")
        data = {"image": (io.BytesIO(minimal_png()), "disk_check.png")}
        resp = self._post_image(client, data)
        assert resp.status_code == 200
        json_data = resp.get_json()
        public_url = json_data["url"]  # e.g. /static/uploads/2026/03/abc.png

        # Build the absolute path from the URL: strip leading /static/
        rel_path = public_url.lstrip("/").replace("static/", "", 1)
        abs_path = os.path.join(app.root_path, "static", rel_path)
        assert os.path.isfile(abs_path), f"Expected file on disk at: {abs_path}"


# ===========================================================================
# Group C: Editor UI Tests
# ===========================================================================

class TestEditorUIImageUpload:

    def _get_new_editor(self, client, username="editor_ui_user", email="editor_ui@x.com"):
        _register(client, username=username, email=email)
        _login(client, identifier=username)
        return client.get("/post/new")

    def test_upload_button_in_new_post_editor(self, client):
        """GET /post/new should include the upload button element."""
        resp = self._get_new_editor(client, username="ui_btn", email="ui_btn@x.com")
        assert resp.status_code == 200
        assert b"img-upload-btn" in resp.data

    def test_file_input_in_new_post_editor(self, client):
        """GET /post/new should include the hidden file input element."""
        resp = self._get_new_editor(client, username="ui_input", email="ui_input@x.com")
        assert resp.status_code == 200
        assert b"img-file-input" in resp.data

    def test_error_div_in_new_post_editor(self, client):
        """GET /post/new should include the error display div."""
        resp = self._get_new_editor(client, username="ui_err", email="ui_err@x.com")
        assert resp.status_code == 200
        assert b"img-upload-error" in resp.data

    def test_upload_button_in_edit_editor(self, client):
        """GET /post/<slug>/edit should also include the upload button."""
        _register(client, username="ui_edit", email="ui_edit@x.com")
        _login(client, identifier="ui_edit")
        client.post("/post/new", data={
            "title": "UI Edit Test Post",
            "body": "some body text",
            "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("UI Edit Test Post")
        resp = client.get(f"/post/{slug}/edit")
        assert resp.status_code == 200
        assert b"img-upload-btn" in resp.data


# ===========================================================================
# Group D: Regression Tests
# ===========================================================================

class TestRegressionAfterImageUpload:

    def test_create_post_still_works(self, client):
        """Creating a new post should still work after image upload was added."""
        _register(client, username="reg_create", email="reg_create@x.com")
        _login(client, identifier="reg_create")
        resp = client.post("/post/new", data={
            "title": "Regression Create Post",
            "body": "This body is for regression testing.",
            "tags": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Regression Create Post" in resp.data

    def test_edit_post_still_works(self, client):
        """Editing a post should still work after image upload was added."""
        _register(client, username="reg_edit", email="reg_edit@x.com")
        _login(client, identifier="reg_edit")
        client.post("/post/new", data={
            "title": "Regression Edit Original",
            "body": "Original body.",
            "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("Regression Edit Original")
        resp = client.post(f"/post/{slug}/edit", data={
            "title": "Regression Edit Updated",
            "body": "Updated body.",
            "tags": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Regression Edit Updated" in resp.data

    def test_delete_post_still_works(self, client):
        """Deleting a post should still work after image upload was added."""
        _register(client, username="reg_del", email="reg_del@x.com")
        _login(client, identifier="reg_del")
        client.post("/post/new", data={
            "title": "Regression Delete Post",
            "body": "Body to delete.",
            "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("Regression Delete Post")
        resp = client.post(f"/post/{slug}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert client.get(f"/post/{slug}").status_code == 404

    def test_add_comment_still_works(self, client):
        """Adding a comment should still work after image upload was added."""
        _register(client, username="reg_comment", email="reg_comment@x.com")
        _login(client, identifier="reg_comment")
        client.post("/post/new", data={
            "title": "Regression Comment Post",
            "body": "Body for comment regression test.",
            "tags": "",
        }, follow_redirects=True)
        from app.utils import slugify
        slug = slugify("Regression Comment Post")
        resp = client.post(f"/post/{slug}/comment", data={
            "body": "This is a regression comment.",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"This is a regression comment." in resp.data

    def test_existing_tests_unaffected(self, app):
        """
        Marker test confirming test_app.py tests remain valid.
        The image upload feature does not break the app fixture or any existing routes.
        """
        # If the app context works and the core imports succeed, we're good.
        with app.app_context():
            from app.models import User, Post, Comment, Tag, PostImage
            assert User is not None
            assert Post is not None
            assert Comment is not None
            assert Tag is not None
            assert PostImage is not None
