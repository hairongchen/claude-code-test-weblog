import os
from flask import Flask
from .extensions import db, migrate, login_manager
from .utils import render_markdown
from .quotes import get_daily_quote


def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("config.Config")

    # Ensure instance folder exists
    os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)   # enables `flask db` CLI commands
    login_manager.init_app(app)

    # Jinja2 filter for Markdown rendering
    app.jinja_env.filters["markdown"] = render_markdown

    # Inject daily quote into every template context
    @app.context_processor
    def inject_quote():
        return {"daily_quote": get_daily_quote()}

    from .auth import auth_bp
    from .blog import blog_bp
    from .games import games_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(games_bp)

    with app.app_context():
        # create_all() only creates missing tables — never drops or alters existing data
        db.create_all()

    return app
