import asyncio
import logging

from qyunslation.server.core import QueueAndHistoryHandler, TranslationService


def test_log_handler_assigns_monotonic_sequence_and_keeps_history():
    queue = asyncio.Queue()
    history = []
    handler = QueueAndHistoryHandler(queue, history, 10, task_id="task-1")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test-log-handler")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("first")
    logger.info("second")

    assert history == [
        {"seq": 1, "message": "first"},
        {"seq": 2, "message": "second"},
    ]
    assert queue.qsize() == 0


def test_history_logs_can_be_read_without_consuming_queue():
    service = TranslationService()
    service.tasks_log_histories["task-1"] = [
        {"seq": 1, "message": "first"},
        {"seq": 2, "message": "second"},
    ]

    assert service.get_task_logs_since("task-1", 0) == service.tasks_log_histories["task-1"]
    assert service.get_task_logs_since("task-1", 1) == [
        {"seq": 2, "message": "second"}
    ]
