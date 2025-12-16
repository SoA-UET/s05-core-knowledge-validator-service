# NOTE: you can modify this file as appropriate.

from flask import Blueprint
from flask_restx import Api

v1 = Blueprint("v1", __name__, url_prefix="/api/v1")

_api = Api(
    v1,
    title='Version 1',
    version='1',
    description='The first stable version.',
    authorizations={
        "Bearer Auth": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "JWT Bearer token. Format: 'Bearer <token>'"
        }
    },
    security="Bearer Auth",
)

from .conversations import api as conversations_api
from .partner_updates import api as partner_updates_api

_api.add_namespace(conversations_api)
_api.add_namespace(partner_updates_api)
