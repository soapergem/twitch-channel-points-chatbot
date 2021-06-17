import logging
import os
import random
import string
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pytz
import requests
from google.cloud import firestore

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SELECT_URI = os.getenv("SELECT_URI")
WEBHOOK_URI = os.getenv("WEBHOOK_URI")
SECRET_LENGTH = int(os.getenv("SECRET_LENGTH", 32))

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


def generate_secret(n_characters):
    return "".join(
        random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits)
        for _ in range(n_characters)
    )


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


def get_rewards(broadcaster_id, access_token):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
    }
    url = f"https://api.twitch.tv/helix/channel_points/custom_rewards?broadcaster_id={broadcaster_id}"
    result = requests.get(url, headers=headers)
    result.raise_for_status()
    response = result.json()
    LOGGER.info(response)
    return {
        x.get("id"): {
            "title": x.get("title"),
            "prompt": x.get("prompt"),
            "cost": x.get("cost"),
        }
        for x in response.get("data")
    }


def get_active_subscription(broadcaster_id):
    db = firestore.Client()
    subscriptions = db.collection("subscriptions")
    result = subscriptions.where("broadcaster_id", "==", broadcaster_id)
    return next((x.to_dict() for x in result.get()), None)


def get_app_token(scopes):
    url = (
        "https://id.twitch.tv/oauth2/token?client_id="
        + quote_plus(CLIENT_ID)
        + "&client_secret="
        + quote_plus(CLIENT_SECRET)
        + "&scope="
        + quote_plus(" ".join(scopes))
        + "&grant_type=client_credentials"
    )
    result = requests.post(url)
    result.raise_for_status()
    response = result.json()
    return response.get("access_token")


def subscribe(broadcaster_id, secret, scopes):
    app_token = get_app_token(scopes)
    url = "https://api.twitch.tv/helix/eventsub/subscriptions"
    data = {
        "type": "channel.channel_points_custom_reward_redemption.add",
        "version": "1",
        "condition": {"broadcaster_user_id": str(broadcaster_id),},
        "transport": {"method": "webhook", "callback": WEBHOOK_URI, "secret": secret,},
    }
    headers = {
        "Authorization": f"Bearer {app_token}",
        "Client-Id": CLIENT_ID,
    }
    result = requests.post(url, json=data, headers=headers)
    result.raise_for_status()
    response = result.json()

    subscription_id = response.get("data")[0].get("id")
    return subscription_id


def unsubscribe(subscription_id, scopes):
    app_token = get_app_token(scopes)
    url = f"https://api.twitch.tv/helix/eventsub/subscriptions?id={subscription_id}"
    headers = {
        "Authorization": f"Bearer {app_token}",
        "Client-Id": CLIENT_ID,
    }
    result = requests.delete(url, headers=headers)
    result.raise_for_status()


def update_subscription_record(subscription_data):
    db = firestore.Client()
    broadcaster_id = subscription_data.get("broadcaster_id")
    subscriptions = db.collection("subscriptions")
    result = subscriptions.where("broadcaster_id", "==", broadcaster_id)
    documents = result.get()
    document_id = documents[0].id if documents else None
    if document_id:
        subscriptions.document(document_id).update(subscription_data)
    else:
        subscriptions.add(subscription_data)


def delete_subscription_record(subscription_id):
    db = firestore.Client()
    subscriptions = db.collection("subscriptions")
    result = subscriptions.where("subscription_id", "==", subscription_id)
    document = result.get()[0]
    subscriptions.document(document.id).delete()


def generate_html(broadcaster_id, rewards, connected_rewards, message_banner):
    html = "<html>"
    html += "<head><title>Lord of the Rings Channel Points</title>"
    if message_banner:
        url = f"{SELECT_URI}?broadcaster_id={broadcaster_id}"
        html += '<meta http-equiv="refresh" content="5;url=' + url + '" />'
    html += "</head><body>"
    html += '<table border="0" cellspacing="0" cellpadding="2">'
    if message_banner:
        html += '<thead><tr><th colspan="2">' + message_banner + "</th></tr></thead>"
    html += "<tbody>"
    for reward_id, reward in rewards.items():
        points = str(reward.get("cost"))
        url = f"{SELECT_URI}?broadcaster_id={broadcaster_id}&reward_id={reward_id}"
        verb = "Disconnect" if reward_id in connected_rewards else "Connect"
        html += "<tr><td>" + reward.get("title") + "</td>"
        html += '<td><a href="' + url + '">' + verb + "</a></td></tr>"
        html += (
            '<tr><td colspan="2">' + reward.get("prompt") + f" ({points} pts)</td></tr>"
        )
    html += "</tbody></table>"
    html += "</body></html>"
    LOGGER.info(html)
    return html


def handler(request):
    broadcaster_id = request.args.get("broadcaster_id")
    access_token = lookup_token(broadcaster_id)
    rewards = get_rewards(broadcaster_id, access_token)

    message_banner = None
    active_subscription = get_active_subscription(broadcaster_id)
    if active_subscription:
        LOGGER.info(active_subscription)
        connected_rewards = active_subscription.get("reward_ids", [])
    else:
        connected_rewards = []

    reward_id = request.args.get("reward_id")
    LOGGER.info(f"Reward ID: {reward_id}")
    app_scopes = ["channel:read:redemptions", "channel:manage:redemptions"]

    if reward_id:
        if reward_id not in rewards:
            message_banner = "Invalid Reward Selected"
        elif not active_subscription:
            # subscribe and insert
            reward_name = rewards[reward_id].get("title")
            message_banner = f"Successfully connected reward: {reward_name}"
            secret = generate_secret(SECRET_LENGTH)
            active_subscription = {
                "reward_ids": [reward_id],
                "broadcaster_id": broadcaster_id,
                "secret": secret,
            }
            # might be overkill to insert this early, but just trying to beat a race condition
            update_subscription_record(active_subscription)
            subscription_id = subscribe(broadcaster_id, secret, app_scopes)
            active_subscription["subscription_id"] = subscription_id
            connected_rewards.append(reward_id)
            update_subscription_record(active_subscription)
        elif reward_id not in connected_rewards:
            # update record only
            reward_name = rewards[reward_id].get("title")
            message_banner = f"Successfully connected reward: {reward_name}"
            connected_rewards.append(reward_id)
            active_subscription["reward_ids"] = connected_rewards
            update_subscription_record(active_subscription)
        elif len(connected_rewards) > 1:
            # update record only
            reward_name = rewards[reward_id].get("title")
            message_banner = f"Successfully disconnected reward: {reward_name}"
            connected_rewards = [x for x in connected_rewards if x != reward_id]
            active_subscription["reward_ids"] = connected_rewards
            update_subscription_record(active_subscription)
        else:
            # unsubscribe and delete
            reward_name = rewards[reward_id].get("title")
            message_banner = f"Successfully disconnected reward: {reward_name}"
            connected_rewards = [x for x in connected_rewards if x != reward_id]
            subscription_id = active_subscription.get("subscription_id")
            unsubscribe(subscription_id, app_scopes)
            delete_subscription_record(subscription_id)

    # display HTML to let the user select which reward
    return generate_html(broadcaster_id, rewards, connected_rewards, message_banner)
