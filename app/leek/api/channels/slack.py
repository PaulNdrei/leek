import logging
from typing import Union

import requests

from leek.api.db.store import Task, Worker, STATES_SUCCESS, STATES_EXCEPTION, STATES_UNREADY
from leek.api.conf import settings

logger = logging.getLogger(__name__)


def get_color(state):
    if state in STATES_EXCEPTION:
        return "danger"
    elif state in STATES_SUCCESS:
        return "good"
    elif state in STATES_UNREADY:
        return "#36C5F0"
    else:
        return "yellow"


def send_slack(app_name: str, event: Union[Task, Worker], wh_url: str, extra: dict):
    fields = [
        {
            "title": "Application",
            "value": app_name,
            "short": True,
        },
        {
            "title": "Environment",
            "value": event.app_env,
            "short": True,
        },
        {
            "title": "Task worker",
            "value": event.worker,
            "short": True,
        },
        {
            "title": "Task state",
            "value": event.state,
            "short": True,
        },
        {
            "title": "Task uuid",
            "value": event.uuid,
            "short": False,
        }
    ]
    
    # Add exception message for failed tasks
    if event.exception:
        fields.append(
            {
                "title": "Exception",
                "value": event.exception,
                "short": False,
            }
        )
    
    # Add runtime for completed tasks
    if event.runtime:
        fields.append(
            {
                "title": "Runtime",
                "value": f"{event.runtime:.2f} seconds",
                "short": True,
            }
        )
    
    # Add queue information
    if event.queue:
        fields.append(
            {
                "title": "Queue",
                "value": event.queue,
                "short": True,
            }
        )
    
    # Add retry count if available
    if event.retries is not None:
        fields.append(
            {
                "title": "Retries",
                "value": str(event.retries),
                "short": True,
            }
        )
    
    # Add task arguments (only if not empty)
    if event.args:
        args_text = str(event.args).strip()
        # Check if args has actual content (not just "()" or "[]" or "{}")
        if args_text and args_text not in ("()", "[]", "{}", "None", "null"):
            if len(args_text) > 500:
                args_text = args_text[:500] + "... (truncated)"
            fields.append(
                {
                    "title": "Arguments",
                    "value": f"```\n{args_text}\n```",
                    "short": False,
                }
            )
    
    # Add task keyword arguments (only if not empty)
    if event.kwargs:
        kwargs_text = str(event.kwargs).strip()
        # Check if kwargs has actual content (not just "()" or "[]" or "{}")
        if kwargs_text and kwargs_text not in ("()", "[]", "{}", "None", "null"):
            if len(kwargs_text) > 500:
                kwargs_text = kwargs_text[:500] + "... (truncated)"
            fields.append(
                {
                    "title": "Keyword Arguments",
                    "value": f"```\n{kwargs_text}\n```",
                    "short": False,
                }
            )
    
    if extra.get("note"):
        fields.append(
            {
                "title": "Note",
                "value": extra.get("note"),
                "short": False,
            }
        )
    
    # Prepare main attachment with fields
    attachments = [
        {
            "color": get_color(event.state),
            "title": f"Task: {event.name}",
            "title_link": f"{settings.LEEK_WEB_URL}/task?app={app_name}&uuid={event.uuid}",
            "fields": fields,
        }
    ]
    
    # Add traceback as a separate attachment at the end
    if event.traceback:
        # Restructure: Show ERROR FIRST (in preview), then full stack trace (in "Show more")
        # Slack shows first ~440 chars before "Show more" button
        lines = event.traceback.strip().split('\n')
        
        # Find the actual error (usually the last 1-3 lines)
        error_lines = []
        for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1):
            line = lines[i].strip()
            if line:  # Skip empty lines
                error_lines.insert(0, lines[i])
                # Stop after we have the error line and maybe one context line
                if len(error_lines) >= 3:
                    break
        
        # Build the traceback with error first, then full trace
        if len(lines) > 10:
            # Show error first, then separator, then full traceback
            error_preview = '\n'.join(error_lines)
            full_trace = '\n'.join(lines)
            traceback_text = f"{error_preview}\n\n{'─' * 40}\n\nFull traceback:\n{full_trace}"
        else:
            # Short traceback, show as is
            traceback_text = event.traceback
        
        # Add as separate attachment at the end
        attachments.append(
            {
                "color": get_color(event.state),
                "title": "Traceback",
                "text": f"```\n{traceback_text}\n```",
            }
        )
    
    body = {
        "attachments": attachments,
    }
    try:
        requests.post(
            wh_url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=body
        ).raise_for_status()
    except Exception as e:
        logger.error(f"Request to slack returned an error: {e}")
