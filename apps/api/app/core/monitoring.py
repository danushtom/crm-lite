"""Error monitoring (Sentry). A no-op unless SENTRY_DSN is set.

Privacy: ``send_default_pii`` stays off, so Sentry's own scrubbing drops the Authorization
header, cookies and client IPs, and request bodies (CRM content: leads, notes, transcripts) are
never attached. What reaches Sentry is the stack trace, the route, and our request id -- enough
to find the matching log line, which carries the rest.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
_initialised = False


def init_monitoring() -> None:
    global _initialised
    if _initialised or not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release or None,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    _initialised = True
    logger.info("monitoring enabled environment=%s", settings.environment)
