import io
import json
import logging
import sys
from datetime import datetime


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

# Configure standard logging
# Configure standard logging to file and console
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("application.log", encoding="utf-8"),
        logging.StreamHandler(_get_safe_console_stream())
    ]
)
logger = logging.getLogger("CookingApp")

class DebugLogger:
    def __init__(self):
        self.logger = logger

    def log_input(self, label, value):
        self.logger.info(f"[INPUT] {label}: {value}")

    def log_step(self, message):
        self.logger.info(f"[STEP] {message}")

    def log_data(self, label, data):
        self.logger.info(f"[DATA] {label}: {json.dumps(data, default=str)}")

    def log_calculation(self, label, formula, inputs, result, unit=""):
        self.logger.info(f"[CALC] {label}: {formula} | Inputs: {inputs} | Result: {result} {unit}")

    def log_success(self, message):
        self.logger.info(f"[SUCCESS] {message}")

    def log_error(self, message):
        self.logger.error(f"[ERROR] {message}")

    def log_warning(self, message):
        self.logger.warning(f"[WARNING] {message}")

    def log_result(self, label, value, unit=""):
        self.logger.info(f"[RESULT] {label}: {value} {unit}")

    def log_subsection(self, message):
        self.logger.info(f"[SUBSECTION] {message}")

    def log_dataframe(self, label, df, max_rows=10):
        self.logger.info(f"[DATAFRAME] {label}:\n{df.head(max_rows).to_string()}")

    def log_table(self, label, data, headers=None):
        header_str = f" | Headers: {headers}" if headers else ""
        self.logger.info(f"[TABLE] {label}{header_str}: {json.dumps(data, default=str)}")

    def log_intermediate_result(self, label, value):
        self.logger.info(f"[INTERMEDIATE] {label}: {value}")

    def get_log_path(self):
        """Return path to current log file"""
        return "application.log"

_debug_logger_instance = DebugLogger()

def get_logger(session_id=None):
    return _debug_logger_instance

def log_request_start(path, method, data):
    logger.info(f"Request started: {method} {path} | Data: {json.dumps(data, default=str)}")

def log_session_data(session):
    logger.info(f"Session data: {dict(session)}")
