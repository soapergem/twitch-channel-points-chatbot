import hashlib
import hmac
import logging
import os
import random
import threading
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pytz
import requests
from google.cloud import firestore
from websocket import WebSocketApp

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
MIN_RANGE = int(os.getenv("MIN_RANGE", 1))
MAX_RANGE = int(os.getenv("MAX_RANGE"))

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
logging.basicConfig()


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


def regenerate_token(token_data, document_id=None):
    refresh_token = token_data.get("refresh_token")
    url = (
        "https://id.twitch.tv/oauth2/token?client_id="
        + quote_plus(CLIENT_ID)
        + "&client_secret="
        + quote_plus(CLIENT_SECRET)
        + "&refresh_token="
        + quote_plus(refresh_token)
        + "&grant_type=refresh_token&redirect_uri="
        + quote_plus(REDIRECT_URI)
    )
    result = requests.post(url)
    result.raise_for_status()
    response = result.json()

    # get the tokens and metadata from the oauth response
    access_token = response.get("access_token")
    scopes = response.get("scope")
    expires_in = response.get("expires_in")

    # calculate the expiration timestamp
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    broadcaster_id = token_data.get("broadcaster_id")
    username = token_data.get("username")
    store_oauth_token(
        access_token,
        refresh_token,
        scopes,
        expires_at,
        broadcaster_id,
        username,
        document_id,
    )
    return access_token


def lookup_token(broadcaster_id):
    db = firestore.Client()
    tokens = db.collection("auth-tokens")
    result = tokens.where("broadcaster_id", "==", broadcaster_id)
    document = result.get()[0]
    token_data = document.to_dict()
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    if token_data.get("expires_at") < now:
        access_token = regenerate_token(token_data, document.id)
    else:
        access_token = token_data.get("access_token")
    return access_token


def lookup_token_and_username():
    db = firestore.Client()
    tokens = db.collection("auth-tokens")
    result = tokens.where("scopes", "array_contains", "chat:edit")
    document = result.get()[0]
    token_data = document.to_dict()
    username = token_data.get("username")
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    if token_data.get("expires_at") < now:
        access_token = regenerate_token(token_data, document.id)
    else:
        access_token = token_data.get("access_token")
    return access_token, username


def get_active_subscription(broadcaster_id):
    db = firestore.Client()
    subscriptions = db.collection("subscriptions")
    result = subscriptions.where("broadcaster_id", "==", broadcaster_id)
    return next((x.to_dict() for x in result.get()), None)


def get_random_quote():
    random_id = random.randint(MIN_RANGE, MAX_RANGE)
    db = firestore.Client()
    quotes = db.collection("lotr-quotes")
    result = quotes.where("id", "==", random_id)
    documents = result.get()
    if not documents:
        return None
    quote_data = documents[0].to_dict()
    return quote_data.get("quote") + " -" + quote_data.get("speaker")


def calculate_message_signature(secret, message_id, timestamp, request_data):
    hmac_message = message_id + timestamp + request_data
    return (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            hmac_message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
    )


def type_quote_in_chat(username, channel, quote, access_token):
    ws = WebSocketApp(
        "wss://irc-ws.chat.twitch.tv:443",
        on_open=lambda ws: on_open(ws, username, channel, quote, access_token),
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=70, ping_timeout=10)


def on_message(ws, message):
    if "PING :tmi.twitch.tv" in message:
        ws.send("PONG :tmi.twitch.tv")


def on_error(ws, error):
    LOGGER.error(f"Error in websocket: {error}")


def on_close(ws, *args):
    LOGGER.info("Chat closed")


def on_open(ws, username, channel, message, access_token):
    def run(*args):
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        ws.send(f"PASS oauth:{access_token}")
        logger.info(f"PASS oauth:{access_token}")
        ws.send(f"NICK {username}")
        logger.info(f"NICK {username}")
        ws.send(f"JOIN #{channel}")
        logger.info(f"JOIN #{channel}")
        ws.send(f"PRIVMSG #{channel} :{message}")
        logger.info(f"PRIVMSG #{channel} :{message}")
        ws.keep_running = False

    threading.Thread(None, run).start()


def mark_as_fulfilled(redemption_id, broadcaster_id, reward_id, access_token):
    url = (
        "https://api.twitch.tv/helix/channel_points/custom_rewards/redemptions"
        + "?id="
        + quote_plus(redemption_id)
        + "&broadcaster_id="
        + quote_plus(broadcaster_id)
        + "&reward_id="
        + quote_plus(reward_id)
    )
    data = {"status": "FULFILLED"}
    LOGGER.info(f"{url}\t{data}")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": CLIENT_ID,
    }
    result = requests.patch(url, headers=headers, json=data)
    try:
        result.raise_for_status()
    except:
        LOGGER.error(f"Could not mark as fulfilled: {result.text}")


def handler(request):
    # look up the secret from the broadcaster id (along with other subscription data)
    LOGGER.info(request.data.decode("utf-8"))
    broadcaster_id = (
        request.json.get("subscription", {})
        .get("condition", {})
        .get("broadcaster_user_id")
    )
    active_subscription = get_active_subscription(broadcaster_id)
    if not active_subscription:
        LOGGER.error("Unable to find active subscription")
        return "Invalid subscription", 404
    else:
        connected_rewards = active_subscription.get("reward_ids", [])

    # validate the message signature
    secret = active_subscription.get("secret")
    message_id = request.headers.get("Twitch-Eventsub-Message-Id")
    timestamp = request.headers.get("Twitch-Eventsub-Message-Timestamp")
    response_data = request.data.decode("utf-8")

    actual_signature = calculate_message_signature(
        secret, message_id, timestamp, response_data
    )
    expected_signature = request.headers.get("Twitch-Eventsub-Message-Signature")
    if expected_signature != actual_signature:
        LOGGER.error(f"Signature mismatch: {actual_signature} vs {expected_signature}")
        LOGGER.warning(f"Broadcaster: {broadcaster_id}; Headers: {request.headers}")
        return "Forbidden", 403

    # delegate two different message types
    message_type = request.headers.get("Twitch-Eventsub-Message-Type")
    if message_type == "webhook_callback_verification":
        challenge = request.json.get("challenge")
        LOGGER.info(f"Challenge responded with {challenge}")
        return challenge, 200, {"Content-Type": "text/plain"}
    elif message_type == "notification":
        redemption_id = request.json.get("event", {}).get("id")
        reward_id = request.json.get("event", {}).get("reward", {}).get("id")
        if reward_id in connected_rewards:
            quote = get_random_quote()
            if not quote:
                LOGGER.error("No LotR quotes have been configured")
                quote = "No LotR quotes have been configured"
            channel = request.json.get("event", {}).get("broadcaster_user_login")
            chat_token, username = lookup_token_and_username()
            type_quote_in_chat(username, channel, quote, chat_token)
            # access_token = lookup_token(broadcaster_id)
            # mark_as_fulfilled(redemption_id, broadcaster_id, reward_id, access_token)
        else:
            LOGGER.info("Reward not connected to subscription")
        return "", 204
    else:
        LOGGER.error(f"Message Type: {message_type}")
        return "Unknown message type", 501
