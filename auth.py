import logging
import os
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import flask
import requests
from google.cloud import firestore

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SELECT_URI = os.getenv("SELECT_URI")

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
logging.basicConfig()


def respond_to_auth_code_request(auth_code):
    url = (
        "https://id.twitch.tv/oauth2/token?client_id="
        + quote_plus(CLIENT_ID)
        + "&client_secret="
        + quote_plus(CLIENT_SECRET)
        + "&code="
        + quote_plus(auth_code)
        + "&grant_type=authorization_code&redirect_uri="
        + quote_plus(REDIRECT_URI)
    )
    result = requests.post(url)
    result.raise_for_status()
    return result.json()


def retrieve_user_data(access_token):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
    }

    url = "https://api.twitch.tv/helix/users"
    result = requests.get(url, headers=headers)
    result.raise_for_status()
    response = result.json()

    LOGGER.info(response)

    entry = response.get("data", [])[0]
    broadcaster_id = entry.get("id")
    username = entry.get("login")
    return broadcaster_id, username


def store_oauth_token(
    access_token,
    refresh_token,
    scopes,
    expires_at,
    broadcaster_id,
    username,
    document_id=None,
):
    db = firestore.Client()
    tokens = db.collection("auth-tokens")
    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "scopes": scopes,
        "expires_at": expires_at,
        "broadcaster_id": broadcaster_id,
        "username": username,
    }
    if document_id:
        tokens.document(document_id).update(token_data)
    else:
        tokens.add(token_data)


def handler(request):
    # complete the oauth code grant flow
    auth_code = request.args.get("code")
    response = respond_to_auth_code_request(auth_code)

    # get the tokens and metadata from the oauth response
    access_token = response.get("access_token")
    refresh_token = response.get("refresh_token")
    scopes = response.get("scope")
    expires_in = response.get("expires_in")

    # calculate the expiration timestamp
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # look up the broadcaster id and username
    broadcaster_id, username = retrieve_user_data(access_token)

    # store auth tokens
    store_oauth_token(
        access_token, refresh_token, scopes, expires_at, broadcaster_id, username
    )

    if "channel:read:redemptions" in scopes:
        LOGGER.info("Redirecting user to reward selection")
        url = f"{SELECT_URI}?broadcaster_id={broadcaster_id}"
        return flask.jsonify({"broadcaster_id": broadcaster_id}), 307, {"Location": url}
    else:
        LOGGER.info("Storing chat token only")
        return flask.jsonify({"success": True}), 200
