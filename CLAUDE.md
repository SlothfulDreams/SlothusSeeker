# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SlothusSeeker is a Discord bot that automatically scrapes internship listings from the SimplifyJobs/Summer2026-Internships GitHub repository and posts new listings to configured Discord channels. It intelligently separates listings by season (Summer vs Off-Season: Fall/Winter/Spring) and prevents duplicate posting through deduplication tracking.

## Development Commands

**Run the bot:**
```bash
uv run python main.py
```

**Run tests:**
```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_github_client.py

# Specific test
uv run pytest tests/test_github_client.py::test_fetch_listings_basic

# With coverage
uv run pytest --cov=src --cov-report=term-missing
```

**Install dependencies:**
```bash
uv sync
```

**Activate virtual environment (if needed):**
```bash
source .venv/bin/activate
```

## Architecture Overview

### Cog Pattern (discord.py)

The bot uses discord.py's **Cog pattern** to organize functionality into modular components:

- **ConfigCommands** (`src/bot/commands/config.py`): Handles all slash commands for configuration
- **ScraperTasks** (`src/scheduler/tasks.py`): Manages background scraping tasks

**Key Pattern**: Cogs are loaded in `bot.setup_hook()` and receive the `ConfigManager` instance via dependency injection. This ensures a single source of truth for configuration across all components.

### Setup Hook Pattern

The bot initialization follows a specific lifecycle:

1. `main.py` → `run_bot()` → `create_bot()`
2. `create_bot()` creates `ConfigManager` and `InternshipBot`
3. `bot.run(token)` triggers `setup_hook()` (async)
4. `setup_hook()` loads cogs and calls `bot.tree.sync()` to register slash commands
5. Only after sync completes does `on_ready()` fire

**Critical**: Slash commands MUST be loaded and synced in `setup_hook()`, not `on_ready()`. Commands loaded after `on_ready()` won't be registered with Discord.

### Configuration System

Two-layer configuration architecture:

**Layer 1: Global Settings** (`config.json` → `"global"` key)
- `scrape_interval_hours`: How often to scrape (default: 6)
- `scrape_start_timestamp`: Unix timestamp for date filtering (default: 3 days ago)

**Layer 2: Per-Guild Settings** (`config.json` → guild ID keys)
- `summer_channel`: Channel ID for Summer internships
- `offseason_channel`: Channel ID for Fall/Winter/Spring internships

**Deduplication Tracking** (`last_scrape.json`)
- Stores two arrays: `summer` and `offseason`
- Each contains UUIDs of already-posted internships
- Updated after each scrape to prevent re-posting

**ConfigManager Methods**:
- `get_guild_config(guild_id)`: Retrieve per-guild config
- `get_all_channels(channel_type)`: Get all configured channels across all guilds (used for posting)
- `update_last_scrape(category, ids)`: Persist posted internship IDs

### Scraping Flow

**Complete flow from trigger to post:**

1. **Trigger**: Either periodic (`@tasks.loop`) or manual (`/scrape_now`)
2. **Fetch**: `GitHubClient.get_new_listings(last_scrape, start_timestamp)`
   - Makes HTTP GET to GitHub listings.json
   - Parses JSON into `Internship` Pydantic models
   - **Optimization**: Stops parsing when hitting old entries (assumes newest-first)
   - Filters by `active=true`, `is_visible=true`, and date > start_timestamp
   - Categorizes into summer vs offseason based on `terms` field
3. **Deduplicate**: Filters out internships with IDs in `last_scrape`
4. **Post**: For each configured channel and new internship:
   - Create Discord embed with `create_internship_embed()`
   - Post to channel with 1-second delay (rate limiting)
   - Catch and log errors without crashing
5. **Update**: `config_manager.update_last_scrape()` persists all internship IDs

**Returns**: Tuple of `(new_listings, all_listings)` where:
- `new_listings`: Only internships not in last_scrape (to be posted)
- `all_listings`: All fetched internships (for updating deduplication tracking)

### Season Categorization Logic

**Summer Internships** (`Internship.is_summer`):
- Any `terms` array element containing "Summer"
- Examples: "Summer 2026", "Summer 2027"

**Off-Season Internships** (`Internship.is_offseason`):
- Any `terms` array element containing "Fall", "Winter", or "Spring"
- Examples: "Fall 2025", "Winter 2026", "Spring 2027"

**Implementation**: See `data_models.py` properties `is_summer` and `is_offseason`

### Dynamic Scheduler Reconfiguration

The scheduler can restart with a new interval **without restarting the bot**:

1. User runs `/set_scrape_interval 3`
2. `ConfigCommands` updates `ConfigManager.set_scrape_interval(3)`
3. Calls `ScraperTasks.restart_scraper(3)`
4. `restart_scraper()` cancels existing `@tasks.loop` task
5. Creates and starts new task with updated interval

**Key Pattern**: Store the task reference as `self.scraper_task` to enable cancellation and recreation.

### Date Filtering

**Default Behavior**: Only scrapes internships from last 3 days

**Configurable via**: `/set_start_date <days_back>`
- Converts days to Unix timestamp
- Stored in `config.json` → `"global"` → `"scrape_start_timestamp"`
- Applied in `GitHubClient.fetch_listings(start_timestamp)`

**Optimization**: Parser stops early when `date_posted < start_timestamp` (assumes newest-first sorting)

## Important Implementation Details

### Discord Privileged Intents

**Current Configuration**: Bot requests `message_content` privileged intent (line 12 in `src/bot/bot.py`)

**Required Action**: Must enable "Message Content Intent" in Discord Developer Portal:
1. Go to https://discord.com/developers/applications/
2. Select your bot
3. Go to "Bot" tab
4. Scroll to "Privileged Gateway Intents"
5. Enable "Message Content Intent"

**Note**: If bot only uses slash commands (current implementation), this intent can be removed.

### Async/Await Patterns

**All I/O is async**: Discord API calls, HTTP requests to GitHub, file operations

**Rate Limiting**: Use `asyncio.sleep(1)` between Discord posts to avoid rate limits

**Task Lifecycle**: Use `@tasks.loop` for periodic tasks, always check `bot.is_ready()` in `before_loop` hook

### Error Handling Philosophy

**Graceful Degradation**: Errors in posting to one channel should not prevent posting to others

**Implementation**: Each channel post is wrapped in try/except, errors are logged but not raised

**Example** (from `tasks.py`):
```python
for channel_id in summer_channels:
    try:
        # ... post internship ...
    except Exception as e:
        print(f"Error posting to channel {channel_id}: {e}")
        # Continue to next channel
```

### Testing Patterns

**Mocking HTTP Responses**: Use `unittest.mock.patch` with `aiohttp.ClientSession.get`

**Async Tests**: All test functions are `async def` with `@pytest.mark.asyncio` decorator

**Fixtures**: `conftest.py` provides reusable fixtures like `sample_internship_data`

**Key Test Files**:
- `test_github_client.py`: Tests fetching, parsing, deduplication
- `test_data_models.py`: Tests Pydantic models and categorization logic
- `test_config_manager.py`: Tests configuration persistence

## Common Gotchas

1. **Slash commands not appearing**: Ensure they're loaded in `setup_hook()` and `bot.tree.sync()` is called
2. **Commands work but scheduler doesn't**: Check `before_loop` hook waits for `bot.wait_until_ready()`
3. **Duplicate posts**: Verify `last_scrape.json` is being updated after each scrape
4. **Missing internships**: Check `scrape_start_timestamp` - might be filtering out recent posts
5. **Parser stopping early**: Assumes newest-first sorting from GitHub - verify this hasn't changed

## Extension Points

**Adding new slash commands**: Add method to `ConfigCommands` with `@app_commands.command()` decorator

**Adding new internship categories**: 
1. Add property to `Internship` model
2. Update `GitHubClient.fetch_listings()` categorization
3. Add channel config option

**Changing scrape source**: Replace `GitHubClient` with new implementation, maintain same interface (`get_new_listings()` method)
