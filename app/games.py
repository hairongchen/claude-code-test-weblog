from flask import Blueprint, render_template

games_bp = Blueprint("games", __name__, url_prefix="/games")


@games_bp.route("/")
def index():
    return render_template("games/index.html")


@games_bp.route("/snake")
def snake():
    return render_template("games/snake.html")


@games_bp.route("/2048")
def game_2048():
    return render_template("games/2048.html")
