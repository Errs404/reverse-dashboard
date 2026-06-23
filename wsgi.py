import os

from reverse_dashboard import create_app, socketio

app = create_app()

if __name__ == "__main__":
    socketio.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
