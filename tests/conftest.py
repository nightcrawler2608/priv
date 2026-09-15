"""
loguru doesn't go through Python's stdlib `logging` module by default, so
pytest's `caplog` fixture (which hooks stdlib logging) can't see loguru
messages on its own. This bridges the two for the whole test suite.
"""
import logging

import pytest
from loguru import logger


class _PropagateToStdlib(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


@pytest.fixture(autouse=True)
def _loguru_caplog_bridge():
    handler_id = logger.add(_PropagateToStdlib(), format="{message}")
    yield
    logger.remove(handler_id)
