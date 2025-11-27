# Discord Webhook Plugin for CTFd

A CTFd plugin that sends Discord webhook notifications when challenges are solved, including first blood announcements.

## Features

- **First Blood Announcements**: Automatically sends Discord webhooks when a challenge gets its first solve
- **All Solves Announcements**: Optional configuration to announce all solves (not just first blood)
- **Customizable Templates**: Configure announcement messages with variables
- **Category Emojis**: Support for category-specific emojis in announcements
- **No Polling Required**: Event-driven, no need for external bots to poll the API
- **No Authentication Issues**: Works independently of API token authentication

## Installation

1. Place the plugin folder in `CTFd/plugins/discord_webhook/`
2. Install dependencies: `pip install -r requirements.txt`
3. Restart CTFd
4. Configure the webhook URL in the admin panel

## Configuration

Navigate to **Plugins > Discord Webhook** in the admin panel to configure:

- **Discord Webhook URL**: Your Discord webhook URL
- **First Blood Template**: Message template for first blood announcements
- **Solve Template**: Message template for regular solve announcements
- **Announce All Solves**: Toggle to announce all solves or only first bloods
- **Category Emojis**: JSON mapping of category names to emoji arrays

## Template Variables

Available variables in announcement templates:

- `{user_name}`: The name of the user (or team) who solved the challenge
- `{chal_name}`: The name of the challenge that was solved
- `{emojis}`: Random emoji from the category's emoji list (if configured)

## Example Configuration

**First Blood Template:**
```
:knife::drop_of_blood: First Blood for challenge **{chal_name}** goes to **{user_name}**! {emojis}
```

**Category Emojis:**
```json
{
    "web": [":globe_with_meridians:"],
    "crypto": [":sob::closed_lock_with_key:"],
    "pwn": [":bug:"],
    "rev": [":rewind:"],
    "forensics": [":mag:"],
    "osint": [":detective:"],
    "misc": [":jigsaw:"]
}
```

## How It Works

The plugin hooks into CTFd's challenge solve mechanism. When a challenge is solved:

1. The plugin checks if this is the first solve (first blood)
2. If it's a first blood, it sends a webhook with the first blood template
3. If "Announce All Solves" is enabled, it also sends a webhook with the solve template
4. Webhooks are sent asynchronously in background threads to avoid blocking

## Advantages Over Polling Bot

- **No API Authentication Required**: Works without API tokens
- **Real-time**: Instant notifications, no polling delay
- **No External Service**: No need to run a separate bot service
- **Integrated**: Managed directly in CTFd admin panel
- **Reliable**: No risk of missing events due to polling gaps

## Requirements

- CTFd 3.x
- Python 3.7+
- requests library (>=2.28.0)

## License

This plugin is provided as-is for use with CTFd.

