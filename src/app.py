import os
import time

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from slack_sdk.errors import SlackApiError

# Load environment variables from .env when running locally
load_dotenv()

# --- Required environment variables ---

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# Comma-separated list of Slack channel IDs to broadcast into
# Example:
#   BROADCAST_CHANNEL_IDS=C01ABCDEF12,C02GHIJKL34
BROADCAST_CHANNEL_IDS = [
    cid.strip()
    for cid in (os.environ.get("BROADCAST_CHANNEL_IDS") or "").split(",")
    if cid.strip()
]

# --- Optional environment variables ---

# Comma-separated Slack user IDs allowed to broadcast.
# If empty or not set, ANY user can use /partner_broadcast.
ALLOWED_BROADCASTERS = {
    uid.strip()
    for uid in (os.environ.get("ALLOWED_BROADCASTERS") or "").split(",")
    if uid.strip()
}

# --- Slack app initialization ---

app = App(token=SLACK_BOT_TOKEN)


def user_is_allowed(user_id: str) -> bool:
    """
    If ALLOWED_BROADCASTERS is empty, any user is allowed.
    Otherwise, only listed user IDs may broadcast.
    """
    if not ALLOWED_BROADCASTERS:
        return True
    return user_id in ALLOWED_BROADCASTERS


@app.command("/partner_broadcast")
def handle_broadcast(ack, body, respond, client, logger):
    """
    Two-step broadcast:

    1) Preview (no CONFIRM prefix):
       /partner_broadcast Message text...

       -> Bot shows preview and instructions.

    2) Confirm (with CONFIRM prefix):
       /partner_broadcast CONFIRM: Message text...

       -> Bot actually broadcasts to all channels in BROADCAST_CHANNEL_IDS.
    """
    # ACK immediately so Slack is happy
    ack()

    user_id = body["user_id"]
    text_raw = (body.get("text") or "").strip()

    # Permission check
    if not user_is_allowed(user_id):
        respond("You are not allowed to use `/partner_broadcast`.")
        return

    if not text_raw:
        respond(
            "Usage:\n"
            "• Preview: `/partner_broadcast Your message here`\n"
            "• Confirm: `/partner_broadcast CONFIRM: Your message here`"
        )
        return

    # Check if this is a confirmation call
    is_confirm = False
    confirm_prefix = "CONFIRM:"
    if text_raw.upper().startswith(confirm_prefix):
        is_confirm = True
        text = text_raw[len(confirm_prefix):].strip()
    else:
        text = text_raw

    if not text:
        respond(
            "Your message is empty after the CONFIRM prefix.\n"
            "Usage: `/partner_broadcast CONFIRM: Your message here`"
        )
        return

    # No channels configured
    if not BROADCAST_CHANNEL_IDS:
        respond(
            "No broadcast channels are configured.\n\n"
            "Ask the maintainer to set BROADCAST_CHANNEL_IDS in the environment "
            "to a comma-separated list of channel IDs."
        )
        return

    # If not confirmed yet, show preview and bail
    if not is_confirm:
        channels_summary = ", ".join(BROADCAST_CHANNEL_IDS)
        respond(
            "Preview only — nothing has been sent yet.\n\n"
            f"This message:\n\n{text}\n\n"
            f"Would be sent to {len(BROADCAST_CHANNEL_IDS)} channel(s):\n"
            f"{channels_summary}\n\n"
            "If this looks correct, send:\n"
            f"`/partner_broadcast CONFIRM: {text}`"
        )
        return

    # --- Confirmed: actually broadcast ---

    sent = 0
    failed = []

    for channel_id in BROADCAST_CHANNEL_IDS:
        try:
            client.chat_postMessage(
                channel=channel_id,
                text=text,
            )
            sent += 1
            # Small sleep for safety
            time.sleep(0.2)
        except SlackApiError as e:
            logger.error(f"Failed to post to {channel_id}: {e}")
            failed.append(channel_id)
        except Exception as e:
            logger.error(f"Unexpected error posting to {channel_id}: {e}")
            failed.append(channel_id)

    msg = f"Broadcast complete. Sent to {sent} channel(s)."
    if failed:
        msg += f" Failed on {len(failed)} channel(s): {', '.join(failed)}"

    respond(msg)


if __name__ == "__main__":
    print("🚀 Partner Alert Bot is starting...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
