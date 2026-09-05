# SlothusSeeker Discord Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Supabase](https://img.shields.io/badge/supabase-backed-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
[![UV](https://img.shields.io/badge/managed%20with-uv-DE5FE9?style=for-the-badge)](https://docs.astral.sh/uv/)
[![GitHub Repo](https://img.shields.io/badge/github-SlothfulDreams%2FSlothusSeeker-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/SlothfulDreams/SlothusSeeker)

A Discord bot that automatically scrapes internship listings from [Jobright's 2026 Software Engineer Internship repository](https://github.com/jobright-ai/2026-Software-Engineer-Internship) and posts allow-listed company matches to configured Discord channels.

## Features

- 🔄 **Automatic Scraping**: Periodically fetches new internship listings (configurable interval)
- 🎯 **Smart Filtering**: Separates Spring/Winter, Summer, and Fall internships by season text in the job title
- 🔔 **Multi-Server Support**: Works across multiple Discord servers with independent configurations
- 🗄️ **Supabase Config**: Stores Discord server/channel mappings and company allow-lists in Supabase
- 🚫 **Deduplication**: Tracks posted internships to avoid spam
- ⚡ **Slash Commands**: Modern Discord slash commands for easy configuration
- 📊 **Rich Embeds**: Beautiful formatted internship posts with all details
- ⚡ **Reliable Parsing**: Processes unsorted source data and sorts results newest-first before posting

## Prerequisites

- Python 3.11 or higher
- UV package manager
- Discord Bot Token
- GitHub Token (optional, for higher rate limits)
- Supabase project URL and service role key

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
SCRAPE_INTERVAL_MINUTES=15
DEFAULT_SCRAPE_DAYS_BACK=3
POST_THROTTLE_SECONDS=1.0
COMPANIES_PER_PAGE=10
SYNC_COMMANDS_ON_START=false  # Set true only when you intentionally want global command sync on startup
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

Run `supabase/schema.sql` in your Supabase SQL editor before starting the bot.
Use the service role key because this is a private backend bot and the schema keeps
row-level security enabled.
The older publishable/anon Supabase key is not enough for server-side writes.

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
   - Mention Everyone
8. Copy the generated URL and use it to invite the bot to your server

## Running the Bot

### Development

```bash
uv run python main.py
```

Global command sync is skipped by default to avoid Discord registration rate limits; set
`SYNC_COMMANDS_ON_START=true` only when you intentionally want startup to sync global commands.

### Production

For Heroku, this repo runs as a worker dyno:

```bash
heroku ps:scale worker=1
```

The Heroku app URL may show `No web processes running`; that is expected because
this bot does not serve a website. Heroku runs the worker with `python main.py`.
For other hosts, use an always-on worker process with `uv run python main.py`.

## Bot Commands

All commands are slash commands (`/command`):

### Configuration Commands (Admin Only)

- `/config set-season-channel <season> <channel>` - Set a Spring/Winter, Summer, or Fall posting channel
- `/config set-sudo-channel <channel>` - Set the sudo channel ID for this server
- `/config set-scrape-interval <minutes>` - Set how often to scrape for new internships (10-10080 minutes, default: 15 minutes)
- `/config set-start-date <days_back>` - Set how far back to scrape internships (1-365 days)
- `/config view` - View current channel configuration, interval, and start date
- `/config scrape-now` - Manually trigger an internship scrape with detailed statistics
- `/companies add <company_name>` - Add a lowercase company allow-list entry
- `/companies list` - View a paginated embed of allow-listed companies and IDs
- `/companies delete <company_id>` - Delete a company by ID

## Usage Example

1. Invite the bot to your Discord server
2. Run `/config set-season-channel Summer #summer-internships`
3. Run `/config set-season-channel Fall #fall-internships`
4. Run `/companies add tesla`
5. (Optional) Run `/config set-start-date 30` to customize how far back to scrape
   - **Default**: Bot scrapes internships from the last **3 days**
   - Adjust based on your needs (e.g., 7, 14, 30, 60 days)
   - Prevents flooding with old/expired internships
6. (Optional) Run `/config set-scrape-interval 180` to scrape every 3 hours instead of default 15 minutes
7. Wait for the bot to scrape (or run `/config scrape-now`)
8. New allow-listed internships will be posted automatically!

**Scheduler Behavior:**
- The bot checks for new internships every 15 minutes by default (configurable)
- If no channels are configured, the scheduler skips execution to prevent wasting resources
- If no companies are configured, the scheduler skips execution
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

## Data Storage

Supabase stores persistent server, company, and posting data:

- `discord_servers` - Discord `guild_id`, server name, season channel IDs, and `sudo_id`
- `companies` - Lowercase unique company names with numeric IDs
- `posted_jobs` - Per-guild, per-season posted job IDs for duplicate prevention

The bot also creates a local JSON file automatically:

- `config.json` - Stores global runtime settings such as scrape interval/start date

This file persists across restarts and is gitignored.

## Duplicate Prevention

Posting history and company lists are read in complete, ID-ordered database pages.
Equivalent US city/state formats now share a job ID across Jobright and Simplify.
Existing records are retained: matching checks canonical IDs, legacy ID aliases,
and exact saved source URLs with matching company, normalized title, and job year.
Aliases from merged feed entries are kept for matching, even when only one embed is posted.

Each successful Discord delivery is recorded before the next message or throttle
delay. If recording fails after a send, the batch stops with an error. A process
crash between Discord accepting the message and its database checkpoint can still
cause that message to be reposted; this is not an exactly-once delivery guarantee.

Older records do not contain locations, so a complete historical ID migration is
not possible. Compatibility matching is conservative; unrelated jobs are not
merged merely because their company and title match. No history reset is needed.

## Filtering Logic

**US-Only Locations (all feeds):**
- Jobright, Simplify Summer, and Simplify Off-Season use the same location check
- Only listings whose locations are all identifiable as US-based are eligible
- US-qualified remote roles (e.g. `Remote in USA`) are included
- Foreign, mixed-country, missing, and ambiguous locations (including bare `Remote`) are excluded
- US country labels, city/state pairs, state names, and common feed shorthand (`NYC`, `SF`, `LA`, `South SF`) are recognized; unknown city-only labels are excluded rather than guessed

**Date Filtering:**
- **Default**: Bot only scrapes internships from the last **3 days**
- Configure the default with `DEFAULT_SCRAPE_DAYS_BACK`
- Use `/config set-start-date <days_back>` to customize the time window (1-365 days)
- Jobright month/day labels use their most recent valid occurrence, including the previous year around New Year; all feeds share one UTC reference time per fetch
- Posting dates are independent of the internship year in the title
- Prevents flooding channels with old/expired internships
- Recommended values: 3-7 days for fresh postings, 30-60 days for broader coverage

**Season Channels:**
- Summer and Fall channels receive jobs whose title contains that season name
- Spring/Winter receives jobs whose title contains either `spring` or `winter`
- Matching is case-insensitive and requires the season word to appear in the title
- If a season channel is not configured, matching jobs for that season are skipped
- Duplicate prevention is tracked in Supabase per guild and season

**Company Allow-List:**
- Only companies stored in `companies` are posted
- Company matching lowercases and normalizes whitespace on both stored names and parsed Jobright names
- Use `/companies list` to find IDs for deletion

## Troubleshooting

### Bot doesn't respond to commands

- Ensure the bot has proper permissions in your server
- Check that slash commands are synced (restart the bot)
- Verify the bot is online in your server

### No internships being posted

- Check that channels are configured with `/config view`
- Check that companies are configured with `/companies list`
- Verify your GitHub token is valid (if using one)
- Check console logs for errors
- Try running `/config scrape-now` manually

### Rate limiting issues

- Add a GitHub token to your `.env` file for higher rate limits
- Increase `SCRAPE_INTERVAL_MINUTES` to scrape less frequently

## Contributing

Pull requests are welcome! Please ensure your code follows the existing style.

## License

MIT License

## Acknowledgments

- Internship data from [jobright-ai/2026-Software-Engineer-Internship](https://github.com/jobright-ai/2026-Software-Engineer-Internship)
- Built with [discord.py](https://github.com/Rapptz/discord.py)
