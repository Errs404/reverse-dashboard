from __future__ import annotations

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from .config import Config

socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)
    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)

    CORS(app, supports_credentials=True)
    socketio.init_app(app)
    from .terminal_socket import register_terminal_socket
    register_terminal_socket(socketio)

    from .blueprints.auth import bp as auth_bp
    from .blueprints.pages import bp as pages_bp
    from .blueprints.api import bp as api_bp
    from .blueprints.files import bp as files_bp
    from .blueprints.docker import bp as docker_bp
    from .blueprints.settings import bp as settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(files_bp, url_prefix="/api/files")
    app.register_blueprint(docker_bp, url_prefix="/api/docker")
    app.register_blueprint(settings_bp, url_prefix="/api/settings")

    @app.context_processor
    def inject_globals():
        from .extensions import current_user
        return {
            "app_name": app.config["DASHBOARD_NAME"],
            "app_version": app.config["VERSION"],
            "current_user": current_user(),
            "file_root": str(app.config["HOST_ROOT"]),
            "files_writable": not app.config.get("FILES_READ_ONLY", False),
        }

    return app
