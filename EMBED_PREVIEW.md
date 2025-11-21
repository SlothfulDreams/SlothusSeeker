# Discord Embed Preview

## 1. Internship Listing Embed (Summer)

```
┌─────────────────────────────────────────────────────────────┐
│ 🔗 Google - Software Engineering Intern                      │
│ https://example.com/apply                                    │
├─────────────────────────────────────────────────────────────┤
│ ☀️ Summer 2026                                               │
│                                                               │
│ 📍 Location              │ 📅 Posted                         │
│ Mountain View, CA,       │ November 14, 2023                 │
│ New York, NY             │                                   │
│                                                               │
│ 🛂 Sponsorship                                               │
│ Offers Sponsorship                                           │
│                                                               │
│ ID: test-uuid-123                                            │
└─────────────────────────────────────────────────────────────┘
Color: Gold/Yellow (#F1C40F)
```

## 2. Internship Listing Embed (Off-Season)

```
┌─────────────────────────────────────────────────────────────┐
│ 🔗 Meta - Product Manager Intern                             │
│ https://example.com/apply2                                   │
├─────────────────────────────────────────────────────────────┤
│ ❄️ Fall 2025                                                 │
│                                                               │
│ 📍 Location              │ 📅 Posted                         │
│ Menlo Park, CA           │ November 3, 2023                  │
│                                                               │
│ 🛂 Sponsorship                                               │
│ Does not offer sponsorship                                   │
│                                                               │
│ ID: test-uuid-456                                            │
└─────────────────────────────────────────────────────────────┘
Color: Blue (#3498DB)
```

## 3. Stats Embed (Posted after scraping)

```
┌─────────────────────────────────────────────────────────────┐
│ 📊 New Internships Found                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ ☀️ Summer               │ ❄️ Off-Season                      │
│ 5 new                   │ 2 new                              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
Color: Green (#2ECC71)
```

## 4. Configuration Embed (from /view_config)

```
┌─────────────────────────────────────────────────────────────┐
│ ⚙️ Configuration for My Discord Server                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ ☀️ Summer Channel                                            │
│ #summer-internships                                          │
│                                                               │
│ ❄️ Off-Season Channel                                        │
│ #offseason-internships                                       │
│                                                               │
│ ⏰ Scrape Interval                                           │
│ 6 hours                                                      │
│                                                               │
│ 📅 Scraping From                                             │
│ Internships posted after November 18, 2025                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
Color: Blurple (#5865F2)
```

## Features:

### Internship Embeds:
- ✅ Clickable title linking directly to application
- ✅ Color-coded: Gold for Summer, Blue for Off-Season
- ✅ Season emoji indicator (☀️ or ❄️)
- ✅ Location and posting date side-by-side
- ✅ Sponsorship status (only shown if available)
- ✅ Unique ID in footer for tracking

### Stats Embed:
- ✅ Quick summary of new postings
- ✅ Separate counts for Summer and Off-Season
- ✅ Green color for positive/success indication

### Config Embed:
- ✅ Shows all current settings
- ✅ Channel mentions are clickable
- ✅ Human-readable interval (converts to minutes/hours)
- ✅ Formatted date display
- ✅ Helpful description if no channels configured

## Examples in Action:

When a user runs `/view_config`, they'll see the configuration embed.

When the scraper finds new internships:
1. Stats embed is posted first (summary)
2. Then individual internship embeds for each new listing
3. Summer internships go to the summer channel
4. Off-Season internships go to the off-season channel
