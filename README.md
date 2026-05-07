# SlothusSeeker Discord Bot

A Discord bot that automatically scrapes internship listings from [SimplifyJobs/Summer2026-Internships](https://github.com/SimplifyJobs/Summer2026-Internships) and posts them to configured Discord channels.

## Features

- 🔄 **Automatic Scraping**: Periodically fetches new internship listings (configurable interval)
- 🎯 **Smart Filtering**: Separates Summer vs Off-Season (Fall/Winter/Spring) internships
- 🔔 **Multi-Server Support**: Works across multiple Discord servers with independent configurations
- 🚫 **Deduplication**: Tracks posted internships to avoid spam
- ⚡ **Slash Commands**: Modern Discord slash commands for easy configuration
- 📊 **Rich Embeds**: Beautiful formatted internship posts with all details
- ⚡ **Reliable Parsing**: Processes unsorted source data and sorts results newest-first before posting

## Prerequisites

- Python 3.11 or higher
- UV package manager
- Discord Bot Token
- GitHub Token (optional, for higher rate limits)

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd SlothusSeeker
```

### 2. Install UV (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Install Dependencies

```bash
uv sync
```

### 4. Configure Environment Variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` and add:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
GITHUB_TOKEN=your_github_token_here  # Optional
SCRAPE_INTERVAL_HOURS=1
TEST_GUILD_ID=your_test_server_id  # Optional, syncs slash commands instantly for development
```

### 5. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Copy the bot token and add it to your `.env` file
5. Go to "OAuth2" > "URL Generator"
6. Select scopes: `bot` and `applications.commands`
7. Select bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
8. Copy the generated URL and use it to invite the bot to your server

## Running the Bot

### Development

```bash
uv run python main.py
```

### Production

For production, consider using a process manager like systemd or Docker.

## Bot Commands

All commands are slash commands (`/command`):

### Configuration Commands (Admin Only)

- `/set_summer_channel <channel>` - Set channel for Summer 2026 internships
- `/set_offseason_channel <channel>` - Set channel for Fall/Winter/Spring internships
- `/set_scrape_interval <hours>` - Set how often to scrape for new internships (0.5-168 hours, default: 6 hours)
- `/set_start_date <days_back>` - Set how far back to scrape internships (1-365 days)
- `/view_config` - View current channel configuration, interval, and start date
- `/scrape_now` - Manually trigger an internship scrape with detailed statistics
- `/test_scrape` - Test the scraper by fetching 5 recent internships (Admin only)

## Usage Example

1. Invite the bot to your Discord server
2. Run `/set_summer_channel #summer-internships`
3. Run `/set_offseason_channel #offseason-jobs`
   - **Note**: Once both channels are configured, the bot triggers an immediate scrape
   - All matching internships from the last 3 days will be posted
4. (Optional) Run `/set_start_date 30` to customize how far back to scrape
   - **Default**: Bot scrapes internships from the last **3 days**
   - Adjust based on your needs (e.g., 7, 14, 30, 60 days)
   - Prevents flooding with old/expired internships
5. (Optional) Run `/set_scrape_interval 3` to scrape every 3 hours instead of default 6 hours
6. Wait for the bot to scrape (or run `/scrape_now`)
7. New internships will be posted automatically!

**Scheduler Behavior:**
- The bot checks for new internships every 6 hours by default (configurable)
- If no channels are configured, the scheduler skips execution to prevent wasting resources
- When both posting channels are set up, an immediate scrape is triggered
- Subsequent scrapes only post NEW internships (deduplication prevents spam)

## Project Structure

```
SlothusSeeker/
├── src/
│   ├── bot/              # Discord bot implementation
│   │   ├── bot.py        # Main bot class
│   │   ├── embeds.py     # Discord embed formatting
│   │   └── commands/     # Slash commands
│   │       └── config.py
│   ├── scraper/          # GitHub scraping logic
│   │   ├── github_client.py
│   │   └── data_models.py
│   ├── scheduler/        # Background tasks
│   │   └── tasks.py
│   └── config/           # Configuration management
│       ├── settings.py
│       └── config_manager.py
├── main.py              # Entry point
├── pyproject.toml       # UV dependencies
└── .env                 # Environment variables (not committed)
```

## Data Files

The bot creates two JSON files automatically:

- `config.json` - Stores channel configurations per server
- `last_scrape.json` - Tracks posted internships to prevent duplicates

Both files persist across restarts and are gitignored.

## Filtering Logic

**Date Filtering:**
- **Default**: Bot only scrapes internships from the last **3 days**
- Use `/set_start_date <days_back>` to customize the time window (1-365 days)
- Prevents flooding channels with old/expired internships
- Recommended values: 3-7 days for fresh postings, 30-60 days for broader coverage

**Summer Channel:**
- Receives internships with "Summer" in the term field
- Examples: Summer 2026, Summer 2027

**Off-Season Channel:**
- Receives internships with "Fall", "Winter", or "Spring" in the term field
- Examples: Fall 2025, Winter 2026, Spring 2027

**Both Channels:**
- Only active internships (`active: true`)
- Only visible internships (`is_visible: true`)
- Only internships posted after the start date (if configured)

## Troubleshooting

### Bot doesn't respond to commands

- Ensure the bot has proper permissions in your server
- Check that slash commands are synced (restart the bot)
- Verify the bot is online in your server

### No internships being posted

- Check that channels are configured with `/view_config`
- Verify your GitHub token is valid (if using one)
- Check console logs for errors
- Try running `/scrape_now` manually

### Rate limiting issues

- Add a GitHub token to your `.env` file for higher rate limits
- Increase `SCRAPE_INTERVAL_HOURS` to scrape less frequently

## Contributing

Pull requests are welcome! Please ensure your code follows the existing style.

## License

MIT License

## Acknowledgments

- Internship data from [SimplifyJobs/Summer2026-Internships](https://github.com/SimplifyJobs/Summer2026-Internships)
- Built with [discord.py](https://github.com/Rapptz/discord.py)
