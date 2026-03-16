import io
import json
import logging
import sys


def _get_safe_console_stream():
    """
    Return a console stream that won't raise UnicodeEncodeError when logging emojis.
    Falls back to the existing stream if wrapping fails.
    """
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"

    # If errors are already handled, reuse the stream
    if getattr(stream, "errors", None) == "replace":
        return stream

    if hasattr(stream, "buffer"):
        try:
            return io.TextIOWrapper(stream.buffer, encoding=encoding, errors="replace")
        except Exception:
            pass

    return stream

def _configure_logging():
    import os
    from logging.handlers import RotatingFileHandler

    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    # Always add rotating file handler
    file_handler = RotatingFileHandler(
        "application.log",
        maxBytes=5_000_000,   # 5 MB per file
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)

    # Only add stdout handler in non-production
    flask_env = os.environ.get("FLASK_ENV", "development").lower()
    if flask_env != "production":
        stream_handler = logging.StreamHandler(_get_safe_console_stream())
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(stream_handler)

_configure_logging()
logger = logging.getLogger("CookingApp")

class DebugLogger:
    def __init__(self):
        self.logger = logger

    def log_input(self, label, value):
        self.logger.debug(f"[INPUT] {label}: {value}")

    def log_step(self, message):
        self.logger.debug(f"[STEP] {message}")

    def log_data(self, label, data):
        self.logger.debug(f"[DATA] {label}: {json.dumps(data, default=str)}")

    def log_calculation(self, label, formula, inputs, result, unit=""):
        self.logger.debug(f"[CALC] {label}: {formula} | Inputs: {inputs} | Result: {result} {unit}")

    def log_success(self, message):
        self.logger.info(f"[SUCCESS] {message}")

    def log_error(self, message):
        self.logger.error(f"[ERROR] {message}")

    def log_warning(self, message):
        self.logger.warning(f"[WARNING] {message}")

    def log_result(self, label, value, unit=""):
        self.logger.debug(f"[RESULT] {label}: {value} {unit}")

    def log_subsection(self, message):
        self.logger.debug(f"[SUBSECTION] {message}")

    def log_dataframe(self, label, df, max_rows=10):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"[DATAFRAME] {label}:\n{df.head(max_rows).to_string()}")

    def log_table(self, label, data, headers=None):
        header_str = f" | Headers: {headers}" if headers else ""
        self.logger.debug(f"[TABLE] {label}{header_str}: {json.dumps(data, default=str)}")

    def log_intermediate_result(self, label, value):
        self.logger.debug(f"[INTERMEDIATE] {label}: {value}")

    def get_log_path(self):
        """Return path to current log file"""
        return "application.log"

_debug_logger_instance = DebugLogger()

def get_logger():
    return _debug_logger_instance

def log_request_start(path, method, data):
    logger.info(f"Request started: {method} {path} | Data: {json.dumps(data, default=str)}")

def log_session_data(session):
    logger.info(f"Session data: {dict(session)}")
