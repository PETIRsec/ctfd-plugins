import json
import random
import threading
from urllib.parse import urlparse

import requests
from flask import Blueprint, render_template, request
from sqlalchemy import event

from CTFd.models import Challenges, Solves, Teams, Users, db
from CTFd.plugins import register_plugin_assets_directory, register_admin_plugin_menu_bar
from CTFd.utils import get_config, set_config
from CTFd.utils.decorators import admins_only
from CTFd.utils.logging import log

# Create Blueprint for plugin routes
discord_webhook_bp = Blueprint(
    "discord_webhook", __name__, url_prefix="/discord-webhook"
)


def send_discord_webhook(webhook_url, content, username="CTFd", avatar_url=None):
    """Send a webhook to Discord"""
    try:
        payload = {
            "content": content,
            "username": username
        }
        if avatar_url:
            payload["avatar_url"] = avatar_url
        
        # Validate webhook URL
        parsed = urlparse(webhook_url)
        if parsed.scheme not in ("http", "https"):
            log("discord_webhook", "Invalid webhook URL scheme")
            return False
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        log("discord_webhook", f"Failed to send webhook: {e}")
        return False
    except Exception as e:
        log("discord_webhook", f"Error sending webhook: {e}")
        return False


def get_category_emojis(category):
    """Get emojis for a category from config"""
    emojis_config = get_config("discord_webhook_category_emojis", default="{}")
    try:
        category_emojis = json.loads(emojis_config)
        return category_emojis.get(category, [])
    except (json.JSONDecodeError, TypeError):
        return []


def format_announcement(template, user_name, chal_name, category=None, is_first_blood=False):
    """Format announcement string with variables"""
    emojis = get_category_emojis(category) if category else []
    emoji_string = random.choice(emojis) if emojis else ""
    
    announcement = template.replace("{user_name}", user_name)
    announcement = announcement.replace("{chal_name}", chal_name)
    announcement = announcement.replace("{emojis}", emoji_string)
    
    return announcement


def handle_solve_webhook(app, solve_id, challenge_id, user_id, team_id):
    """Handle sending webhook for a solve"""
    # Use the app context in this thread
    with app.app_context():
        # Get webhook URL
        webhook_url = get_config("discord_webhook_url", default="")
        if not webhook_url:
            return  # No webhook configured, skip
        
        # Get challenge details
        challenge = Challenges.query.filter_by(id=challenge_id).first()
        if not challenge:
            return
        
        # Get user/team name
        user = Users.query.filter_by(id=user_id).first()
        user_name = user.name if user else "Unknown"
        
        if team_id:
            team = Teams.query.filter_by(id=team_id).first()
            if team:
                user_name = team.name
        
        chal_name = challenge.name
        category = challenge.category
        
        # Check if this is first blood (count solves for this challenge)
        solve_count = Solves.query.filter_by(challenge_id=challenge_id).count()
        is_first_blood = solve_count == 1
        
        # Send first blood announcement
        if is_first_blood:
            first_blood_template = get_config(
                "discord_webhook_first_blood_template",
                default=":knife::drop_of_blood: First Blood for challenge **{chal_name}** goes to **{user_name}**! {emojis}"
            )
            announcement = format_announcement(
                first_blood_template, user_name, chal_name, category, is_first_blood=True
            )
            
            # Send webhook (no need for another thread, we're already in a background thread)
            send_discord_webhook(webhook_url, announcement)
        
        # Send all solves announcement if enabled
        announce_all = get_config("discord_webhook_announce_all", default="false")
        if announce_all == "true":
            solve_template = get_config(
                "discord_webhook_solve_template",
                default="**{user_name}** just solved **{chal_name}**! {emojis}"
            )
            announcement = format_announcement(
                solve_template, user_name, chal_name, category, is_first_blood=False
            )
            
            # Send webhook (no need for another thread, we're already in a background thread)
            send_discord_webhook(webhook_url, announcement)


# Admin routes
@discord_webhook_bp.route("/admin/config", methods=["GET", "POST"])
@admins_only
def admin_config():
    """Admin configuration page"""
    if request.method == "POST":
        webhook_url = request.form.get("webhook_url", "").strip()
        first_blood_template = request.form.get("first_blood_template", "").strip()
        solve_template = request.form.get("solve_template", "").strip()
        announce_all = request.form.get("announce_all", "false")
        category_emojis = request.form.get("category_emojis", "{}").strip()
        
        # Validate webhook URL if provided
        if webhook_url:
            parsed = urlparse(webhook_url)
            if parsed.scheme not in ("http", "https"):
                return render_template(
                    "plugins/discord_webhook/config.html",
                    error="Invalid webhook URL. Must start with http:// or https://",
                    webhook_url="",
                    first_blood_template=get_config(
                        "discord_webhook_first_blood_template",
                        default=":knife::drop_of_blood: First Blood for challenge **{chal_name}** goes to **{user_name}**! {emojis}"
                    ),
                    solve_template=get_config(
                        "discord_webhook_solve_template",
                        default="**{user_name}** just solved **{chal_name}**! {emojis}"
                    ),
                    announce_all=get_config("discord_webhook_announce_all", default="false"),
                    category_emojis=get_config("discord_webhook_category_emojis", default="{}")
                )
        
        # Validate JSON for category emojis
        if category_emojis:
            try:
                json.loads(category_emojis)
            except json.JSONDecodeError:
                return render_template(
                    "plugins/discord_webhook/config.html",
                    error="Invalid JSON format for category emojis",
                    webhook_url=webhook_url,
                    first_blood_template=first_blood_template,
                    solve_template=solve_template,
                    announce_all=announce_all,
                    category_emojis=category_emojis
                )
        
        # Save configuration
        set_config("discord_webhook_url", webhook_url)
        set_config("discord_webhook_first_blood_template", first_blood_template)
        set_config("discord_webhook_solve_template", solve_template)
        set_config("discord_webhook_announce_all", announce_all)
        set_config("discord_webhook_category_emojis", category_emojis)
        
        return render_template(
            "plugins/discord_webhook/config.html",
            success="Configuration saved successfully!",
            webhook_url=webhook_url,
            first_blood_template=first_blood_template,
            solve_template=solve_template,
            announce_all=announce_all,
            category_emojis=category_emojis
        )
    
    # GET request - show current config
    webhook_url = get_config("discord_webhook_url", default="")
    first_blood_template = get_config(
        "discord_webhook_first_blood_template",
        default=":knife::drop_of_blood: First Blood for challenge **{chal_name}** goes to **{user_name}**! {emojis}"
    )
    solve_template = get_config(
        "discord_webhook_solve_template",
        default="**{user_name}** just solved **{chal_name}**! {emojis}"
    )
    announce_all = get_config("discord_webhook_announce_all", default="false")
    category_emojis = get_config("discord_webhook_category_emojis", default="{}")
    
    return render_template(
        "plugins/discord_webhook/config.html",
        webhook_url=webhook_url,
        first_blood_template=first_blood_template,
        solve_template=solve_template,
        announce_all=announce_all,
        category_emojis=category_emojis
    )


def load(app):
    """Main plugin load function"""
    # Register blueprint
    app.register_blueprint(discord_webhook_bp)
    
    # Register admin menu item
    register_admin_plugin_menu_bar(
        "Discord Webhook",
        "/discord-webhook/admin/config"
    )
    
    # Register SQLAlchemy event listener for Solves
    @event.listens_for(Solves, "after_insert")
    def receive_after_insert(mapper, connection, target):
        """Listen for new solves and send webhooks"""
        # Extract IDs to pass to background thread (avoid passing ORM objects)
        solve_id = target.id
        challenge_id = target.challenge_id
        user_id = target.user_id
        team_id = target.team_id if hasattr(target, 'team_id') else None
        
        # Use a background thread to avoid blocking the database transaction
        thread = threading.Thread(
            target=handle_solve_webhook,
            args=(app, solve_id, challenge_id, user_id, team_id)
        )
        thread.daemon = True
        thread.start()
    
    print(" * Loaded plugin: Discord Webhook")

