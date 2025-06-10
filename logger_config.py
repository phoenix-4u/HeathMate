# healthmate_app/logger_config.py
import logging
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "healthmate_app.log" # Default if not in .env

# Read configuration from environment variables
log_level_name = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
log_file_path = os.getenv("LOG_FILE_PATH", DEFAULT_LOG_FILE)

# --- Logger Setup ---

# Get the numeric logging level
numeric_log_level = getattr(logging, log_level_name, None)
if not isinstance(numeric_log_level, int):
    print(f"Warning: Invalid LOG_LEVEL '{log_level_name}'. Defaulting to {DEFAULT_LOG_LEVEL}.")
    numeric_log_level = getattr(logging, DEFAULT_LOG_LEVEL)


# Create a custom logger

logger = logging.getLogger("healthmate_app")
logger.setLevel(numeric_log_level) # Set the minimum level for the logger itself

# --- Console Handler ---
# This handler will output logs to the console (stdout)
console_handler = logging.StreamHandler(sys.stdout)

# Set the level for console logs
console_log_level_name = "INFO"
numeric_console_log_level = getattr(logging, console_log_level_name, logging.INFO)

# Ensure console doesn't show less than what the main logger is set to, if main logger is stricter
if numeric_log_level > numeric_console_log_level:
    console_handler.setLevel(numeric_log_level)
else:
    console_handler.setLevel(numeric_console_log_level)


# Create a formatter for console logs (simple format)
console_formatter = logging.Formatter(
    fmt="%(levelname)s: %(message)s (%(filename)s:%(lineno)d)"
)
console_handler.setFormatter(console_formatter)

# Add the console handler to the logger
if not logger.handlers or not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    logger.addHandler(console_handler)


# --- File Handler ---
# This handler will output logs to a file
try:
    # Ensure the directory for the log file exists if a path is specified
    log_file_dir = os.path.dirname(log_file_path)
    if log_file_dir and not os.path.exists(log_file_dir):
        os.makedirs(log_file_dir, exist_ok=True)

    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8') # 'a' for append
    file_handler.setLevel(numeric_log_level) # File handler logs everything from the logger's set level

    # Create a more detailed formatter for file logs
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    # Add the file handler to the logger
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        logger.addHandler(file_handler)

except IOError as e:
    logger.error(f"Failed to configure file logging to '{log_file_path}': {e}", exc_info=True)
    # Fallback to console only if file handler fails
    if 'file_handler' in locals() and file_handler in logger.handlers:
        logger.removeHandler(file_handler)


# --- Initial Log Message ---
# This will be logged by both handlers according to their levels
logger.info(f"Logger initialized. Main log level: {log_level_name}. Console level: {logging.getLevelName(console_handler.level)}. File logging to: {log_file_path}")
logger.debug("This is a debug message (will appear in file if LOG_LEVEL=DEBUG, not on console unless console also DEBUG).")



if __name__ == "__main__":
    # Test the logger configuration
    logger.debug("This is a debug message from test.")
    logger.info("This is an info message from test.")
    logger.warning("This is a warning message from test.")
    logger.error("This is an error message from test.")
    logger.critical("This is a critical message from test.")
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("Test exception caught!")
    
    print(f"\nCheck the console for INFO+ messages and '{log_file_path}' for {log_level_name}+ messages.")