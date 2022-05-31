import argparse
from pathlib import Path
from cyborg.config import Config

from cyborg.utils.logging import set_up_logging
from cyborg.main import run

from ruamel.yaml import YAML


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="The path to the config file.", default=None
    )
    return parser.parse_args()


def main():
    args = get_args()

    set_up_logging()

    if args.config:
        config_path = Path(args.config).expanduser()

        with config_path.open("r") as config_file:
            config_dict = YAML(typ="safe").load(config_file)

        config = Config(**config_dict)
    else:
        config = Config()

    run(config)


if __name__ == "__main__":
    main()
