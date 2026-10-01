"""Whac-A-Mole package entrypoint."""

import sys
from whacamole.cli import main

if __name__ == "__main__":
    main(sys.argv[1:])
