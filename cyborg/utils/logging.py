import logging
import sys
from pathlib import Path
from typing import Union

LOG_FORMAT = "%(asctime)s %(levelname)s (%(name)s:%(funcName)s) - %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def set_up_logging(
    *, filename: Union[str, Path] = "./cyborg.log", log_level: int = logging.DEBUG
):
    root = logging.getLogger()
    root.setLevel(log_level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    file_handler = logging.FileHandler(filename)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)
