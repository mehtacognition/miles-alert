"""Send iMessages via AppleScript."""
import subprocess


def send_imessage(phone_number: str, message: str) -> bool:
    """Send an iMessage to the given phone number.

    Raises RuntimeError if sending fails.
    """
    escaped_message = message.replace('"', '\\"')
    escaped_phone = phone_number.replace('"', '\\"')

    applescript = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{escaped_phone}" of targetService
        send "{escaped_message}" to targetBuddy
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", applescript],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to send iMessage: {result.stderr}")

    return True
