#!/usr/bin/env python3
"""
Website-monitor: Website monitoring tool with AI-powered change summaries.

This script monitors websites for changes and generates intelligent summaries
using OpenAI's API. It compares daily crawls and creates HTML reports with
visual diffs.

Cross-platform: Windows, Linux, macOS
Requirements: Python 3.8+, requests, openai, markdownify
"""

import sys
import json
import time
import re
import html
import difflib
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Third-party imports
import requests
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
import markdownify as md

# Module-level warning tracking
_warnings_shown = set()


# --- Markdown Conversion ---

def convert_to_markdown(html_path):
    """
    Converts HTML file to Markdown using markdownify.

    Args:
        html_path: Path to HTML file (e.g., output/2026-02-08/example.com.html)

    Returns:
        Path to converted Markdown file (e.g., output/2026-02-08/example.com.md)
        Falls back to html_path if conversion fails
    """
    md_path = html_path.with_suffix('.md')

    try:
        html_content = html_path.read_text(encoding='utf-8')
        md_content = md.markdownify(html_content, heading_style="ATX", strip=['img'])
        md_path.write_text(md_content, encoding='utf-8')
        print(f" - Converted to {md_path}")
        return md_path

    except Exception as e:
        print(f"Warning: Failed to convert {html_path} to Markdown. Error: {e}")
        return html_path


# --- HTML Content Filtering ---

def filter_html_content(html_content, config):
    """
    Filters HTML content to extract main content before pandoc conversion.

    Uses a 3-tier fallback strategy:
    1. Trafilatura (best accuracy, purpose-built)
    2. BeautifulSoup (manual rules)
    3. Original HTML (if both fail)

    Args:
        html_content: Raw HTML string
        config: Configuration dict with filtering settings

    Returns:
        Filtered HTML string, or original if filtering fails/disabled
    """
    if not config.get('html_filtering_enabled', True):
        return html_content

    original_len = len(html_content)
    method = config.get('html_filtering_method', 'trafilatura')

    # Tier 1: Try trafilatura
    if method == 'trafilatura':
        filtered = _filter_with_trafilatura(html_content, config)
        if _is_valid_filtered_html(filtered, original_len):
            print(f" - HTML filtering (trafilatura): {original_len:,} → {len(filtered):,} chars ({100 - int(len(filtered)/original_len*100)}% reduction)")
            return filtered
        if filtered is not None:  # Failed validation
            print(f" - Trafilatura output too short ({len(filtered)} chars), trying fallback...")
        # If filtered is None, trafilatura failed or not installed

    # Tier 2: Try BeautifulSoup
    fallback_method = config.get('html_filtering_fallback', 'beautifulsoup')
    if fallback_method == 'beautifulsoup':
        filtered = _filter_with_beautifulsoup(html_content, config)
        if _is_valid_filtered_html(filtered, original_len):
            print(f" - HTML filtering (beautifulsoup): {original_len:,} → {len(filtered):,} chars ({100 - int(len(filtered)/original_len*100)}% reduction)")
            return filtered
        if filtered is not None:  # Failed validation
            print(f" - BeautifulSoup output too short ({len(filtered)} chars)")

    # Tier 3: Return original
    print(f" - HTML filtering: Using original HTML (no filtering applied)")
    return html_content


def _filter_with_trafilatura(html_content, config):
    """Filter HTML using trafilatura library."""
    try:
        # Check if trafilatura is available (cache result)
        if not hasattr(_filter_with_trafilatura, 'module_available'):
            try:
                import trafilatura
                _filter_with_trafilatura.module = trafilatura
                _filter_with_trafilatura.module_available = True
                print(" - HTML filtering: Using trafilatura for content extraction")
            except ImportError:
                _filter_with_trafilatura.module_available = False

        if not _filter_with_trafilatura.module_available:
            if 'trafilatura' not in _warnings_shown:
                print("   Warning: trafilatura not installed, using BeautifulSoup fallback")
                print("   Install with: pip install trafilatura")
                _warnings_shown.add('trafilatura')
            return None

        trafilatura = _filter_with_trafilatura.module
        options = config.get('trafilatura_options', {})

        # Extract with configured options
        extracted = trafilatura.extract(
            html_content,
            include_links=options.get('include_links', True),
            include_images=options.get('include_images', False),
            include_formatting=options.get('include_formatting', True),
            deduplicate=options.get('deduplicate', True),
            favor_precision=options.get('favor_precision', False),
            output_format='html'  # Returns cleaned HTML
        )

        return extracted

    except Exception as e:
        print(f"   Warning: Trafilatura error: {e}")
        return None


def _filter_with_beautifulsoup(html_content, config):
    """Filter HTML using BeautifulSoup with manual rules."""
    try:
        from bs4 import BeautifulSoup

        # Parse with lxml parser (fastest)
        soup = BeautifulSoup(html_content, 'lxml')

        # Step 1: Remove unwanted elements (nav, header, footer, etc.)
        remove_elements = config.get('beautifulsoup_remove_elements', [])
        for tag_name in remove_elements:
            for element in soup.find_all(tag_name):
                element.decompose()

        # Step 2: Remove elements by class/id patterns (only for clearly non-content areas)
        remove_patterns = config.get('beautifulsoup_remove_class_patterns', [])
        for pattern in remove_patterns:
            # Remove by class - be more conservative, only exact matches
            for element in soup.find_all(class_=lambda x: x and any(pattern.lower() == cls.lower() for cls in str(x).split())):
                element.decompose()
            # Remove by id - only exact matches
            for element in soup.find_all(id=lambda x: x and pattern.lower() == str(x).lower()):
                element.decompose()

        # Step 3: Get the filtered content
        # Try to find main content container first
        main_content = None
        for selector in ['main', 'article', '[role="main"]', '#readme', '.markdown-body']:
            if selector.startswith('#'):
                # ID selector
                main_content = soup.find(id=selector[1:])
            elif selector.startswith('.'):
                # Class selector
                main_content = soup.find(class_=selector[1:])
            elif selector.startswith('['):
                # Attribute selector
                main_content = soup.find(attrs={'role': 'main'})
            else:
                # Tag selector
                main_content = soup.find(selector)
            if main_content:
                break

        # If found, use only that container; otherwise use whole body
        if main_content:
            filtered_html = str(main_content)
        else:
            # Use body (which already has unwanted elements removed)
            body = soup.find('body')
            filtered_html = str(body) if body else str(soup)

        return filtered_html

    except ImportError:
        if 'beautifulsoup' not in _warnings_shown:
            print("   Warning: BeautifulSoup not installed (pip install beautifulsoup4 lxml)")
            _warnings_shown.add('beautifulsoup')
        return None
    except Exception as e:
        print(f"   Warning: BeautifulSoup error: {e}")
        return None


def _is_valid_filtered_html(filtered_html, original_len, min_chars=100):
    """
    Validate filtered HTML is usable.

    Args:
        filtered_html: Filtered HTML string (or None)
        original_len: Length of original HTML
        min_chars: Minimum character threshold (default: 100)

    Returns:
        True if filtered HTML is valid and usable
    """
    if filtered_html is None:
        return False

    filtered_len = len(filtered_html.strip())

    # Must have minimum content
    if filtered_len < min_chars:
        return False

    # Shouldn't be excessively short compared to original (possible over-filtering)
    # Allow up to 99% reduction (some pages like GitHub have 95%+ noise)
    # But ensure we have meaningful content (checked by min_chars above)
    if filtered_len < original_len * 0.01:
        return False

    return True


# --- Configuration ---

def load_config(config_path):
    """
    Loads configuration with fallback defaults.

    Args:
        config_path: Path to config.json file

    Returns:
        tuple: (api_key, config_dict)

    Raises:
        SystemExit: If config file not found or API key not configured
    """
    # Validate config file exists
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Load JSON
    with open(config_path, 'r', encoding='utf-8') as f:
        config_json = json.load(f)

    # Validate API key
    api_key = config_json.get('OpenAI_API_Key', '')
    if not api_key or api_key.strip() == '' or api_key == 'YOUR_API_KEY_HERE':
        print("Error: OpenAI API key is not configured in config.json. Please add your key.", file=sys.stderr)
        sys.exit(1)

    # Get config values that need None-checking (avoid duplicate .get() calls)
    openai_temp = config_json.get('OpenAI_Temperature')
    request_max_retries = config_json.get('Request_MaxRetries')
    html_filtering_enabled = config_json.get('HTML_Filtering_Enabled')
    markdown_cleanup_enabled = config_json.get('Markdown_Cleanup_Enabled')

    # Configuration with defaults (fallback pattern)
    config = {
        'openai_api_endpoint': config_json.get('OpenAI_ApiEndpoint') or 'https://api.openai.com/v1',
        'openai_model': config_json.get('OpenAI_Model') or 'gpt-4o-mini',
        'openai_reasoning_effort': config_json.get('OpenAI_ReasoningEffort') or 'low',
        'openai_temperature': openai_temp if openai_temp is not None else 0.5,
        'request_timeout_seconds': config_json.get('Request_TimeoutSeconds') or 30,
        'request_max_retries': request_max_retries if request_max_retries is not None else 1,
        'request_retry_backoff_seconds': config_json.get('Request_RetryBackoffSeconds') or 1,
        'max_diff_lines': config_json.get('Max_Diff_Lines') or 500,
        'redaction_patterns': config_json.get('Redaction_Patterns') or [
            r"password\s*[:=]\s*[\"'][^\"'>]*[\"']",
            r"api[_-]?key\s*[:=]\s*[\"'][^\"'>]*[\"']",
            r"token\s*[:=]\s*[\"'][^\"'>]*[\"']"
        ],
        'sites_file': config_json.get('Sites_File') or 'website.txt',
        'output_directory': config_json.get('Output_Directory') or 'output',
        'crawl_delay_seconds': config_json.get('Crawl_DelaySeconds') or 3,
        # HTML filtering configuration
        'html_filtering_enabled': html_filtering_enabled if html_filtering_enabled is not None else True,
        'html_filtering_method': config_json.get('HTML_Filtering_Method') or 'trafilatura',
        'html_filtering_fallback': config_json.get('HTML_Filtering_Fallback') or 'beautifulsoup',
        'trafilatura_options': config_json.get('Trafilatura_Options') or {
            'include_links': True,
            'include_images': False,
            'include_formatting': True,
            'deduplicate': True,
            'favor_precision': False
        },
        'beautifulsoup_remove_elements': config_json.get('BeautifulSoup_Remove_Elements') or [
            'nav', 'header', 'footer', 'aside',
            'script', 'style', 'noscript',
            'form', 'input', 'button', 'select', 'textarea',
            'iframe', 'embed', 'object',
            'img', 'svg', 'picture'  # Remove images including data:image Base64
        ],
        'beautifulsoup_remove_class_patterns': config_json.get('BeautifulSoup_Remove_Class_Patterns') or [
            'sidebar', 'menu', 'navigation', 'nav',
            'header', 'footer', 'breadcrumb',
            'advertisement', 'ad-', 'social',
            'share', 'comment', 'cookie', 'popup'
        ],
        # Markdown cleanup configuration
        'markdown_cleanup_enabled': markdown_cleanup_enabled if markdown_cleanup_enabled is not None else True,
        'markdown_cleanup_patterns': config_json.get('Markdown_Cleanup_Patterns') or [
            r'^:::.*$',                    # Pandoc fenced divs
            r'^{\..*}$',                   # CSS class attributes
            r'^</?div.*>$',                # Div tags (with or without attributes)
            r'^</?span.*>$',               # Span tags (with or without attributes)
            r'^</?figure.*>$',             # Figure tags
            r'^\[\]$'                      # Empty links (standalone)
        ]
    }

    # Clear sensitive data
    del config_json

    return api_key, config


# --- Core Functions ---

def generate_filename(url):
    """
    Generates unique filename from URL using hostname + hash.

    Args:
        url: Website URL

    Returns:
        str: Filename without extension
    """
    parsed_uri = urlparse(url)
    hostname = parsed_uri.netloc

    # Create hash from path + query to ensure uniqueness
    # Use path + query (everything after hostname)
    url_suffix = parsed_uri.path + ('?' + parsed_uri.query if parsed_uri.query else '')

    # Generate MD5 hash (8 characters is enough for uniqueness in typical use cases)
    hash_obj = hashlib.md5(url_suffix.encode('utf-8'))
    url_hash = hash_obj.hexdigest()[:8]

    # Combine hostname and hash
    filename = f"{hostname}-{url_hash}"

    return filename


def get_site_content(url, directory, redaction_patterns, config):
    """
    Downloads webpage, applies redaction, filters HTML, saves HTML, converts to Markdown.

    Args:
        url: Website URL to fetch
        directory: Directory to save HTML file
        redaction_patterns: List of regex patterns for redaction
        config: Configuration dict with HTML filtering settings

    Returns:
        dict with keys: success, file_path (HTML), md_path (Markdown), filename, content
    """
    try:
        print(f"Processing {url}")
        filename = generate_filename(url)
        html_path = directory / f"{filename}.html"

        # Fetch content
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        filtered_content = response.text

        # Apply redaction patterns
        for pattern in redaction_patterns:
            filtered_content = re.sub(pattern, '***', filtered_content)

        # Apply HTML content filtering (function checks if enabled internally)
        filtered_content = filter_html_content(filtered_content, config)

        # Save HTML (now contains filtered content)
        html_path.write_text(filtered_content, encoding='utf-8')
        print(f" - Saved HTML to {html_path}")

        # Convert to Markdown
        md_path = convert_to_markdown(html_path)

        # Clean the markdown file and save cleaned version
        if md_path.suffix == '.md':  # Only clean if pandoc conversion succeeded
            md_content = md_path.read_text(encoding='utf-8')
            cleaned_md = clean_markdown_for_diff(md_content, config)
            md_path.write_text(cleaned_md, encoding='utf-8')
            print(f" - Cleaned and saved to {md_path}")

        return {
            'success': True,
            'file_path': html_path,      # HTML file path
            'md_path': md_path,           # Markdown file path (for comparison)
            'filename': filename,         # Unique filename (without extension)
            'content': filtered_content
        }
    except Exception as e:
        print(f"Warning: Failed to process '{url}'. Error: {e}")
        return {'success': False}


def clean_markdown_for_diff(md_content, config):
    """
    Cleans Markdown content for diff comparison by removing structural noise.

    Removes:
    - Pandoc fenced divs (:::)
    - CSS class attributes ({.class-name} and {#id .class-name})
    - HTML tags and attributes
    - Empty links and text fragments
    - Excessive blank lines

    Args:
        md_content: Raw Markdown content string
        config: Configuration dict with cleaning settings

    Returns:
        Cleaned Markdown content string
    """
    if not config.get('markdown_cleanup_enabled', True):
        return md_content

    lines = md_content.split('\n')
    cleaned_lines = []

    # Get patterns from config for line removal
    patterns = config.get('markdown_cleanup_patterns')

    # Compile patterns
    compiled_patterns = [re.compile(p) for p in patterns]

    for line in lines:
        # Skip lines matching any cleanup pattern
        if any(pattern.match(line.strip()) for pattern in compiled_patterns):
            continue

        # Remove inline Pandoc attributes: {.class}, {#id .class}, {key=value}
        # Matches: {.xxx}, {#xxx}, {.xxx .yyy}, {#id .class .another}, etc.
        line = re.sub(r'\{[#\.]?[^}]*\}', '', line)

        # Remove HTML attributes from tags: target="...", rel="...", class="...", etc.
        # Matches: attribute="value" or attribute='value'
        line = re.sub(r'\s+(?:target|rel|class|style|id|role|aria-[\w-]+)=["\'][^"\']*["\']', '', line)

        # Remove HTML tags with attributes: <tag attr="value">
        line = re.sub(r'<(\w+)[^>]*>', r'<\1>', line)

        # Remove common empty HTML tags
        line = re.sub(r'<(div|span|figure|section|article|header|footer|aside)>\s*</\1>', '', line)

        # Remove empty Markdown links: []
        line = re.sub(r'\[\]\s*', '', line)

        # Remove Markdown links with empty text: [](url) or []()
        line = re.sub(r'\[\s*\]\([^)]*\)', '', line)

        # Remove standalone link URLs in parentheses: (url)
        line = re.sub(r'^\s*\([^)]+\)\s*$', '', line)

        # Skip if line becomes empty or just whitespace after cleaning
        if not line.strip():
            continue

        cleaned_lines.append(line)

    # Join and remove excessive blank lines
    cleaned_content = '\n'.join(cleaned_lines)

    # Reduce multiple consecutive blank lines to single blank line
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)

    return cleaned_content


def compare_site_content(old_md_path, new_md_path, config):
    """
    Compares two cleaned Markdown files line-by-line.

    Args:
        old_md_path: Previous crawl's Markdown file (already cleaned)
        new_md_path: Current crawl's Markdown file (already cleaned)
        config: Configuration dict (not used, kept for compatibility)

    Returns:
        List of diff dicts with 'InputObject' and 'SideIndicator' keys, or None
    """
    if not old_md_path.exists():
        print(" - Previous Markdown file not found, skipping comparison.")
        return None

    print(f" - Comparing with {old_md_path}")

    # Read Markdown files (already cleaned when saved)
    old_content = old_md_path.read_text(encoding='utf-8')
    new_content = new_md_path.read_text(encoding='utf-8')

    # Split into lines
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    # Use difflib.Differ
    differ = difflib.Differ()
    diff = list(differ.compare(old_lines, new_lines))

    # Convert to PowerShell-like format
    result = []
    for line in diff:
        if line.startswith('- '):
            result.append({'InputObject': line[2:], 'SideIndicator': '<='})
        elif line.startswith('+ '):
            result.append({'InputObject': line[2:], 'SideIndicator': '=>'})
        # Skip '  ' (unchanged) and '? ' (hints)

    return result if result else None


def summarize_changes(site_change, api_key, config):
    """
    Generates AI summary of website changes using OpenAI API.

    Args:
        site_change: Dict with 'url' and 'diff' keys
        api_key: OpenAI API key
        config: Configuration dict with API settings

    Returns:
        Summary text in Japanese
    """
    try:
        print(f"Summarizing changes for {site_change['url']}")

        # Format diff with truncation if needed
        diff_lines = []
        for diff_obj in site_change['diff']:
            indicator = '-' if diff_obj['SideIndicator'] == '<=' else '+'
            diff_lines.append(f"{indicator}{diff_obj['InputObject']}")

        max_diff_lines = config['max_diff_lines']

        # Truncate diff if it exceeds max_diff_lines
        if len(diff_lines) > max_diff_lines:
            half_lines = max_diff_lines // 2
            omitted_count = len(diff_lines) - max_diff_lines
            formatted_diff = '\n'.join(
                diff_lines[:half_lines] +
                [f"... (中略 {omitted_count} 行) ..."] +
                diff_lines[-half_lines:]
            )
        else:
            formatted_diff = '\n'.join(diff_lines)

        prompt = f"""# Role
You are a web content analyst specializing in detecting meaningful changes between website versions.

# Task
Analyze the provided Markdown diff and summarize user-visible changes in Japanese.

# Guidelines
- **Focus on:** Text content changes, new/removed sections, structural changes (headings, lists, tables)
- **Ignore:** Minor formatting differences, whitespace changes
- **Output format:** Bulleted list in Japanese, categorized as "追加", "変更", "削除" if needed

# Input
Below is a diff comparing cleaned Markdown content (`-` = removed, `+` = added):

```diff
{formatted_diff}
```
"""

        # Initialize OpenAI client
        client = OpenAI(
            api_key=api_key,
            base_url=config['openai_api_endpoint'],
            timeout=config['request_timeout_seconds']
        )

        # API call with retry logic
        retries = 0
        max_retries = config['request_max_retries']

        while retries <= max_retries:
            try:
                response = client.chat.completions.create(
                    model=config['openai_model'],
                    reasoning_effort=config['openai_reasoning_effort'],
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant who summarizes website changes for a user."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=config['openai_temperature']
                )

                # Validate response
                if not response.choices or not response.choices[0].message:
                    raise ValueError("Invalid API response structure")

                summary = response.choices[0].message.content.strip()
                print(" - Summary received.")
                return summary

            except (APIError, RateLimitError, APIConnectionError) as e:
                retries += 1
                if retries <= max_retries:
                    backoff = config['request_retry_backoff_seconds'] * retries
                    print(f" - API call failed, retrying in {backoff} seconds...")
                    time.sleep(backoff)
                else:
                    raise

    except Exception as e:
        print(f"Warning: Failed to get summary for '{site_change['url']}'. Error: {e}")
        return "Failed to generate summary."


def generate_report(changed_sites, report_path, timestamp):
    """
    Generates an interactive HTML report with collapsible diffs.

    Args:
        changed_sites: List of dicts with 'url', 'diff', 'summary' keys
        report_path: Path to save HTML report
        timestamp: Timestamp string (YYYY-MM-DD format)
    """
    print("\n--- Generating HTML report... ---")

    css = """<style>
    body { font-family: sans-serif; line-height: 1.6; }
    h1, h2 { border-bottom: 2px solid #eee; padding-bottom: 5px; }
    .site-section { border: 1px solid #ccc; padding: 10px; margin-bottom: 20px; border-radius: 5px; }
    .summary { background-color: #f8f9fa; border-left: 5px solid #007bff; padding: 10px; margin-top: 10px; }
    pre { background-color: #f1f1f1; padding: 10px; border-radius: 3px; white-space: pre-wrap; word-wrap: break-word; }
    .diff-add { color: #28a745; }
    .diff-del { color: #dc3545; text-decoration: line-through; }
    .toggle-details { cursor: pointer; }
    .details-content { display: none; }
</style>"""

    javascript = """<script>
    function toggleDetails(id) {
        var element = document.getElementById(id);
        if (element.style.display === 'none' || element.style.display === '') {
            element.style.display = 'block';
        } else {
            element.style.display = 'none';
        }
    }
</script>"""

    html_body = f"<h1>Website Monitor Report - {timestamp}</h1>"

    for site_index, site in enumerate(changed_sites):
        # Format diff with HTML encoding
        html_diff_lines = []
        for diff_obj in site['diff']:
            line = html.escape(diff_obj['InputObject'])
            if diff_obj['SideIndicator'] == '<=':
                html_diff_lines.append(f"<span class='diff-del'>-{line}</span>")
            elif diff_obj['SideIndicator'] == '=>':
                html_diff_lines.append(f"<span class='diff-add'>+{line}</span>")
            else:
                html_diff_lines.append(line)

        html_diff = '\n'.join(html_diff_lines)

        # HTML encode summary and convert newlines to <br>
        encoded_summary = html.escape(site['summary']).replace('\n', '<br>')

        details_id = f"details-{site_index}"

        html_body += f"""<div class='site-section'>
    <h2><a href='{site['url']}' target='_blank'>{site['url']}</a></h2>
    <h3>Summary of Changes</h3>
    <div class='summary'>
        <p>{encoded_summary}</p>
    </div>
    <h3 class='toggle-details' onclick="toggleDetails('{details_id}')">Detail (click to toggle)</h3>
    <pre id='{details_id}' class='details-content'>{html_diff}</pre>
</div>
"""

    html_content = f"""<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8' />
    <title>Website Monitor Report</title>
    {css}
    {javascript}
</head>
<body>
    {html_body}
</body>
</html>
"""

    # Write with explicit UTF-8 encoding
    report_path.write_text(html_content, encoding='utf-8')
    print(f" - Report saved to {report_path}")


# --- Utility Functions ---

def setup_directories(base_dir, output_dir_name, timestamp):
    """
    Sets up output directories and finds previous crawl directory.

    Args:
        base_dir: Base directory path
        output_dir_name: Output directory name
        timestamp: Timestamp string (YYYY-MM-DD format)

    Returns:
        tuple: (today_dir, previous_dir or None)
    """
    # Create output directory
    output_dir = base_dir / output_dir_name
    output_dir.mkdir(exist_ok=True)

    # Create today's directory
    today_dir = output_dir / timestamp
    today_dir.mkdir(exist_ok=True)

    # Find previous crawl directory
    all_dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()])

    if len(all_dirs) > 1:
        # Get second-to-last directory (last is today)
        previous_dir = all_dirs[-2]
        print(f"Previous crawl directory found: {previous_dir}")
    else:
        previous_dir = None
        print("No previous crawl directory found. Skipping diff check.")

    return today_dir, previous_dir


# --- Main Execution ---

def main():
    """Main execution function"""
    # Setup
    base_dir = Path.cwd()
    config_path = base_dir / 'config.json'
    timestamp = datetime.now().strftime('%Y-%m-%d')

    # Load configuration
    api_key, config = load_config(config_path)

    # Setup directories
    today_dir, previous_dir = setup_directories(base_dir, config['output_directory'], timestamp)

    # Load URLs
    website_list_path = base_dir / config['sites_file']
    if not website_list_path.exists():
        print(f"Error: Website list file not found: {website_list_path}", file=sys.stderr)
        sys.exit(1)

    urls = website_list_path.read_text(encoding='utf-8').strip().split('\n')
    urls = [url.strip() for url in urls if url.strip()]  # Remove empty lines

    # Main processing loop
    changed_sites = []

    for url in urls:
        # Crawl and convert
        crawl_result = get_site_content(url, today_dir, config['redaction_patterns'], config)
        if not crawl_result['success']:
            time.sleep(config['crawl_delay_seconds'])
            continue

        # Compare with previous crawl (using Markdown files)
        if previous_dir:
            previous_md_path = previous_dir / f"{crawl_result['filename']}.md"
            current_md_path = crawl_result['md_path']

            diff = compare_site_content(previous_md_path, current_md_path, config)

            if diff and len(diff) > 0:
                print(" - Differences found!")
                change = {
                    'url': url,
                    'diff': diff,
                    'new_content': crawl_result['content']
                }
                changed_sites.append(change)

        time.sleep(config['crawl_delay_seconds'])

    # Summarization and reporting
    if changed_sites:
        print(f"\n--- Found {len(changed_sites)} sites with changes. Summarizing with OpenAI... ---")

        for site in changed_sites:
            summary = summarize_changes(site, api_key, config)
            site['summary'] = summary

        # Clear API key from memory
        api_key = None
        del api_key

        # Generate report
        report_dir = base_dir / 'reports'
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"report-{timestamp}.html"
        generate_report(changed_sites, report_path, timestamp)

        print(f"\nTo view the report, open this file in your browser: {report_path}")

    print("Script finished.")


if __name__ == '__main__':
    main()
