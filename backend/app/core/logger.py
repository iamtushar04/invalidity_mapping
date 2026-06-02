import logging
import os
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime

# 1. Create the Context Variables (The "invisible bubbles")
current_user_id: ContextVar[str] = ContextVar("current_user_id", default=None)
current_project_id: ContextVar[str] = ContextVar("current_project_id", default=None)

class DynamicRoutingHandler(logging.Handler):
    """
    A custom handler that dynamically routes logs to:
    logs/user_<id>/project_<id>.log
    logs/user_<id>/general.log
    logs/system_<date>.log
    """
    def __init__(self, base_dir="logs"):
        super().__init__()
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        # Cache file handlers to prevent opening/closing files thousands of times
        self._handlers = {}

    def _get_handler(self, user_id, project_id):
        key = (user_id, project_id)
        if key in self._handlers:
            return self._handlers[key]
        
        try:
            if user_id:
                # We have a user! Create their personal folder
                user_dir = self.base_dir / f"user_{user_id}"
                user_dir.mkdir(exist_ok=True)
                
                if project_id:
                    # We have a project! Create/Append to project log
                    file_path = user_dir / f"project_{project_id}.log"
                else:
                    # User is doing something outside a project
                    file_path = user_dir / "general.log"
            else:
                # System/startup logs (no user context yet)
                date_str = datetime.now().strftime("%Y-%m-%d")
                file_path = self.base_dir / f"system_{date_str}.log"

            # Cache safety: limit to 50 open files to prevent OS exhaustion
            if len(self._handlers) > 50:
                oldest_key = next(iter(self._handlers))
                old_h = self._handlers.pop(oldest_key)
                old_h.close()

            # Create the actual standard FileHandler for this specific file
            h = logging.FileHandler(file_path, encoding="utf-8")
            h.setFormatter(self.formatter)
            self._handlers[key] = h
            return h
            
        except Exception:
            # Absolute fallback if a folder can't be created (e.g. permission error)
            fallback = self.base_dir / "fallback.log"
            h = logging.FileHandler(fallback, encoding="utf-8")
            h.setFormatter(self.formatter)
            return h

    def emit(self, record):
        try:
            # Grab current context
            uid = current_user_id.get()
            pid = current_project_id.get()
            
            # Inject into the record so the formatter string can print it
            record.user_id = uid or "SYSTEM"
            record.project_id = pid or "GLOBAL"
            
            # Get the correct file handler for this combination
            h = self._get_handler(uid, pid)
            
            # Write to the file
            msg = self.format(record)
            h.stream.write(msg + '\n')
            h.flush()
        except Exception:
            self.handleError(record)
            
    def close(self):
        for h in self._handlers.values():
            h.close()
        super().close()

def setup_logger():
    """
    Hooks our custom dynamic logger into the very root of Python.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove all default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Set up our dynamic router
    dynamic_handler = DynamicRoutingHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] [User: %(user_id)s] [Proj: %(project_id)s] - %(message)s"
    )
    dynamic_handler.setFormatter(formatter)
    
    # Keep printing to Docker console so you can still read it live!
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    root_logger.addHandler(dynamic_handler)
    root_logger.addHandler(stream_handler)
    
    # Force FastAPI/Uvicorn to use our router too
    logging.getLogger("uvicorn.access").handlers = [dynamic_handler, stream_handler]
    logging.getLogger("uvicorn.error").handlers = [dynamic_handler, stream_handler]
