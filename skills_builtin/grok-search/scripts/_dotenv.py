"""Environment policy for Grok Search scripts."""


def load_dotenv() -> bool:
    """Keep compatibility with older callers while enforcing env-only secrets."""
    return False
