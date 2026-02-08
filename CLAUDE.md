# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Website Monitor is a Python-based website monitoring tool that automatically detects changes on websites and generates AI-powered summaries in Japanese. Designed for cross-platform use (Windows/Linux/macOS).

**Key Features:**
- HTML→Markdown normalization using markdownify for cleaner diffs
- AI-powered change summaries in Japanese
- Cross-platform compatibility
- Interactive HTML reports

## Running the Tool

```bash
# First-time setup
pip install -r requirements.txt
cp config.example.json config.json
# Then edit config.json to add OpenAI API key

# Main execution
python3 website_monitor.py  # Linux/macOS
python website_monitor.py   # Windows

# Run tests
python3 test_website_monitor.py
```

## Architecture

### Core Processing Flow

1. **Crawling** (`get_site_content`): Downloads HTML from URLs in `website.txt`
2. **Redaction**: Applies regex patterns to filter sensitive data (passwords, API keys)
3. **HTML Filtering** (`filter_html_content`): Extracts main content, removes navigation/headers/footers
4. **Storage**: Saves to `output/YYYY-MM-DD/hostname.html` with redaction and filtering applied
5. **Normalization** (`convert_to_markdown`): Converts HTML to Markdown using markdownify
6. **Markdown Cleanup** (`clean_markdown_for_diff`): Removes structural noise (CSS classes, empty tags, HTML attributes)
7. **Storage**: Saves cleaned Markdown to `output/YYYY-MM-DD/hostname.md`
8. **Comparison** (`compare_site_content`): Diffs cleaned Markdown against previous crawl
9. **AI Summarization** (`summarize_changes`): Sends diffs to OpenAI API for Japanese summaries
10. **Report Generation** (`generate_report`): Creates HTML report with visual diffs

**Key Features:**
- Uses HTML filtering (trafilatura) to extract main content and reduce noise by 40-70%
- Uses Markdown normalization to reduce diff noise from HTML formatting changes
- Uses Markdown cleanup to remove structural elements (`<div>`, etc.)
- Focuses on actual content changes (text, tables, code blocks)

### Configuration System

The script uses a **fallback pattern** for all settings:
- Reads from `config.json` first
- Falls back to hardcoded defaults if setting is missing
- This provides backward compatibility when new config options are added

All configuration variables are initialized in the "Configuration with Defaults" section after API key validation.

### Key Design Patterns

**Redaction System**
- `Redaction_Patterns` is an array of regex patterns from config.json
- Applied dynamically in `Get-SiteContent` before saving HTML
- Filters sensitive data (passwords, API keys, tokens) from saved content

**Diff Truncation**
- `Max_Diff_Lines` (default: 500) controls token usage
- When exceeded, shows first 250 + "... (中略 X 行) ..." + last 250 lines
- Prevents API token limit issues on large page changes

**API Retry Logic**
- `Request_MaxRetries` (default: 1) with exponential backoff
- `Request_TimeoutSeconds` (default: 30)
- `Request_RetryBackoffSeconds` (default: 1)
- Uses `Invoke-RestMethod` for modern HTTP handling

**Cross-Platform Compatibility**
- Uses `System.Net.WebUtility::HtmlEncode` (not `System.Web.HttpUtility`)
- UTF-8 encoding enforced throughout for Japanese text support
- No Windows-specific dependencies

### Function Responsibilities

**`convert_to_markdown(html_path: Path) -> Path`**
- Converts HTML file to Markdown using `markdownify` library
- Uses ATX-style headings for consistent output
- Graceful fallback: returns HTML path if conversion fails

**`filter_html_content(html_content: str, config: dict) -> str`**
- Extracts main content from HTML before Markdown conversion
- Uses 3-tier fallback: Trafilatura → BeautifulSoup → Original HTML
- **Trafilatura method** (primary): Purpose-built content extraction with 93.7% accuracy
- **BeautifulSoup method** (fallback): Removes nav/header/footer/aside/script/style elements
- Validates filtered content isn't too short (<100 chars or <5% of original)
- Reduces output size by 40-70% while preserving text/tables/code/lists
- Logs filtering results (character count reduction)
- Can be disabled via `HTML_Filtering_Enabled: false` in config

**`get_site_content(url, directory, redaction_patterns, config) -> dict`**
- Downloads webpage content using `requests` library
- Applies redaction patterns dynamically
- Calls `filter_html_content()` to extract main content (if enabled)
- Saves HTML file (redacted and filtered)
- Calls `convert_to_markdown()` to create Markdown version
- Calls `clean_markdown_for_diff()` to clean the Markdown
- Saves cleaned Markdown file (overwrites markdownify output)
- Returns dict: `{'success': bool, 'file_path': Path, 'md_path': Path, 'hostname': str, 'content': str}`

**`clean_markdown_for_diff(md_content: str, config: dict) -> str`**
- Removes structural noise from Markdown content
- Configurable via regex patterns in config
- Default patterns remove:
  - `^:::.*$` - Fenced divs (e.g., `::: {.container}`, `:::`)
  - `^{\..*}$` - CSS class attributes (e.g., `{.bg-white .dark:bg-slate-700}`)
  - `^</?div.*>$` - Div tags (with or without attributes)
  - `^</?span.*>$` - Span tags (with or without attributes)
  - `^</?figure.*>$` - Figure tags
  - `^\[\]$` - Empty Markdown links
- Also removes inline attributes: `{.class}`, `{#id}`
- Removes HTML attributes: `target="..."`, `rel="..."`, `class="..."`
- Removes empty links: `[]`, `[](url)`, `(url)`
- Reduces multiple consecutive blank lines to single blank line
- Can be disabled via `Markdown_Cleanup_Enabled: false` in config
- Reduces diff noise by focusing on actual content changes

**`compare_site_content(old_md_path, new_md_path, config) -> list`**
- Uses Python's `difflib.Differ()` for line-by-line diff
- Compares **cleaned Markdown files** (already cleaned when saved)
- Returns list of dicts with 'InputObject' and 'SideIndicator' keys
- Returns None if no previous file exists

**`summarize_changes(site_change, api_key, config) -> str`**
- Truncates diff if exceeds `max_diff_lines`
- Calls OpenAI API using official `openai` library
- Implements retry logic with exponential backoff
- Prompts for Japanese summaries of user-visible changes

**`generate_report(changed_sites, report_path) -> None`**
- Creates interactive HTML with collapsible diff sections
- Uses `html.escape()` for cross-platform safety
- Outputs UTF-8 encoded HTML

**`setup_directories(base_dir, output_dir_name) -> tuple`**
- Creates output and daily directories
- Finds previous crawl directory for comparison
- Returns `(today_dir, previous_dir or None)`

**`load_config(config_path) -> tuple`**
- Loads config.json with fallback defaults (same pattern as PowerShell)
- Validates API key
- Returns `(api_key, config_dict)`

## Important Implementation Notes

#### Library Choices
- **`requests`**: HTTP requests (replaces PowerShell's `Invoke-WebRequest`)
- **`openai`**: Official OpenAI client (cleaner than direct API calls)
- **`markdownify`**: HTML to Markdown conversion (pure Python, no external dependencies)
- **`difflib`**: Standard library for diff (replaces PowerShell's `Compare-Object`)
- **`pathlib`**: Cross-platform path handling (replaces string concatenation)

#### UTF-8 Encoding in Python
- All file I/O uses explicit `encoding='utf-8'` parameter
- HTTP responses: `response.encoding = 'utf-8'`
- HTML report includes `<meta charset='UTF-8' />`
- markdownify handles UTF-8 via BeautifulSoup

#### Error Handling Pattern
```python
try:
    # Main operation
except SpecificException as e:
    print(f"Warning: {message}. Error: {e}")
    return default_value
```

#### Configuration Fallback Pattern (Python)
```python
config = {
    'option': config_json.get('Option') or 'default_value',
    'numeric': config_json.get('Numeric') if config_json.get('Numeric') is not None else 0
}
```

**Note**: Numeric options use `is not None` check to allow zero values.

#### Cross-Platform Compatibility
- `Path` objects handle platform-specific separators automatically

## Configuration Reference

All settings in `config.json` are optional (defaults apply):

| Setting | Default | Purpose |
|---------|---------|---------|
| `OpenAI_API_Key` | *required* | OpenAI API authentication |
| `OpenAI_ApiEndpoint` | `https://api.openai.com/v1/chat/completions` | API endpoint URL |
| `OpenAI_Model` | `gpt-4.1-nano` | Model for summarization |
| `OpenAI_Temperature` | `0.5` | Response creativity (0-1) |
| `Request_TimeoutSeconds` | `30` | HTTP timeout |
| `Request_MaxRetries` | `1` | Retry attempts on failure |
| `Request_RetryBackoffSeconds` | `1` | Base backoff delay |
| `Max_Diff_Lines` | `500` | Diff truncation limit |
| `Redaction_Patterns` | [see config.example.json] | Regex array for sensitive data |
| `Sites_File` | `website.txt` | URL list file |
| `Output_Directory` | `output` | Storage directory |
| `Crawl_DelaySeconds` | `3` | Politeness delay between requests |
| `HTML_Filtering_Enabled` | `true` | Enable HTML content filtering |
| `HTML_Filtering_Method` | `trafilatura` | Primary filtering method |
| `HTML_Filtering_Fallback` | `beautifulsoup` | Fallback filtering method |
| `Trafilatura_Options` | [see config.example.json] | Trafilatura extraction options |
| `BeautifulSoup_Remove_Elements` | [see config.example.json] | HTML elements to remove |
| `BeautifulSoup_Remove_Class_Patterns` | [see config.example.json] | CSS class patterns to remove |
| `Markdown_Cleanup_Enabled` | `true` | Enable Markdown cleanup before diff |
| `Markdown_Cleanup_Patterns` | [see config.example.json] | Regex patterns for structural noise removal |

## Output Files

- `output/YYYY-MM-DD/hostname.html`: Redacted and filtered HTML snapshots (main content only)
- `output/YYYY-MM-DD/hostname.md`: Cleaned Markdown (structural noise removed, ready for comparison)
- `reports/report-YYYY-MM-DD.html`: Daily change report with AI summaries (file path displayed after generation)

## Dependencies

- Python 3.8+
- Python packages (see `requirements.txt`):
  - `requests>=2.31.0` - HTTP client
  - `openai>=2.17.0` - OpenAI API client
  - `markdownify>=1.2.2` - HTML to Markdown conversion
  - `trafilatura>=2.0.0` - HTML content extraction
  - `beautifulsoup4>=4.12.0` - HTML parsing (fallback)
  - `lxml>=5.0.0` - Fast XML/HTML parser
