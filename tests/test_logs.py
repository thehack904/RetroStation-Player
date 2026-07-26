import logging

from retrostation_player.logs import RuntimeLogBuffer, normalize_line_count


def test_normalize_line_count_is_bounded():
    assert normalize_line_count("0") == 1
    assert normalize_line_count("200") == 200
    assert normalize_line_count("5000") == 1000
    assert normalize_line_count("invalid") == 200


def test_runtime_log_buffer_filters_entries():
    handler = RuntimeLogBuffer(capacity=10)
    logger = logging.getLogger("test.runtime.logs")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info("Playback started")
        logger.error("Stream failed")
        errors = handler.read(lines=10, level="error")
        matches = handler.read(lines=10, search="playback")
    finally:
        logger.removeHandler(handler)
        logger.propagate = True

    assert len(errors) == 1
    assert errors[0]["message"] == "Stream failed"
    assert len(matches) == 1
    assert matches[0]["message"] == "Playback started"
