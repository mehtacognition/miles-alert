"""Tests for iMessage sending."""
from unittest.mock import patch, MagicMock
import pytest
from imessage import send_imessage


@patch("imessage.subprocess.run")
def test_send_imessage_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    result = send_imessage("+15551234567", "Test message")
    assert result is True
    mock_run.assert_called_once()


@patch("imessage.subprocess.run")
def test_send_imessage_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stderr="AppleScript error")
    with pytest.raises(RuntimeError, match="Failed to send"):
        send_imessage("+15551234567", "Test message")


@patch("imessage.subprocess.run")
def test_send_imessage_escapes_quotes(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    send_imessage("+15551234567", 'Message with "quotes"')
    call_args = mock_run.call_args[0][0]
    script = call_args[2]  # osascript -e <script>
    assert '\\"' in script or "quotes" in script
