"""
Parse ticker lists from input.txt or CLI arguments.
"""

import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INPUT_FILE = os.path.join(BASE_DIR, "input.txt")


def parse_input_file(path: str = DEFAULT_INPUT_FILE) -> list[str]:
    """
    Read tickers from a text file (one per line, # for comments, blank lines ignored).
    Returns list of uppercase ticker strings.
    """
    tickers = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Take first token (in case of inline comments)
            ticker = line.split("#")[0].strip().upper()
            if ticker:
                tickers.append(ticker)
    return tickers
