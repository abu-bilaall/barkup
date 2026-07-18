import sys

from pydantic import ValidationError

from barkup import run_barkup
from cli import cli


def main() -> None:
    try:
        run_barkup()
    except ValidationError as e:
        print("Configuration error:\n")

        for err in e.errors():
            field = ".".join(str(x) for x in err["loc"])
            message = err["msg"]
            print(f"  • {field}: {message}")

        sys.exit(1)

    # except Exception as e:
    #     print(f"Unexpected error: {e}")
    #     sys.exit(1)


if __name__ == "__main__":
    cli()
