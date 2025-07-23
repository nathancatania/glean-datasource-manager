#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "glean-api-client",
#     "rich",
#     "click",
#     "pydantic",
#     "pydantic-settings",
#     "httpx",
# ]
# ///

"""Glean Custom Datasource Management Tool."""

VERSION = "0.1.0"

import base64
import json
import os
import re
import sys
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

import click
import httpx
from glean.api_client import Glean, models
from glean.api_client.models import DocCategory, DatasourceCategory as GleanDatasourceCategory
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

console = Console()


def log_info(message: str) -> None:
    """Log info message."""
    console.print(f"[cyan]ℹ[/cyan] {message}")


def log_success(message: str) -> None:
    """Log success message."""
    console.print(f"[green]✓[/green] {message}")


def log_error(message: str) -> None:
    """Log error message."""
    console.print(f"[red]✗[/red] {message}")


def log_warning(message: str) -> None:
    """Log warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def display_banner(command_title: str, command_desc: str) -> None:
    """Display a consistent banner for commands."""
    banner_content = f"[bold cyan]Glean Custom Datasource Manager (v{VERSION})[/bold cyan]\n"
    banner_content += "[dim]https://github.com/nathancatania/glean-datasource-manager[/dim]\n\n"
    banner_content += f"[bold]{command_title}[/bold]\n"
    banner_content += command_desc
    console.print(Panel.fit(banner_content, border_style="cyan"))
    console.print()


def normalize_datasource_id(display_name: str) -> str:
    """Convert display name to datasource ID format."""
    # Remove special characters and convert to lowercase
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", "", display_name)
    # Replace spaces with hyphens
    normalized = re.sub(r"\s+", "-", normalized)
    # Remove multiple consecutive hyphens
    normalized = re.sub(r"-+", "-", normalized)
    # Strip leading/trailing hyphens and convert to lowercase
    return normalized.strip("-").lower()


def get_icon_as_data_url(file_path: Path) -> str:
    """Convert an image file to a base64 data URL."""
    mime_types = {
        ".png": "image/png",
        ".svg": "image/svg+xml",
    }

    suffix = file_path.suffix.lower()
    if suffix not in mime_types:
        raise ValueError(f"Unsupported image format: {suffix}")

    with open(file_path, "rb") as f:
        content = f.read()

    base64_content = base64.b64encode(content).decode("utf-8")
    return f"data:{mime_types[suffix]};base64,{base64_content}"


def download_icon(url: str) -> str:
    """Download icon from URL and convert to data URL."""
    try:
        response = httpx.get(url, follow_redirects=True)
        response.raise_for_status()

        # Determine MIME type
        content_type = response.headers.get("content-type", "").lower()
        if "svg" in content_type:
            mime_type = "image/svg+xml"
        elif "png" in content_type:
            mime_type = "image/png"
        else:
            # Try to guess from URL
            if url.lower().endswith(".svg"):
                mime_type = "image/svg+xml"
            else:
                mime_type = "image/png"

        base64_content = base64.b64encode(response.content).decode("utf-8")
        return f"data:{mime_type};base64,{base64_content}"
    except Exception as e:
        raise ValueError(f"Failed to download icon from {url}: {e}")


def save_data_url_to_file(data_url: str, file_path: Path) -> str:
    """Extract and save base64 data URL content to a file.

    Returns the file extension used (png or svg).
    """
    if not data_url or not data_url.startswith("data:"):
        raise ValueError("Invalid data URL")

    # Parse data URL: data:image/png;base64,<content>
    match = re.match(r"data:([^;]+);base64,(.+)", data_url)
    if not match:
        raise ValueError("Invalid data URL format")

    mime_type, base64_content = match.groups()

    # Determine file extension from MIME type
    extension_map = {
        "image/png": "png",
        "image/svg+xml": "svg",
    }

    extension = extension_map.get(mime_type)
    if not extension:
        raise ValueError(f"Unsupported MIME type: {mime_type}")

    # Decode and save file
    content = base64.b64decode(base64_content)
    with open(file_path.with_suffix(f".{extension}"), "wb") as f:
        f.write(content)

    return extension


def load_object_definitions(file_path: str = "object_types.json") -> list[dict]:
    """Load object definitions from JSON file."""
    path = Path(file_path)
    if not path.exists():
        return []

    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data.get("objectTypes", [])
    except Exception as e:
        log_warning(f"Failed to load object definitions from {file_path}: {e}")
        return []


def load_quick_links(file_path: str = "quick_links.json") -> list[dict]:
    """Load quick links from JSON file."""
    path = Path(file_path)
    if not path.exists():
        return []

    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data.get("quicklinks", [])
    except Exception as e:
        log_warning(f"Failed to load quick links from {file_path}: {e}")
        return []


class DatasourceCategory(str, Enum):
    """Glean datasource categories."""

    KNOWLEDGE_HUB = "KNOWLEDGE_HUB"
    PUBLISHED_CONTENT = "PUBLISHED_CONTENT"
    COLLABORATIVE_CONTENT = "COLLABORATIVE_CONTENT"
    QUESTION_ANSWER = "QUESTION_ANSWER"
    TICKETS = "TICKETS"
    CODE_REPOSITORY = "CODE_REPOSITORY"
    CHANGE_MANAGEMENT = "CHANGE_MANAGEMENT"
    EMAIL = "EMAIL"
    MESSAGING = "MESSAGING"
    CRM = "CRM"
    SSO = "SSO"
    ATS = "ATS"
    PEOPLE = "PEOPLE"
    EXTERNAL_SHORTCUT = "EXTERNAL_SHORTCUT"
    UNCATEGORIZED = "UNCATEGORIZED"


CATEGORY_DESCRIPTIONS = {
    DatasourceCategory.KNOWLEDGE_HUB: "Reference documentation that may be continually updated as a source of truth, such as Github READMEs, Confluence documents, or ServiceNow knowledge articles",
    DatasourceCategory.PUBLISHED_CONTENT: "Blog posts published at a point in time, such as Brightspot posts or Confluence blog posts. Note that Confluence blog posts are different from other Confluence documents, which should be classified as KNOWLEDGE_HUB.",
    DatasourceCategory.COLLABORATIVE_CONTENT: "Documents that can be edited collaboratively, such as Google Drive, Dropbox, or Figma files",
    DatasourceCategory.QUESTION_ANSWER: "Question-answer content such as Stack Overflow posts",
    DatasourceCategory.TICKETS: "Work item or issue trackers such as Asana tasks, Jira tickets, or Github issues",
    DatasourceCategory.CODE_REPOSITORY: "Source code repositories such as Github repositories",
    DatasourceCategory.CHANGE_MANAGEMENT: "Code change management systems such as pull or merge requests on Github",
    DatasourceCategory.EMAIL: "Email content such as Gmail or Outlook messages",
    DatasourceCategory.MESSAGING: "Chat message or conversational content such as Slack or Discord messages",
    DatasourceCategory.CRM: "Customer relationship management systems such as Sales Cloud",
    DatasourceCategory.SSO: "Single-sign-on services such as Azure SSO or GSuite SSO",
    DatasourceCategory.ATS: "Applicant tracking systems such as Greenhouse",
    DatasourceCategory.PEOPLE: "This should not be used, please instead use the /bulkindexemployees API to upload data about employees",
    DatasourceCategory.EXTERNAL_SHORTCUT: "This should not be used; please contact us for guidance",
    DatasourceCategory.UNCATEGORIZED: "This should not be used; please contact us for guidance",
}


# Mapping dictionaries for Glean SDK enums
DOCUMENT_CATEGORY_MAP = {
    "KNOWLEDGE_HUB": DocCategory.KNOWLEDGE_HUB,
    "PUBLISHED_CONTENT": DocCategory.PUBLISHED_CONTENT,
    "COLLABORATIVE_CONTENT": DocCategory.COLLABORATIVE_CONTENT,
    "QUESTION_ANSWER": DocCategory.QUESTION_ANSWER,
    "TICKETS": DocCategory.TICKETS,
    "CODE_REPOSITORY": DocCategory.CODE_REPOSITORY,
    "CHANGE_MANAGEMENT": DocCategory.CHANGE_MANAGEMENT,
    "EMAIL": DocCategory.EMAIL,
    "MESSAGING": DocCategory.MESSAGING,
    "CRM": DocCategory.CRM,
    "SSO": DocCategory.SSO,
    "ATS": DocCategory.ATS,
    "PEOPLE": DocCategory.PEOPLE,
    "EXTERNAL_SHORTCUT": DocCategory.EXTERNAL_SHORTCUT,
    "UNCATEGORIZED": DocCategory.UNCATEGORIZED,
}

DATASOURCE_CATEGORY_MAP = {
    "KNOWLEDGE_HUB": GleanDatasourceCategory.KNOWLEDGE_HUB,
    "PUBLISHED_CONTENT": GleanDatasourceCategory.PUBLISHED_CONTENT,
    "COLLABORATIVE_CONTENT": GleanDatasourceCategory.COLLABORATIVE_CONTENT,
    "QUESTION_ANSWER": GleanDatasourceCategory.QUESTION_ANSWER,
    "TICKETS": GleanDatasourceCategory.TICKETS,
    "CODE_REPOSITORY": GleanDatasourceCategory.CODE_REPOSITORY,
    "CHANGE_MANAGEMENT": GleanDatasourceCategory.CHANGE_MANAGEMENT,
    "EMAIL": GleanDatasourceCategory.EMAIL,
    "MESSAGING": GleanDatasourceCategory.MESSAGING,
    "CRM": GleanDatasourceCategory.CRM,
    "SSO": GleanDatasourceCategory.SSO,
    "ATS": GleanDatasourceCategory.ATS,
    "PEOPLE": GleanDatasourceCategory.PEOPLE,
    "EXTERNAL_SHORTCUT": GleanDatasourceCategory.EXTERNAL_SHORTCUT,
    "UNCATEGORIZED": GleanDatasourceCategory.UNCATEGORIZED,
}


class DatasourceSettings(BaseSettings):
    """Settings for Glean datasource configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # API Authentication (no prefix for these)
    glean_indexing_api_key: str = Field(..., description="API key for Glean Indexing API")
    glean_instance_name: str = Field(..., description="Glean instance name")

    # Datasource configuration (with GLEAN_DATASOURCE_ prefix)
    glean_datasource_display_name: str = Field(..., max_length=50, description="Display name for the datasource")
    glean_datasource_id: str = Field(..., pattern="^[a-z0-9-]+$", description="Unique ID for the datasource")
    glean_datasource_category: DatasourceCategory = Field(DatasourceCategory.KNOWLEDGE_HUB, description="Category of the datasource")
    glean_datasource_home_url: str = Field(..., pattern="^https?://", description="Home URL of the datasource")
    glean_datasource_url_regex: Optional[str] = Field(None, description="URL regex pattern for documents")

    # Icon configuration
    glean_datasource_icon_filename_lightmode: Optional[str] = Field(None, description="Path to light mode icon file")
    glean_datasource_icon_url_lightmode: Optional[str] = Field(None, description="URL for light mode icon")
    glean_datasource_icon_filename_darkmode: Optional[str] = Field(None, description="Path to dark mode icon file")
    glean_datasource_icon_url_darkmode: Optional[str] = Field(None, description="URL for dark mode icon")

    # Identity configuration
    glean_datasource_user_referenced_by_email: bool = Field(True, description="Whether users are referenced by email (True) or ID (False)")

    # Test mode configuration
    glean_datasource_is_test_mode: bool = Field(True, description="Whether to start in test mode")
    glean_datasource_test_user_emails: str = Field("", description="Comma-separated list of test user emails")

    # Suggestion text
    glean_datasource_suggestion_text: Optional[str] = Field(None, description="Example text for what to search for in this datasource")

    @field_validator("glean_datasource_display_name")
    def validate_display_name(cls, v):
        """Validate display name has no trailing whitespace or symbols."""
        if v != v.strip():
            raise ValueError("Display name cannot have leading or trailing whitespace")
        if v and v[-1] in ["/", ";", ":", ","]:
            raise ValueError("Display name cannot end with symbols like /, ;, :, ,")
        return v

    @property
    def url_regex(self) -> str:
        """Get URL regex, defaulting to home URL pattern if not specified."""
        if self.glean_datasource_url_regex:
            return self.glean_datasource_url_regex
        return f"{self.glean_datasource_home_url.rstrip('/')}/.*"

    @property
    def test_user_emails_list(self) -> list[str]:
        """Parse comma-separated test user emails into a list."""
        if not self.glean_datasource_test_user_emails:
            return []

        emails = [email.strip() for email in self.glean_datasource_test_user_emails.split(",") if email.strip()]

        # Validate emails
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        valid_emails = []
        for email in emails:
            if re.match(email_pattern, email):
                valid_emails.append(email)
            else:
                log_warning(f"Invalid email format: {email} (skipped)")

        return valid_emails

    @property
    def icon_url(self) -> str:
        """Get the light mode icon URL, handling file paths and URLs."""
        # Check for file path from env var first
        if self.glean_datasource_icon_filename_lightmode:
            path = Path(self.glean_datasource_icon_filename_lightmode)
            if path.exists():
                return get_icon_as_data_url(path)
            else:
                raise ValueError(f"Icon file not found: {self.glean_datasource_icon_filename_lightmode}")

        # Check for URL from env var
        if self.glean_datasource_icon_url_lightmode:
            return download_icon(self.glean_datasource_icon_url_lightmode)

        # Check for default local file
        default_path = Path("icon-lightmode.png")
        if default_path.exists():
            return get_icon_as_data_url(default_path)

        # No icon found - raise error with helpful message
        raise ValueError("No light mode icon found. Please provide one of the following:\n" "1. Place an 'icon-lightmode.png' file in the current directory\n" "2. Set GLEAN_DATASOURCE_ICON_FILENAME_LIGHTMODE to point to your icon file\n" "3. Set GLEAN_DATASOURCE_ICON_URL_LIGHTMODE to an icon URL")

    @property
    def icon_dark_url(self) -> str:
        """Get the dark mode icon URL, handling file paths and URLs."""
        # Check for file path from env var first
        if self.glean_datasource_icon_filename_darkmode:
            path = Path(self.glean_datasource_icon_filename_darkmode)
            if path.exists():
                return get_icon_as_data_url(path)
            else:
                raise ValueError(f"Icon file not found: {self.glean_datasource_icon_filename_darkmode}")

        # Check for URL from env var
        if self.glean_datasource_icon_url_darkmode:
            return download_icon(self.glean_datasource_icon_url_darkmode)

        # Check for default local file
        default_path = Path("icon-darkmode.png")
        if default_path.exists():
            return get_icon_as_data_url(default_path)

        # Fall back to light mode icon
        try:
            return self.icon_url
        except ValueError:
            # If light mode icon also fails, re-raise with dark mode context
            raise ValueError(
                "No dark mode icon found. Please provide one of the following:\n"
                "1. Place an 'icon-darkmode.png' file in the current directory\n"
                "2. Set GLEAN_DATASOURCE_ICON_FILENAME_DARKMODE to point to your icon file\n"
                "3. Set GLEAN_DATASOURCE_ICON_URL_DARKMODE to an icon URL\n"
                "Note: Dark mode icon falls back to light mode icon if not specified."
            )

    @property
    def object_definitions(self) -> list[dict]:
        """Load object definitions from JSON file."""
        return load_object_definitions()

    @property
    def quick_links(self) -> list[dict]:
        """Load quick links from JSON file."""
        return load_quick_links()

    @property
    def suggestion_text(self) -> str:
        """Get suggestion text, defaulting to display name based text."""
        if self.glean_datasource_suggestion_text:
            return self.glean_datasource_suggestion_text
        return f"Search for anything in {self.glean_datasource_display_name}..."


@lru_cache
def get_settings(**kwargs) -> DatasourceSettings:
    """Get cached settings instance."""
    return DatasourceSettings(**kwargs)


def display_configuration_summary(settings: DatasourceSettings) -> None:
    """Display a detailed configuration summary."""
    # Main configuration table
    config_table = Table(title="Configuration Summary")
    config_table.add_column("Setting", style="cyan", no_wrap=True)
    config_table.add_column("Value", style="yellow")

    # Basic settings
    config_table.add_row("Display Name", settings.glean_datasource_display_name)
    config_table.add_row("Datasource ID", settings.glean_datasource_id)
    config_table.add_row("Category", settings.glean_datasource_category.value)
    config_table.add_row("Home URL", settings.glean_datasource_home_url)
    config_table.add_row("URL Regex", settings.url_regex)
    config_table.add_row("Suggestion Text", settings.suggestion_text)

    # Highlighted settings
    user_ref_text = "[bold green]✓ By Email[/bold green]" if settings.glean_datasource_user_referenced_by_email else "[bold yellow]⚡ By ID (not email)[/bold yellow]"
    config_table.add_row("User Reference Type", user_ref_text)

    test_mode_text = "[bold yellow]Yes - Test Mode[/bold yellow]" if settings.glean_datasource_is_test_mode else "[green]No - Live Mode[/green]"
    config_table.add_row("Test Mode", test_mode_text)

    # Icon configuration
    try:
        # Try to determine icon source
        if settings.glean_datasource_icon_filename_lightmode:
            light_icon_text = f"File: {settings.glean_datasource_icon_filename_lightmode}"
        elif settings.glean_datasource_icon_url_lightmode:
            light_icon_text = f"URL: {settings.glean_datasource_icon_url_lightmode}"
        elif Path("icon-lightmode.png").exists():
            light_icon_text = "icon-lightmode.png (default)"
        else:
            light_icon_text = "[red]Not configured[/red]"
    except:
        light_icon_text = "[red]Not configured[/red]"
    config_table.add_row("Light Mode Icon", light_icon_text)

    try:
        # Try to determine dark icon source
        if settings.glean_datasource_icon_filename_darkmode:
            dark_icon_text = f"File: {settings.glean_datasource_icon_filename_darkmode}"
        elif settings.glean_datasource_icon_url_darkmode:
            dark_icon_text = f"URL: {settings.glean_datasource_icon_url_darkmode}"
        elif Path("icon-darkmode.png").exists():
            dark_icon_text = "icon-darkmode.png (default)"
        else:
            dark_icon_text = "[dim]<using light mode icon>[/dim]"
    except:
        dark_icon_text = "[dim]<using light mode icon>[/dim]"
    config_table.add_row("Dark Mode Icon", dark_icon_text)

    console.print(config_table)

    # Test users if applicable
    if settings.glean_datasource_is_test_mode and settings.test_user_emails_list:
        console.print("\n[bold]Test Users:[/bold]")
        for email in settings.test_user_emails_list:
            console.print(f"  • {email}")

    # Object definitions
    if settings.object_definitions:
        console.print()
        obj_table = Table(title="Object Definitions")
        obj_table.add_column("Name", style="cyan")
        obj_table.add_column("Display Name", style="yellow")
        obj_table.add_column("Properties", style="blue")
        obj_table.add_column("Groups", style="magenta")
        obj_table.add_column("Summarizable", style="green")

        for obj in settings.object_definitions:
            prop_count = len(obj.get("property_definitions", [])) if "property_definitions" in obj else 0
            group_count = len(obj.get("property_groups", [])) if "property_groups" in obj else 0
            obj_table.add_row(obj.get("name", ""), obj.get("display_label", obj.get("name", "")), str(prop_count) if prop_count > 0 else "-", str(group_count) if group_count > 0 else "-", "Yes" if obj.get("summarizable", True) else "No")

        console.print(obj_table)

    # Quick links
    if settings.quick_links:
        console.print(f"\n[bold]Quick Links:[/bold] {len(settings.quick_links)} defined")


def generate_sample_object_types() -> dict:
    """Generate sample object types JSON."""
    return {
        "objectTypes": [
            {
                "name": "article",
                "display_label": "News/Articles",
                "doc_category": "PUBLISHED_CONTENT",
                "summarizable": True,
                "property_definitions": [
                    {"name": "author", "display_label": "Author", "property_type": "USERID"},
                    {"name": "publishDate", "display_label": "Publish Date", "property_type": "DATE"},
                    {"name": "category", "display_label": "Category", "property_type": "PICKLIST", "ui_options": "SEARCH_RESULT"},
                    {"name": "tags", "display_label": "Tags", "display_label_plural": "Tags", "property_type": "TEXTLIST"},
                ],
                "property_groups": [{"name": "metadata", "display_label": "Article Metadata"}],
            },
            {"name": "site", "display_label": "Site", "doc_category": "KNOWLEDGE_HUB", "summarizable": False},
            {"name": "page", "display_label": "Page", "doc_category": "KNOWLEDGE_HUB", "summarizable": False},
            {"name": "event", "display_label": "Event", "doc_category": "PUBLISHED_CONTENT", "summarizable": True},
            {"name": "announcement", "display_label": "Announcement", "doc_category": "PUBLISHED_CONTENT", "summarizable": False},
            {"name": "question", "display_label": "FAQ", "doc_category": "QUESTION_ANSWER", "summarizable": True},
            {"name": "ticket", "display_label": "Ticket", "doc_category": "TICKETS", "summarizable": True},
            {"name": "document", "display_label": "Files", "doc_category": "COLLABORATIVE_CONTENT", "summarizable": True},
            {"name": "folder", "display_label": "Repository", "doc_category": "COLLABORATIVE_CONTENT", "summarizable": False},
        ]
    }


def interactive_setup() -> DatasourceSettings:
    """Run interactive setup flow."""
    console.print("\n[bold cyan]Glean Datasource Setup - Interactive Mode[/bold cyan]\n")

    # Collect all settings interactively
    settings_dict = {}

    # Display name
    while True:
        display_name = Prompt.ask("\n[bold]What is the name of the datasource?[/bold] This will be shown to users in the UI\n" 'E.g. "Intranet", "Backstage Catalog", etc')
        try:
            # Validate display name using settings validator
            test_settings = DatasourceSettings(glean_indexing_api_key="temp", glean_instance_name="temp", glean_datasource_display_name=display_name, glean_datasource_id="temp", glean_datasource_home_url="https://temp.com")
            settings_dict["glean_datasource_display_name"] = display_name
            break
        except ValidationError as e:
            for error in e.errors():
                if "glean_datasource_display_name" in str(error["loc"]):
                    log_error(error["msg"])

    # Datasource ID
    suggested_id = normalize_datasource_id(display_name)
    console.print(f"\n[bold]Based on the name, the following ID will be used to reference the datasource in the index:[/bold]")
    console.print(f"[yellow]{suggested_id}[/yellow]")

    if Confirm.ask("Is this OK?", default=True):
        settings_dict["glean_datasource_id"] = suggested_id
    else:
        while True:
            datasource_id = Prompt.ask("\nEnter a custom datasource ID (lowercase letters, numbers, and hyphens only)")
            if re.match(r"^[a-z0-9-]+$", datasource_id):
                settings_dict["glean_datasource_id"] = datasource_id
                break
            log_error("Invalid format. Use only lowercase letters, numbers, and hyphens.")

    # Category selection
    console.print("\n[bold]What category best describes the datasource?[/bold]\n")

    # Show categories excluding the ones that shouldn't be used
    valid_categories = [cat for cat in DatasourceCategory if cat not in [DatasourceCategory.PEOPLE, DatasourceCategory.EXTERNAL_SHORTCUT, DatasourceCategory.UNCATEGORIZED]]

    for i, cat in enumerate(valid_categories, 1):
        console.print(f"{i}. [cyan]{cat.value}[/cyan]")
        console.print(f"   [dim]{CATEGORY_DESCRIPTIONS[cat]}[/dim]\n")

    while True:
        choice = IntPrompt.ask("Select a category (enter number)", default=1)
        if 1 <= choice <= len(valid_categories):
            settings_dict["glean_datasource_category"] = valid_categories[choice - 1]
            break
        log_error(f"Please enter a number between 1 and {len(valid_categories)}")

    # Icons
    console.print("\n[bold]Configure datasource icons[/bold]")
    console.print("Default: icon-lightmode.png and icon-darkmode.png in current directory")
    console.print("You can also provide URLs or specify different filenames via environment variables")

    # Check for local files - both default names and legacy names
    default_light = Path("icon-lightmode.png")
    default_dark = Path("icon-darkmode.png")
    legacy_light_files = list(Path.cwd().glob("icon_lightmode.*"))
    legacy_dark_files = list(Path.cwd().glob("icon_darkmode.*"))

    # Light mode icon
    icon_configured = False

    # Check for default file first
    if default_light.exists():
        if Confirm.ask(f"\nFound default icon file: {default_light.name}. Use this?", default=True):
            log_success(f"Using default file: {default_light.name}")
            icon_configured = True
    # Check for legacy named files
    elif legacy_light_files:
        if Confirm.ask(f"\nFound icon file: {legacy_light_files[0].name}. Use this?", default=True):
            settings_dict["glean_datasource_icon_filename_lightmode"] = str(legacy_light_files[0])
            log_success(f"Using file: {legacy_light_files[0].name}")
            icon_configured = True

    if not icon_configured:
        console.print("\n[yellow]No light mode icon file found.[/yellow]")
        icon_input = Prompt.ask("Enter light mode icon URL (or press Enter to skip)", default="")
        if icon_input:
            if icon_input.startswith("http"):
                settings_dict["glean_datasource_icon_url_lightmode"] = icon_input
                icon_configured = True
            else:
                log_error("Invalid URL format. Must start with http:// or https://")

        if not icon_configured:
            log_warning("No icon configured. You'll need to provide one of:\n" "  - Place 'icon-lightmode.png' in current directory\n" "  - Set GLEAN_DATASOURCE_ICON_FILENAME_LIGHTMODE env var\n" "  - Set GLEAN_DATASOURCE_ICON_URL_LIGHTMODE env var")

    # Dark mode icon
    dark_configured = False

    # Check for default file first
    if default_dark.exists():
        if Confirm.ask(f"\nFound default dark icon file: {default_dark.name}. Use this?", default=True):
            log_success(f"Using default file: {default_dark.name}")
            dark_configured = True
    # Check for legacy named files
    elif legacy_dark_files:
        if Confirm.ask(f"\nFound dark icon file: {legacy_dark_files[0].name}. Use this?", default=True):
            settings_dict["glean_datasource_icon_filename_darkmode"] = str(legacy_dark_files[0])
            log_success(f"Using file: {legacy_dark_files[0].name}")
            dark_configured = True

    if not dark_configured:
        dark_icon_input = Prompt.ask("\nDark mode icon URL (or press Enter to use light mode icon)", default="")
        if dark_icon_input:
            if dark_icon_input.startswith("http"):
                settings_dict["glean_datasource_icon_url_darkmode"] = dark_icon_input
            else:
                log_error("Invalid URL. Dark mode will use light mode icon.")

    # Home URL
    while True:
        home_url = Prompt.ask("\n[bold]What is the URL of the home/landing page of the app?[/bold]\n" "This is the URL of the app the user is taken to after they log in\n" "E.g. https://myapp.com/dashboard")
        if re.match(r"^https?://", home_url):
            settings_dict["glean_datasource_home_url"] = home_url
            break
        log_error("URL must start with http:// or https://")

    # URL regex
    console.print("\n[bold]Are documents and assets in this datasource accessed at the same domain?[/bold]")
    console.print(f"E.g. {home_url}/content/myfolder/document1")

    if Confirm.ask("Use the same domain?", default=True):
        # Extract base URL
        from urllib.parse import urlparse

        parsed = urlparse(home_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        settings_dict["glean_datasource_url_regex"] = f"{base_url}/.*"
    else:
        base_url = Prompt.ask("\nEnter the base URL for documents")
        if not base_url.endswith("/*"):
            settings_dict["glean_datasource_url_regex"] = f"{base_url}/.*"
        else:
            settings_dict["glean_datasource_url_regex"] = base_url

    # User identity
    console.print("\n[bold]Are user identities referenced by email or a different ID in this data source?[/bold]")
    console.print("Examples:")
    console.print('  "created_by": "sam.sample@company.com" → [green]Email[/green]')
    console.print('  "created_by": "sam.sample" → [yellow]ID[/yellow]')
    console.print('  "created_by": "U1234567" → [yellow]ID[/yellow]')

    settings_dict["glean_datasource_user_referenced_by_email"] = Confirm.ask("\nAre users referenced by email?", default=True)

    # Test mode
    console.print("\n[bold]Should this datasource be made live straight away, or would you like it only visible to test users to begin with?[/bold]")
    settings_dict["glean_datasource_is_test_mode"] = Confirm.ask("Start in test mode (recommended)?", default=True)

    # Test users
    if settings_dict["glean_datasource_is_test_mode"]:
        console.print("\n[bold]Add test user emails[/bold] (comma-separated, or press Enter to skip)")
        emails_input = Prompt.ask("Test user emails", default="")
        if emails_input:
            settings_dict["glean_datasource_test_user_emails"] = emails_input

    # Load object definitions
    object_definitions = load_object_definitions()
    if object_definitions:
        log_success(f"Loaded {len(object_definitions)} object definitions from object_types.json")
    else:
        log_info("No object_types.json found. Datasource will be created without object definitions.")

    # Get API credentials from environment or prompt
    api_token = os.getenv("GLEAN_INDEXING_API_KEY")
    instance_name = os.getenv("GLEAN_INSTANCE_NAME")

    if not api_token:
        console.print("\n[bold yellow]GLEAN_INDEXING_API_KEY not found in environment[/bold yellow]")
        api_token = Prompt.ask("Enter your Glean Indexing API token", password=True)
        settings_dict["glean_indexing_api_key"] = api_token
    else:
        settings_dict["glean_indexing_api_key"] = api_token

    if not instance_name:
        console.print("\n[bold yellow]GLEAN_INSTANCE_NAME not found in environment[/bold yellow]")
        instance_name = Prompt.ask("Enter your Glean instance name (e.g., mycompany)")
        settings_dict["glean_instance_name"] = instance_name
    else:
        settings_dict["glean_instance_name"] = instance_name

    return get_settings(**settings_dict)


def create_datasource(settings: DatasourceSettings, force: bool = False) -> bool:
    """Create or update the datasource in Glean."""
    try:
        with Glean(api_token=settings.glean_indexing_api_key, instance=settings.glean_instance_name) as glean:
            # Check if datasource exists
            try:
                existing = glean.indexing.datasources.retrieve_config(datasource=settings.glean_datasource_id)
                if existing:
                    console.print()  # Add line break
                    console.print(f"[bold red]⚠ Datasource '{settings.glean_datasource_id}' already exists[/bold red]")
                    if not force:
                        if not Confirm.ask("Do you want to overwrite the existing configuration?", default=False):
                            log_info("Aborted")
                            return False
            except Exception:
                # Datasource doesn't exist, which is fine
                pass

            # Prepare object definitions
            object_defs = []
            for obj in settings.object_definitions:
                # Map doc_category string to enum
                doc_category_str = obj.get("doc_category", "KNOWLEDGE_HUB")
                doc_category = DOCUMENT_CATEGORY_MAP.get(doc_category_str, DocCategory.KNOWLEDGE_HUB)

                object_defs.append(models.ObjectDefinition(name=obj["name"], display_label=obj.get("display_label", obj["name"]), doc_category=doc_category, property_definitions=obj.get("property_definitions", None), property_groups=obj.get("property_groups", None), summarizable=obj.get("summarizable", False)))

            # Prepare quick links
            quicklinks = []
            for ql in settings.quick_links:
                quicklink_dict = {
                    "name": ql.get("name"),
                    "short_name": ql.get("short_name"),
                    "url": ql.get("url"),
                    "id": ql.get("id"),
                }

                # Handle icon_config if present
                if "icon_config" in ql and ql["icon_config"]:
                    icon_config = {}
                    for key in ["generated_background_color_key", "background_color", "color", "key", "icon_type", "masked", "name", "url"]:
                        if key in ql["icon_config"]:
                            icon_config[key] = ql["icon_config"][key]
                    if icon_config:
                        quicklink_dict["icon_config"] = models.IconConfig(**icon_config)

                # Handle scopes if present
                if "scopes" in ql and ql["scopes"]:
                    quicklink_dict["scopes"] = ql["scopes"]

                quicklinks.append(models.Quicklink(**quicklink_dict))

            # Map category to Glean enum
            glean_category = DATASOURCE_CATEGORY_MAP.get(settings.glean_datasource_category.value, GleanDatasourceCategory.KNOWLEDGE_HUB)

            # Create datasource
            console.print("\n[bold]Creating datasource...[/bold]")

            result = glean.indexing.datasources.add(
                name=settings.glean_datasource_id,
                display_name=settings.glean_datasource_display_name,
                datasource_category=glean_category,
                url_regex=settings.url_regex,
                icon_url=settings.icon_url,
                icon_dark_url=settings.icon_dark_url,
                home_url=settings.glean_datasource_home_url,
                suggestion_text=settings.suggestion_text,
                object_definitions=object_defs if object_defs else None,
                quicklinks=quicklinks if quicklinks else None,
                is_user_referenced_by_email=settings.glean_datasource_user_referenced_by_email,
                is_test_datasource=settings.glean_datasource_is_test_mode,
                trust_url_regex_for_view_activity=True,
                strip_fragment_in_canonical_url=True,
                is_entity_datasource=False,
            )

            log_success(f"Successfully created/updated datasource '{settings.glean_datasource_id}'")

            # Show Glean UI URL
            console.print(f"\n🔗 You can view the connector configuration in the Glean UI at:")
            console.print(f"[cyan]https://app.glean.com/admin/setup/apps/custom/{settings.glean_datasource_id}[/cyan]")

            # Add test users if specified
            test_emails = settings.test_user_emails_list
            if settings.glean_datasource_is_test_mode and test_emails:
                console.print(f"\n[dim]Note: Test users ({len(test_emails)}) can be managed in the Glean admin interface[/dim]")

            return True

    except Exception as e:
        log_error(f"Failed to create datasource: {e}")
        return False


def fetch_datasource_config(datasource_id: Optional[str] = None, save: bool = False) -> None:
    """Fetch and display datasource configuration."""
    try:
        settings = get_settings()
    except ValidationError as e:
        log_error("Missing required environment variables. Use --help for more information.")
        return

    try:
        with Glean(api_token=settings.glean_indexing_api_key, instance=settings.glean_instance_name) as glean:
            if datasource_id:
                # Show specific datasource
                try:
                    config = glean.indexing.datasources.retrieve_config(datasource=datasource_id)

                    table = Table(title=f"Datasource Configuration: {datasource_id}")
                    table.add_column("Property", style="cyan")
                    table.add_column("Value", style="yellow")

                    # Add configuration details
                    table.add_row("Display Name", config.display_name or "N/A")
                    table.add_row("Datasource ID", datasource_id)
                    table.add_row("Category", config.datasource_category.value if config.datasource_category else "N/A")
                    table.add_row("Home URL", config.home_url or "N/A")
                    table.add_row("URL Regex", config.url_regex or "N/A")
                    table.add_row("Suggestion Text", config.suggestion_text or "N/A")
                    table.add_row("Icon URL (Light)", config.icon_url[:40] + "..." if config.icon_url else "N/A")
                    table.add_row("Icon URL (Dark)", config.icon_dark_url[:40] + "..." if config.icon_dark_url else "N/A")
                    table.add_row("Test Mode", "Yes" if config.is_test_datasource else "No")
                    table.add_row("User Reference", "Email" if config.is_user_referenced_by_email else "ID")
                    table.add_row("Object Types", str(len(config.object_definitions)) if config.object_definitions else "0")
                    table.add_row("Quick Links", str(len(config.quicklinks)) if hasattr(config, "quicklinks") and config.quicklinks else "0")

                    # Additional fields if available
                    if hasattr(config, "crawler_seed_urls") and config.crawler_seed_urls:
                        table.add_row("Crawler Seed URLs", ", ".join(config.crawler_seed_urls))

                    console.print(table)

                    # Show object definitions if any
                    if config.object_definitions:
                        obj_table = Table(title="Object Definitions")
                        obj_table.add_column("Name", style="cyan")
                        obj_table.add_column("Display Label", style="yellow")
                        obj_table.add_column("Category", style="green")
                        obj_table.add_column("Properties", style="blue")
                        obj_table.add_column("Groups", style="magenta")
                        obj_table.add_column("Summarizable", style="blue")

                        for obj in config.object_definitions:
                            prop_count = len(obj.property_definitions) if hasattr(obj, "property_definitions") and obj.property_definitions else 0
                            group_count = len(obj.property_groups) if hasattr(obj, "property_groups") and obj.property_groups else 0
                            obj_table.add_row(obj.name, obj.display_label or obj.name, obj.doc_category.value if obj.doc_category else "N/A", str(prop_count) if prop_count > 0 else "-", str(group_count) if group_count > 0 else "-", "Yes" if obj.summarizable else "No")

                        console.print("\n")
                        console.print(obj_table)

                    # Show tip if not saving
                    if not save:
                        console.print("\n[yellow]💡 Tip:[/yellow] You can export this configuration by using the --save flag:")
                        console.print(f"[dim]   uv run manage.py config {datasource_id} --save[/dim]\n")

                    # Save configuration if requested
                    if save:
                        # Create directory
                        config_dir = Path(f"{datasource_id}-config")
                        config_dir.mkdir(exist_ok=True)

                        # Save icons
                        icon_light_filename = None
                        icon_dark_filename = None

                        if config.icon_url:
                            try:
                                ext = save_data_url_to_file(config.icon_url, config_dir / "icon-lightmode")
                                icon_light_filename = f"icon-lightmode.{ext}"
                                log_success(f"Saved light mode icon: {icon_light_filename}")
                            except Exception as e:
                                log_warning(f"Could not save light mode icon: {e}")

                        if config.icon_dark_url:
                            try:
                                ext = save_data_url_to_file(config.icon_dark_url, config_dir / "icon-darkmode")
                                icon_dark_filename = f"icon-darkmode.{ext}"
                                log_success(f"Saved dark mode icon: {icon_dark_filename}")
                            except Exception as e:
                                log_warning(f"Could not save dark mode icon: {e}")

                        # Save object definitions
                        if config.object_definitions:
                            object_types_list = []
                            for obj in config.object_definitions:
                                obj_dict = {"name": obj.name, "display_label": obj.display_label or obj.name, "doc_category": obj.doc_category.value if obj.doc_category else "KNOWLEDGE_HUB", "summarizable": obj.summarizable if hasattr(obj, "summarizable") else True}

                                # Only include property_definitions if they exist and are not empty
                                if hasattr(obj, "property_definitions") and obj.property_definitions:
                                    prop_defs = []
                                    for prop in obj.property_definitions:
                                        prop_dict = {"name": prop.name}
                                        if prop.display_label:
                                            prop_dict["display_label"] = prop.display_label
                                        if hasattr(prop, "display_label_plural") and prop.display_label_plural:
                                            prop_dict["display_label_plural"] = prop.display_label_plural
                                        if hasattr(prop, "property_type") and prop.property_type:
                                            prop_dict["property_type"] = prop.property_type.value if hasattr(prop.property_type, "value") else str(prop.property_type)
                                        if hasattr(prop, "ui_options") and prop.ui_options:
                                            prop_dict["ui_options"] = prop.ui_options.value if hasattr(prop.ui_options, "value") else str(prop.ui_options)
                                        if hasattr(prop, "hide_ui_facet") and prop.hide_ui_facet:
                                            prop_dict["hide_ui_facet"] = prop.hide_ui_facet
                                        if hasattr(prop, "ui_facet_order") and prop.ui_facet_order is not None:
                                            prop_dict["ui_facet_order"] = prop.ui_facet_order
                                        if hasattr(prop, "skip_indexing") and prop.skip_indexing:
                                            prop_dict["skip_indexing"] = prop.skip_indexing
                                        if hasattr(prop, "group") and prop.group:
                                            prop_dict["group"] = prop.group
                                        prop_defs.append(prop_dict)
                                    obj_dict["property_definitions"] = prop_defs

                                # Only include property_groups if they exist and are not empty
                                if hasattr(obj, "property_groups") and obj.property_groups:
                                    groups = []
                                    for group in obj.property_groups:
                                        group_dict = {"name": group.name}
                                        if group.display_label:
                                            group_dict["display_label"] = group.display_label
                                        groups.append(group_dict)
                                    obj_dict["property_groups"] = groups

                                object_types_list.append(obj_dict)

                            object_types = {"objectTypes": object_types_list}

                            with open(config_dir / "object_types.json", "w") as f:
                                json.dump(object_types, f, indent=2)

                            log_success(f"Saved {len(config.object_definitions)} object definitions to object_types.json")

                        # Save quick links
                        if hasattr(config, "quicklinks") and config.quicklinks:
                            quicklinks_list = []
                            for ql in config.quicklinks:
                                ql_dict = {}
                                if hasattr(ql, "name") and ql.name:
                                    ql_dict["name"] = ql.name
                                if hasattr(ql, "short_name") and ql.short_name:
                                    ql_dict["short_name"] = ql.short_name
                                if hasattr(ql, "url") and ql.url:
                                    ql_dict["url"] = ql.url
                                if hasattr(ql, "id") and ql.id:
                                    ql_dict["id"] = ql.id

                                # Handle icon_config
                                if hasattr(ql, "icon_config") and ql.icon_config:
                                    icon_config = {}
                                    for attr in ["generated_background_color_key", "background_color", "color", "key", "icon_type", "masked", "name", "url"]:
                                        if hasattr(ql.icon_config, attr):
                                            value = getattr(ql.icon_config, attr)
                                            if value is not None:
                                                # Handle enum values
                                                if attr == "icon_type" and hasattr(value, "value"):
                                                    icon_config[attr] = value.value
                                                else:
                                                    icon_config[attr] = value
                                    if icon_config:
                                        ql_dict["icon_config"] = icon_config

                                # Handle scopes
                                if hasattr(ql, "scopes") and ql.scopes:
                                    scopes = []
                                    for scope in ql.scopes:
                                        if hasattr(scope, "value"):
                                            scopes.append(scope.value)
                                        else:
                                            scopes.append(str(scope))
                                    if scopes:
                                        ql_dict["scopes"] = scopes

                                if ql_dict:  # Only add if we have data
                                    quicklinks_list.append(ql_dict)

                            if quicklinks_list:
                                quicklinks_data = {"quicklinks": quicklinks_list}
                                with open(config_dir / "quick_links.json", "w") as f:
                                    json.dump(quicklinks_data, f, indent=2)

                                log_success(f"Saved {len(quicklinks_list)} quick links to quick_links.json")

                        # Save .env file
                        env_content = f"""# Glean API Authentication
GLEAN_INSTANCE_NAME={settings.glean_instance_name}
GLEAN_INDEXING_API_KEY=  # redacted

# Datasource Configuration
GLEAN_DATASOURCE_DISPLAY_NAME={config.display_name or ''}
GLEAN_DATASOURCE_ID={datasource_id}
GLEAN_DATASOURCE_CATEGORY={config.datasource_category.value if config.datasource_category else 'KNOWLEDGE_HUB'}
GLEAN_DATASOURCE_HOME_URL={config.home_url or ''}
GLEAN_DATASOURCE_URL_REGEX={config.url_regex or ''}

# Icon Configuration
GLEAN_DATASOURCE_ICON_FILENAME_LIGHTMODE={icon_light_filename or 'icon-lightmode.png'}
GLEAN_DATASOURCE_ICON_FILENAME_DARKMODE={icon_dark_filename or 'icon-darkmode.png'}

# Identity Configuration
GLEAN_DATASOURCE_USER_REFERENCED_BY_EMAIL={'true' if config.is_user_referenced_by_email else 'false'}

# Test Mode Configuration
GLEAN_DATASOURCE_IS_TEST_MODE={'true' if config.is_test_datasource else 'false'}
# GLEAN_DATASOURCE_TEST_USER_EMAILS=

# Optional Settings
GLEAN_DATASOURCE_SUGGESTION_TEXT={config.suggestion_text or ''}
"""

                        env_path = config_dir / f"{datasource_id}.env"
                        with open(env_path, "w") as f:
                            f.write(env_content)

                        log_success(f"Configuration saved to {config_dir}/")
                        console.print(f"\n[green]✓[/green] Created configuration directory: [cyan]{config_dir}[/cyan]")
                        console.print(f"  - {datasource_id}.env (environment configuration)")
                        if config.object_definitions:
                            console.print("  - object_types.json (object definitions)")
                        if hasattr(config, "quicklinks") and config.quicklinks:
                            console.print("  - quick_links.json (quick links)")
                        if icon_light_filename:
                            console.print(f"  - {icon_light_filename} (light mode icon)")
                        if icon_dark_filename:
                            console.print(f"  - {icon_dark_filename} (dark mode icon)")
                        console.print(f"\n[yellow]💡 Tip:[/yellow] You can now run the setup script from the {config_dir}/ directory to recreate this datasource.\n")

                except Exception as e:
                    log_error(f"Failed to retrieve datasource '{datasource_id}': {e}")
            else:
                # List all datasources
                log_info("Listing all datasources requires admin access. Showing help instead.")
                console.print("\nTo fetch a specific datasource configuration, use:")
                console.print("[yellow]uv run manage.py config <datasource_id>[/yellow]")
                console.print("[yellow]uv run manage.py config <datasource_id> --save[/yellow]")

    except Exception as e:
        log_error(f"Failed to connect to Glean API: {e}")


def run_interactive_setup(silent: bool, force: bool):
    """Run the interactive datasource setup flow."""
    display_banner("New Datasource Setup", "Create and configure a custom datasource in Glean")

    if silent:
        console.print("\n[bold yellow]Running in silent mode[/bold yellow]")
        try:
            settings = get_settings()
            log_success("Loaded configuration from environment variables")

            # Display configuration
            console.print()
            display_configuration_summary(settings)

            # In silent mode, check if datasource exists and require --force to overwrite
            datasource_exists = False
            try:
                with Glean(api_token=settings.glean_indexing_api_key, instance=settings.glean_instance_name) as glean:
                    existing = glean.indexing.datasources.retrieve_config(datasource=settings.glean_datasource_id)
                    if existing:
                        datasource_exists = True
            except Exception:
                # Datasource doesn't exist, which is fine
                pass

            if datasource_exists and not force:
                console.print()  # Add line break
                console.print(f"[bold red]❌ Datasource '{settings.glean_datasource_id}' already exists. Use --force to overwrite.[/bold red]")
                sys.exit(1)

            if create_datasource(settings, force=force):
                log_success("Datasource setup completed successfully!")
            else:
                log_error("Datasource setup failed")
                sys.exit(1)

        except ValidationError as e:
            log_error("Configuration error - missing required environment variables:")
            for error in e.errors():
                field = error["loc"][0] if error["loc"] else "unknown"
                log_error(f"  - {field}: {error['msg']}")
            console.print("\n[dim]Tip: Use 'generate-example-env' command to create a template .env file[/dim]")
            sys.exit(1)
        except Exception as e:
            log_error(f"Configuration error: {e}")
            console.print("\n[dim]Tip: Use 'generate-example-env' command to create a template .env file[/dim]")
            sys.exit(1)
    else:
        # Interactive mode (default)
        try:
            # First try to load from environment
            try:
                settings = get_settings()
                log_success("Loaded configuration from environment variables")
                console.print()
                display_configuration_summary(settings)
            except ValidationError:
                # Some env vars missing, run interactive setup
                log_info("Running interactive setup...")
                settings = interactive_setup()
                console.print()
                display_configuration_summary(settings)

            # Always ask for confirmation before creating
            if Confirm.ask("\n[bold]Proceed with creating the datasource?[/bold]", default=True):
                if create_datasource(settings):
                    log_success("Datasource setup completed successfully!")
                else:
                    log_error("Datasource setup failed")
                    sys.exit(1)
            else:
                log_info("Setup cancelled")

        except KeyboardInterrupt:
            console.print("\n[yellow]Setup cancelled by user[/yellow]")
            sys.exit(0)
        except Exception as e:
            log_error(f"Setup error: {e}")
            sys.exit(1)


@click.group()
@click.version_option(VERSION, "--version", "-v", message="%(version)s")
def cli():
    """Glean Custom Datasource Management Tool.

    Manage Glean custom datasources with commands for setup, configuration, and templates.
    """


@cli.command()
@click.option("--silent", is_flag=True, help="Run in silent mode without prompts (requires all env vars)")
@click.option("--force", is_flag=True, help="Force overwrite existing datasource (requires --silent)")
def setup(silent: bool, force: bool):
    """Setup a new Glean datasource.

    Run without options for interactive setup, or use --silent for automated setup using environment variables.
    """
    run_interactive_setup(silent, force)


@cli.command()
def generate_object_template():
    """Generate a sample object_types.json template."""
    display_banner("Object Types Template Generator", "Create a sample object_types.json file")
    sample = generate_sample_object_types()
    with open("object_types.json", "w") as f:
        json.dump(sample, f, indent=2)
    log_success("Generated object_types.json template")


@cli.command()
def generate_quicklinks_template():
    """Generate a sample quick_links.json template."""
    display_banner("Quick Links Template Generator", "Create a sample quick_links.json file")
    sample = {
        "quicklinks": [
            {"name": "Create New Issue", "short_name": "New Issue", "url": "https://backstage.example.com/catalog/create", "id": "create-issue", "icon_config": {"icon_type": "GLYPH", "name": "plus-circle", "color": "#343CED"}, "scopes": ["APP_CARD", "AUTOCOMPLETE_EXACT_MATCH"]},
            {"name": "View All Entities", "short_name": "All Entities", "url": "https://backstage.example.com/catalog", "id": "view-all", "icon_config": {"icon_type": "GLYPH", "name": "list", "color": "#28A745"}, "scopes": ["APP_CARD", "AUTOCOMPLETE_FUZZY_MATCH", "NEW_TAB_PAGE"]},
            {"name": "Search Documentation", "short_name": "Search Docs", "url": "https://backstage.example.com/docs/search", "id": "search-docs", "icon_config": {"icon_type": "GLYPH", "name": "search", "color": "#6C757D"}, "scopes": ["AUTOCOMPLETE_ZERO_QUERY", "AUTOCOMPLETE_FUZZY_MATCH"]},
        ]
    }

    with open("quick_links.json", "w") as f:
        json.dump(sample, f, indent=2)
    log_success("Generated quick_links.json template")


@cli.command()
def generate_example_env():
    """Generate an example .env.setup.example file."""
    display_banner("Environment Template Generator", "Create a sample .env configuration file")
    env_content = """# Glean API Authentication
GLEAN_INSTANCE_NAME=your-glean-instance-name  # e.g. mycompany-prod, if your Glean backend domain is https://mycompany-prod-be.glean.com
GLEAN_INDEXING_API_KEY=your-glean-indexing-api-token


# Datasource Configuration
GLEAN_DATASOURCE_DISPLAY_NAME=My Application
GLEAN_DATASOURCE_ID=my-application
GLEAN_DATASOURCE_CATEGORY=KNOWLEDGE_HUB
GLEAN_DATASOURCE_HOME_URL=https://myapp.com/dashboard
GLEAN_DATASOURCE_URL_REGEX=https://myapp.com/.*

# Icon Configuration
# Default: Place icon-lightmode.png and icon-darkmode.png in current directory
# Or use one of these options:
# GLEAN_DATASOURCE_ICON_FILENAME_LIGHTMODE=path/to/icon-light.png
# GLEAN_DATASOURCE_ICON_URL_LIGHTMODE=https://myapp.com/logo.png
# GLEAN_DATASOURCE_ICON_FILENAME_DARKMODE=path/to/icon-dark.png
# GLEAN_DATASOURCE_ICON_URL_DARKMODE=https://myapp.com/logo-dark.png

# Identity Configuration
GLEAN_DATASOURCE_USER_REFERENCED_BY_EMAIL=true

# Test Mode Configuration
GLEAN_DATASOURCE_IS_TEST_MODE=true
GLEAN_DATASOURCE_TEST_USER_EMAILS=user1@company.com,user2@company.com

# Optional Settings
GLEAN_DATASOURCE_SUGGESTION_TEXT=Search for engineering docs...
"""
    with open(".env.setup.example", "w") as f:
        f.write(env_content)
    log_success("Generated .env.setup.example file")


@cli.command()
@click.argument("datasource_id", required=False)
@click.option("--save", is_flag=True, help="Save configuration to files")
def config(datasource_id: Optional[str], save: bool):
    """Fetch datasource configuration from Glean.

    DATASOURCE_ID: The ID of the datasource to fetch (required)
    """
    display_banner("Configuration Export", "View and export datasource configurations from Glean")
    if not datasource_id:
        log_error("Please provide a datasource ID. Usage: config <datasource_id>")
        return
    fetch_datasource_config(datasource_id, save)


@cli.command()
def check_categories():
    """Show available datasource categories."""
    display_banner("Datasource Categories", "View available datasource categories")
    table = Table(title="Datasource Categories")
    table.add_column("Category", style="cyan", width=25)
    table.add_column("Description", style="yellow")

    for cat, desc in CATEGORY_DESCRIPTIONS.items():
        if cat not in [DatasourceCategory.PEOPLE, DatasourceCategory.EXTERNAL_SHORTCUT, DatasourceCategory.UNCATEGORIZED]:
            table.add_row(cat.value, desc)

    console.print(table)


if __name__ == "__main__":
    cli()
