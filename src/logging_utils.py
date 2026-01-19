"""
Shared logging configuration for StudioZero.

Provides a unified logging setup used across CLI and batch processing.
"""

import logging
import sys
from typing import Optional

# Module loggers to configure for detailed output
MODULE_LOGGERS = [
    'src.pipeline',
    'src.narrative',
    'src.moviedbapi',
    'src.gemini_tts',
    'src.stock_media',
    'src.renderer',
    'src.config',
    'src.batch_runner',
    'src.cloud_services',
    'src.marketing',
]


def setup_logging(
    verbose: bool = False,
    logger_name: Optional[str] = None,
) -> logging.Logger:
    """
    Configure logging with consistent formatting across the application.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
        logger_name: Optional name for the returned logger.
                    If None, returns the root logger.

    Returns:
        Configured logger instance.
    """
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter with detailed output
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []
    root_logger.addHandler(console_handler)

    # Configure specific module loggers for detailed output
    for module in MODULE_LOGGERS:
        module_logger = logging.getLogger(module)
        module_logger.setLevel(log_level)

    if logger_name:
        return logging.getLogger(logger_name)
    return root_logger
