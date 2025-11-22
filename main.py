"""Entry point for the SlothusSeeker Discord bot."""

from src.bot.bot import run_bot
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Start the Discord bot."""
    logger.info("Starting SlothusSeeker Discord Bot...")
    run_bot()


if __name__ == "__main__":
    main()
