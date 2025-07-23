# Custom Datasource Management CLI for Glean

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![UV](https://img.shields.io/badge/package%20manager-uv-purple.svg)](https://github.com/astral-sh/uv)

A self-contained Python script for creating and managing custom datasources in Glean.

 This tool provides both interactive and automated modes for datasource setup, configuration export/import, and template generation.

If you are looking to create a new Glean custom datasource, or backup the configuration from one, this is the tool for you!

## Prerequisites

### Install uv

This script uses [uv](https://github.com/astral-sh/uv) for Python package management:

```bash
# macOS
brew install uv

# Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Python Version

- Requires Python 3.13 or later

## Quick Start

```bash
# Run the script (shows help)
uv run manage.py

# Interactive setup (recommended for first-time users)
uv run manage.py setup

# Silent setup (no confirmation prompts)
uv run manage.py setup --silent

# Read config of custom datasource from Glean
uv run manage.py config <datasource_id>

# Export config for a custom datasource from Glean
# 💡 Tip: You can push this again to Glean using the 'setup' commands above!
uv run manage.py config <datasource_id> --save
```

## Commands

### `setup` - Create or Update a Datasource

Interactive or automated datasource creation.

```bash
# Interactive mode (default)
uv run manage.py setup

# Silent mode - no prompts, uses environment variables
uv run manage.py setup --silent

# Force overwrite existing datasource (requires --silent)
uv run manage.py setup --silent --force
```

### `config` - View and Export Datasource Configuration

Fetch configuration from an existing Glean datasource.

```bash
# View configuration
uv run manage.py config <datasource_id>

# Export configuration to files
uv run manage.py config <datasource_id> --save
```

When using `--save`, creates a directory with:
- `<datasource_id>.env` - Environment configuration
- `object_types.json` - Object type definitions (if any)
- `quick_links.json` - Quick link definitions (if any)
- Icon files (extracted from data URLs)

### `generate-object-template` - Create Object Types Template

Generate a sample `object_types.json` file with examples.

```bash
uv run manage.py generate-object-template
```

### `generate-quicklinks-template` - Create Quick Links Template

Generate a sample `quick_links.json` file with examples.

```bash
uv run manage.py generate-quicklinks-template
```

### `generate-example-env` - Create Environment File Template

Generate a `.env.setup.example` file with all available variables.

```bash
uv run manage.py generate-example-env
```

### `check-categories` - List Datasource Categories

Display available Glean datasource categories and their descriptions.

```bash
uv run manage.py check-categories
```

## Environment Variables

### Required Variables

| Variable                        | Description                                                      |
| ------------------------------- | ---------------------------------------------------------------- |
| `GLEAN_INDEXING_API_KEY`        | API key for Glean Indexing API                                   |
| `GLEAN_INSTANCE_NAME`           | Your Glean instance name (e.g., "mycompany")                     |
| `GLEAN_DATASOURCE_DISPLAY_NAME` | Display name for the datasource (max 50 chars)                   |
| `GLEAN_DATASOURCE_ID`           | Unique ID for the datasource (lowercase, alphanumeric + hyphens) |
| `GLEAN_DATASOURCE_HOME_URL`     | Home URL of the datasource                                       |

### Optional Variables

| Variable                                    | Description                                    | Default              |
| ------------------------------------------- | ---------------------------------------------- | -------------------- |
| `GLEAN_DATASOURCE_CATEGORY`                 | Datasource category                            | `KNOWLEDGE_HUB`      |
| `GLEAN_DATASOURCE_URL_REGEX`                | URL pattern for documents                      | `<home_url>/.*`      |
| `GLEAN_DATASOURCE_ICON_FILENAME_LIGHTMODE`  | Path to light mode icon file                   | `icon-lightmode.png` |
| `GLEAN_DATASOURCE_ICON_URL_LIGHTMODE`       | URL for light mode icon                        | -                    |
| `GLEAN_DATASOURCE_ICON_FILENAME_DARKMODE`   | Path to dark mode icon file                    | `icon-darkmode.png`  |
| `GLEAN_DATASOURCE_ICON_URL_DARKMODE`        | URL for dark mode icon                         | -                    |
| `GLEAN_DATASOURCE_USER_REFERENCED_BY_EMAIL` | Users referenced by email (true) or ID (false) | `true`               |
| `GLEAN_DATASOURCE_IS_TEST_MODE`             | Start in test mode                             | `true`               |
| `GLEAN_DATASOURCE_TEST_USER_EMAILS`         | Comma-separated test user emails               | -                    |
| `GLEAN_DATASOURCE_SUGGESTION_TEXT`          | Search suggestion text                         | Auto-generated       |

## Configuration Files

### Icons

The script looks for icons in this order:
1. File specified in `GLEAN_DATASOURCE_ICON_FILENAME_*` environment variable
2. URL specified in `GLEAN_DATASOURCE_ICON_URL_*` environment variable
3. Default files: `icon-lightmode.png` and `icon-darkmode.png` in current directory

Supported formats: PNG, SVG

### object_types.json

Defines custom object types for your datasource. Structure:

```json
{
  "objectTypes": [
    {
      "name": "article",
      "display_label": "Article",
      "doc_category": "PUBLISHED_CONTENT",
      "summarizable": true,
      "property_definitions": [...],
      "property_groups": [...]
    }
  ]
}
```

### quick_links.json

Defines quick action links for your datasource. Structure:

```json
{
  "quicklinks": [
    {
      "name": "Create New Item",
      "short_name": "New Item",
      "url": "https://example.com/create",
      "id": "create-item",
      "icon_config": {
        "icon_type": "GLYPH",
        "name": "plus",
        "color": "#343CED"
      },
      "scopes": ["APP_CARD", "AUTOCOMPLETE_EXACT_MATCH"]
    }
  ]
}
```

## Example Workflows

### 1. First-Time Setup

```bash
# Generate templates
uv run manage.py generate-example-env
uv run manage.py generate-object-template
uv run manage.py generate-quicklinks-template

# Edit .env with your values
cp .env.setup.example .env
# Edit .env file...

# Add icon files
# Place icon-lightmode.png and icon-darkmode.png in current directory

# Run interactive setup
uv run manage.py setup
```

### 2. Automated Deployment

```bash
# Set all required environment variables
export GLEAN_INDEXING_API_KEY="your-api-key"
export GLEAN_INSTANCE_NAME="mycompany"
export GLEAN_DATASOURCE_DISPLAY_NAME="My Datasource"
export GLEAN_DATASOURCE_ID="my-datasource"
export GLEAN_DATASOURCE_HOME_URL="https://myapp.com"

# Run silent setup
uv run manage.py setup --silent --force
```

### 3. Backup and Restore Configuration

```bash
# Export existing datasource configuration
uv run manage.py config my-datasource --save

# This creates my-datasource-config/ directory with all settings

# To recreate on another system:
cd my-datasource-config/
cp my-datasource.env .env
# Add your API key to .env
uv run ../manage.py setup --silent
```

### 4. Testing with Limited Users

```bash
# Set test mode variables
export GLEAN_DATASOURCE_IS_TEST_MODE=true
export GLEAN_DATASOURCE_TEST_USER_EMAILS="user1@company.com,user2@company.com"

# Create datasource in test mode
uv run manage.py setup
```

## Tips

1. **Icon Requirements**: Icons should be square and at least 256x256 pixels for best results.

2. **Datasource IDs**: Once created, datasource IDs cannot be changed. Choose carefully.

3. **URL Regex**: The URL pattern determines which documents belong to your datasource. Default is `<home_url>/.*` which matches all pages under your home URL.

4. **Test Mode**: Always start in test mode to verify your configuration before making the datasource available to all users.

5. **Categories**: Use `check-categories` to see available categories and choose the most appropriate one for your content type.

## Troubleshooting

### "Icon file not found" Error
- Ensure icon files exist in the current directory or specified path
- Check file extensions match (.png or .svg)
- Use absolute paths in environment variables

### "Datasource already exists" Error
- Use `--force` flag with `--silent` to overwrite
- Or delete the datasource in Glean UI first

### API Authentication Errors
- Verify your API key has indexing permissions
- Check instance name matches your Glean URL (e.g., if URL is `mycompany.glean.com`, instance is `mycompany`)

## After Setup

Once your datasource is created, you can:
1. View it in Glean UI at: `https://app.glean.com/admin/setup/apps/custom/<datasource_id>`
2. Start indexing documents using the Glean Indexing API
3. Manage test users and permissions in the Glean admin interface