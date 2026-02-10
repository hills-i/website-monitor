# Web-Monitor

A Python-based website monitoring tool that automatically detects changes on websites and generates intelligent summaries using AI.

> ⚠️ **Security Notice**: This tool requires an OpenAI API key. Never commit `config.json` to version control - it's protected by `.gitignore` but always verify before pushing to public repositories.

## Features

- **Automated Website Crawling**: Monitors multiple websites from a configurable list
- **Change Detection**: Compares current crawls with previous ones to identify modifications
- **HTML Normalization**: Converts HTML to Markdown content-focused diffs
- **AI-Powered Summaries**: Uses OpenAI API to generate summaries of detected changes
- **Visual Reports**: Creates HTML reports with colored diff visualization
- **Cross-Platform**: Works on Windows, Linux, and macOS

## Quick Start

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure**
   ```bash
   cp config.example.json config.json
   # Edit config.json and add your OpenAI API key
   ```

3. **Add Websites to Monitor**
   ```bash
   # Edit website.txt and add URLs (one per line)
   nano website.txt  # or your preferred editor
   ```

4. **Run the Monitor**
   ```bash
   # Linux/macOS
   python3 website_monitor.py

   # Windows
   python website_monitor.py
   ```

## How It Works

1. **Crawling**: Downloads HTML content from each URL in `website.txt`
2. **Storage**: Saves content to `output/YYYY-MM-DD/hostname.html`
3. **Normalization**: Converts HTML to Markdown (for cleaner diffs)
4. **Storage**: Saves Markdown to `output/YYYY-MM-DD/hostname.md`
5. **Comparison**: Compares Markdown files with previous crawl to detect content changes
6. **AI Analysis**: Sends diffs to OpenAI for intelligent summarization
7. **Reporting**: Generates `reports/report-YYYY-MM-DD.html` with summaries and visual diffs

**Why Markdown normalization?** HTML diffs can be noisy due to whitespace, attribute order, and tag formatting changes. Converting to Markdown allows the tool to focus on actual content changes (headings, links, text) rather than HTML structural noise.

## Output Structure

```
website-monitor/
├── website_monitor.py           # Main Python script
├── requirements.txt         # Python dependencies
├── website.txt              # URLs to monitor
├── config.json              # API configuration (gitignored)
├── prompt.txt               # AI summarization prompt template
├── output/
│   └── YYYY-MM-DD/          # Daily crawl results
│       ├── example.com.html         # Original HTML
│       ├── example.com.md           # Converted Markdown
│       ├── another-site.html
│       └── another-site.md          # Converted Markdown
└── reports/                 # Generated reports
    └── report-YYYY-MM-DD.html
```

## Configuration

The `config.json` file must contain:
- `OpenAI_API_Key`: Your OpenAI API key for generating summaries

### Customizing AI Summaries

Edit `prompt.txt` to customize how changes are summarized. The `{formatted_diff}` placeholder must remain in the file.

## Requirements

- Python 3.8 or higher
- Python packages: `requests`, `openai`, `markdownify` (see `requirements.txt`)
- Internet connection for crawling websites
- OpenAI API key for change summarization

## Error Handling

The script includes robust error handling for:
- Network failures during website crawling
- OpenAI API errors and rate limits
- File system operations
- Missing configuration files

Failed operations are logged with warnings, and the script continues processing remaining sites.

## Politeness Features

- 3-second delay between website requests to avoid overwhelming servers
- Error handling for unavailable sites
- UTF-8 encoding support for international content

# License
MIT