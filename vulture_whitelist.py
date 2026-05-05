# vulture_whitelist.py
# Whitelist for the vulture dead code detector (tox -e reaper).
# Add false-positive entries here — code that appears unused but is needed.
# Format: function_name  # reason

# Context manager protocol methods (required by Python, flagged as unused params)
exc_type = None  # noqa: unused — __exit__ protocol
exc_val = None  # noqa: unused — __exit__ protocol
exc_tb = None  # noqa: unused — __exit__ protocol
