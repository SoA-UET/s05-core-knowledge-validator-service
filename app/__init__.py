"""
WARNING: Change this file if the
service does not need HTTP API
or WebSocket features.
"""

SERVICE_NAME = "Telcenter Core - Knowledge Validator Service (S05)"



from flask import Flask, url_for
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask(__name__)

app.url_map.strict_slashes = False

socketio = SocketIO(app, cors_allowed_origins="*")

CORS(app)  # Enable CORS for all routes

with app.app_context():
    from .controllers import register_api_controllers
    register_api_controllers(app, socketio)

    @app.get('/')
    def home():
        return f"""
        <html><head><title>{SERVICE_NAME}</title></head><body>
        <h1>Welcome to the {SERVICE_NAME}!</h1>
        <a href={url_for("get_api_versions")}>Here is the API documentation.</a>
        </body></html>
        """

print(app.url_map)
