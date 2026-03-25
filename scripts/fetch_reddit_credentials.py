#!/usr/bin/env python3
"""Helper script to auto-detect Reddit API credentials using Playwright.

Usage
-----
    pip install playwright
    playwright install chromium
    python scripts/fetch_reddit_credentials.py

The script opens a Chromium browser (visible by default so you can watch and
intervene), logs in to Reddit with your account credentials, navigates to the
app-preferences page, and prints the client_id / client_secret for any
"script"-type app it finds.  If none exists it will help you create one.

Options
-------
    --headless          Run without a visible browser window.
    --username TEXT     Reddit username  (overrides REDDIT_USERNAME env var).
    --password TEXT     Reddit password  (overrides REDDIT_PASSWORD env var).
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Reddit API credentials via Playwright.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run the browser in headless mode (default: headed/visible).",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("REDDIT_USERNAME", ""),
        help="Reddit username (falls back to REDDIT_USERNAME env var).",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("REDDIT_PASSWORD", ""),
        help="Reddit password (falls back to REDDIT_PASSWORD env var).",
    )
    return parser.parse_args()


def _prompt_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Return (username, password), prompting interactively if needed."""
    username = args.username
    if not username:
        username = input("Reddit username: ").strip()

    password = args.password
    if not password:
        password = getpass.getpass("Reddit password: ")

    return username, password


def _offer_write_env(client_id: str, client_secret: str) -> None:
    """Optionally write the credentials into the project's .env file."""
    # Validate before writing.
    if not client_id or not client_secret:
        print("⚠️  Skipping .env write — one or both credential values are empty.")
        return

    answer = input("\nWrite these into your .env file? [y/N] ").strip().lower()
    if answer != "y":
        print("OK — not written.")
        return

    # Find the .env file relative to this script's location (project root).
    env_path = Path(__file__).parent.parent / ".env"

    if not env_path.exists():
        example = env_path.with_suffix(".example")
        if example.exists():
            shutil.copy(example, env_path)
            print(f"Created {env_path} from .env.example")
        else:
            env_path.touch()
            print(f"Created empty {env_path}")

    text = env_path.read_text(encoding="utf-8")

    def _set_var(content: str, key: str, value: str) -> str:
        """Replace or append KEY=value in the env file content."""
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        replacement = f"{key}={value}"
        if pattern.search(content):
            return pattern.sub(replacement, content)
        # Append after the last non-empty line.
        return content.rstrip("\n") + f"\n{replacement}\n"

    text = _set_var(text, "REDDIT_CLIENT_ID", client_id)
    text = _set_var(text, "REDDIT_CLIENT_SECRET", client_secret)
    env_path.write_text(text, encoding="utf-8")
    print(f"✅ Credentials written to {env_path}")


def main() -> None:  # noqa: C901  (intentionally long — it's a script)
    args = _parse_args()

    # Import Playwright here so a missing install gives a clear message.
    try:
        from playwright.sync_api import TimeoutError as PWTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "❌  Playwright is not installed.\n"
            "   Run:  pip install playwright && playwright install chromium"
        )

    username, password = _prompt_credentials(args)

    print("\n🚀 Launching browser…")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        context = browser.new_context()
        page = context.new_page()

        # ------------------------------------------------------------------
        # Step 1 — Log in
        # ------------------------------------------------------------------
        print("🔐 Navigating to Reddit login page…")
        page.goto("https://www.reddit.com/login", wait_until="domcontentloaded")

        try:
            # Fill username field
            page.locator('input[name="username"], #loginUsername').fill(username)
            # Fill password field
            page.locator('input[name="password"], #loginPassword').fill(password)
            # Click the login button
            page.locator(
                'button[type="submit"]:has-text("Log In"), '
                'button[type="submit"]:has-text("Log in")'
            ).first.click()

            # Wait for navigation away from the login page.
            page.wait_for_url(
                lambda url: "login" not in url,
                timeout=30_000,
            )
        except PWTimeoutError:
            # Reddit may have presented a CAPTCHA or 2FA challenge.
            print(
                "\n⚠️  The page did not advance after clicking Log In.\n"
                "   This usually means Reddit is showing a CAPTCHA or a\n"
                "   two-factor-authentication prompt.\n"
                "   Please complete the challenge in the browser window,\n"
                "   then press Enter here to continue…"
            )
            input()

        # Verify we are actually logged in by checking for a user avatar or
        # the account menu element that appears after successful login.
        try:
            page.wait_for_selector(
                '[data-testid="user-drawer-trigger"], '
                'a[href*="/user/"], '
                '#header-bottom-right:not(:has(.login-required))',
                timeout=15_000,
            )
            print(f"✅ Logged in as {username}")
        except PWTimeoutError:
            print(
                "\n⚠️  Could not confirm login.  The page structure may have\n"
                "   changed, or login failed.  Please check the browser.\n"
                "   Press Enter to continue anyway, or Ctrl-C to abort…"
            )
            input()

        # ------------------------------------------------------------------
        # Step 2 — Navigate to the apps preferences page
        # ------------------------------------------------------------------
        print("🔗 Navigating to https://www.reddit.com/prefs/apps …")
        page.goto(
            "https://www.reddit.com/prefs/apps",
            wait_until="domcontentloaded",
        )

        # Give dynamic content time to render.
        page.wait_for_load_state("networkidle", timeout=20_000)

        # ------------------------------------------------------------------
        # Step 3 — Scrape existing "script"-type apps
        # ------------------------------------------------------------------
        credentials: list[dict[str, str]] = []

        try:
            # Each app is inside a container that holds both the "type" label
            # and the credential strings.  Reddit's legacy prefs page uses a
            # table-like structure; the new one uses divs.  We try both.

            # --- Legacy Reddit prefs/apps layout ----------------------------
            app_sections = page.locator(".developed-app").all()

            for section in app_sections:
                type_text = section.inner_text()

                # Only care about "script" type apps.
                if "personal use script" not in type_text.lower():
                    continue

                # The client_id appears as small text immediately under the
                # app name, before the "secret" row.
                try:
                    client_id = (
                        section.locator(".app-credentials .client-id, "
                                        "td.app-meta:first-child > .reddit-app-id, "
                                        ".app-data-overview .reddit-app-id")
                        .first.inner_text()
                        .strip()
                    )
                except Exception:
                    # Fallback: the id is the first short alphanumeric
                    # string in a span/div inside the credentials block.
                    client_id = ""

                try:
                    client_secret = (
                        section.locator(
                            "td:has-text('secret') + td, "
                            ".secret > span, "
                            '[id^="secret"]'
                        )
                        .first.inner_text()
                        .strip()
                    )
                except Exception:
                    client_secret = ""

                if client_id or client_secret:
                    name_el = section.locator("h3, .name, .app-name").first
                    app_name = (
                        name_el.inner_text().strip() if name_el.count() else "unknown"
                    )
                    credentials.append(
                        {
                            "name": app_name,
                            "client_id": client_id,
                            "client_secret": client_secret,
                        }
                    )

        except Exception as exc:
            print(f"⚠️  Error while reading app list: {exc}")

        # ------------------------------------------------------------------
        # Step 4 — If no apps found, help the user create one
        # ------------------------------------------------------------------
        if not credentials:
            print(
                "\n⚠️  No 'script'-type app found on your Reddit account.\n"
                "   The script will try to start the app-creation form for you."
            )

            try:
                # Click "are you a developer? create an app..." or
                # "create another app..." button.
                create_btn = page.locator(
                    'a:has-text("create an app"), '
                    'a:has-text("create another app"), '
                    'button:has-text("create an app"), '
                    'button:has-text("create another app")'
                ).first
                create_btn.click(timeout=10_000)
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PWTimeoutError:
                print(
                    "   Could not find the create-app button.  "
                    "Please click it manually in the browser."
                )
                input("   Press Enter once the creation form is visible… ")

            # Pre-fill the form fields.
            try:
                page.locator('input[name="name"], #name').fill("SENTRX-Q")
            except Exception:
                pass

            try:
                # Select the "script" radio button.
                page.locator('input[value="script"]').check()
            except Exception:
                pass

            try:
                page.locator(
                    'input[name="redirect_uri"], #redirect_uri'
                ).fill("http://localhost:8080")
            except Exception:
                pass

            print(
                "\n📝 The form has been pre-filled with:\n"
                "   name        = SENTRX-Q\n"
                "   type        = script\n"
                "   redirect_uri= http://localhost:8080\n"
                "\n"
                "   Please review the form in the browser and click\n"
                '   "create app" when you are ready.\n'
            )
            input("   Press Enter here after the app has been created… ")

            # Re-scrape the page for the newly created app.
            page.wait_for_load_state("networkidle", timeout=20_000)

            try:
                app_sections = page.locator(".developed-app").all()
                for section in app_sections:
                    type_text = section.inner_text()
                    if "personal use script" not in type_text.lower():
                        continue

                    try:
                        client_id = (
                            section.locator(
                                ".app-credentials .client-id, "
                                ".reddit-app-id"
                            )
                            .first.inner_text()
                            .strip()
                        )
                    except Exception:
                        client_id = ""

                    try:
                        client_secret = (
                            section.locator(
                                "td:has-text('secret') + td, "
                                ".secret > span, "
                                '[id^="secret"]'
                            )
                            .first.inner_text()
                            .strip()
                        )
                    except Exception:
                        client_secret = ""

                    if client_id or client_secret:
                        name_el = section.locator("h3, .name, .app-name").first
                        app_name = (
                            name_el.inner_text().strip()
                            if name_el.count()
                            else "SENTRX-Q"
                        )
                        credentials.append(
                            {
                                "name": app_name,
                                "client_id": client_id,
                                "client_secret": client_secret,
                            }
                        )
            except Exception as exc:
                print(f"⚠️  Error while reading newly created app: {exc}")

        browser.close()

    # ------------------------------------------------------------------
    # Step 5 — Print results
    # ------------------------------------------------------------------
    if not credentials:
        sys.exit(
            "\n❌  Could not extract credentials automatically.\n"
            "   Please visit https://www.reddit.com/prefs/apps manually,\n"
            "   find your 'script' app, and copy the client_id (shown\n"
            "   directly under the app name) and the secret value.\n"
        )

    print("\n" + "=" * 60)
    print("✅ Reddit API credentials found!\n")

    # Use the first script-type app found (most users only have one).
    cred = credentials[0]
    client_id = cred["client_id"]
    client_secret = cred["client_secret"]

    if len(credentials) > 1:
        print(
            f"ℹ️  Multiple script apps found ({len(credentials)}).  "
            "Showing the first one.\n"
        )

    print(f"  App name : {cred['name']}")
    print()
    print(f"  REDDIT_CLIENT_ID={client_id}")
    print(f"  REDDIT_CLIENT_SECRET={client_secret}")
    print()
    print("  Copy these into your .env file.")
    print("=" * 60)

    _offer_write_env(client_id, client_secret)


if __name__ == "__main__":
    main()
