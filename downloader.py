#!/usr/bin/env python3
"""
Codecademy Bootcamp Video Downloader

Downloads recorded bootcamp sessions for offline viewing.
Uses Playwright for authentication and yt-dlp for video downloading.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Error: playwright is not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("Error: python-dotenv is not installed.")
    print("Run: pip install python-dotenv")
    sys.exit(1)


# Load environment variables
load_dotenv()

# Configuration
CODECADEMY_EMAIL = os.getenv("CODECADEMY_EMAIL", "")
CODECADEMY_PASSWORD = os.getenv("CODECADEMY_PASSWORD", "")
BASE_URL = os.getenv("BASE_URL", "https://www.codecademy.com/bootcamps/fullstack-8/recordings")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "downloads")

# File paths
SCRIPT_DIR = Path(__file__).parent
COOKIES_FILE = SCRIPT_DIR / "cookies.json"
AUTH_STATE_FILE = SCRIPT_DIR / "auth_state.json"


def print_banner():
    """Print application banner."""
    print("\n" + "=" * 60)
    print("  Codecademy Bootcamp Video Downloader")
    print("=" * 60 + "\n")


def check_ffmpeg():
    """Check if ffmpeg is installed and accessible."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0:
            # Extract version info
            version_line = result.stdout.split('\n')[0] if result.stdout else "unknown"
            print(f"  ffmpeg found: {version_line[:60]}")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  Error checking ffmpeg: {e}")
    
    print("\n" + "=" * 60)
    print("  WARNING: ffmpeg is NOT installed!")
    print("=" * 60)
    print("\n  ffmpeg is required to merge video and audio streams.")
    print("  Without it, downloads will have separate audio/video files.\n")
    print("  To install ffmpeg on Windows:")
    print("    Option 1 (winget): winget install ffmpeg")
    print("    Option 2 (choco):  choco install ffmpeg")
    print("    Option 3: Download from https://ffmpeg.org/download.html")
    print("\n  After installing, restart your terminal and run this script again.\n")
    return False


def merge_split_files(output_path, only_nums=None):
    """
    Find and merge any split audio/video files in the output directory.
    This handles cases where ffmpeg wasn't available during download.
    """
    print("\n[*] Scanning for unmerged audio/video files...")
    
    # Pattern to match split files: Recording_XX.fhls-*.mp4
    # Video files have patterns like: -1422.mp4, -1896.mp4 (numbers only)
    # Audio files have patterns like: -audio-high-Original.mp4, -audio-high-English.mp4
    
    merged_count = 0

    # Normalize filter set
    only_set = None
    if only_nums is not None:
        if isinstance(only_nums, (list, tuple, set)):
            only_set = {int(x) for x in only_nums}
        else:
            only_set = {int(only_nums)}

    def _is_audio_candidate(suffix: str, ext: str) -> bool:
        s = (suffix or "").lower()
        e = (ext or "").lower()
        if "audio" in s:
            return True
        return e in {"m4a", "aac", "mp3", "opus", "ogg", "wav"}

    def _audio_score(suffix: str) -> int:
        s = (suffix or "").lower()
        # Prefer Original over English when both exist
        if "original" in s:
            return 3
        if "english" in s:
            return 2
        return 1

    def _video_score(suffix: str) -> int:
        # Prefer higher numeric quality tokens like "-2378" if present
        s = (suffix or "")
        m = re.search(r"-(\d+)$", s)
        return int(m.group(1)) if m else 0

    # Find all candidate media files (video and audio can be .mp4, audio can be .m4a, etc.)
    media_files = list(output_path.glob("Recording_*.*"))

    # Group files by recording number
    recordings = {}
    for f in media_files:
        # Match: Recording_02.<suffix>.<ext>  OR  Recording_02.<ext> (already merged)
        m_split = re.match(r"Recording_(\d+)\.(.+)\.([A-Za-z0-9]+)$", f.name)
        m_merged = re.match(r"Recording_(\d+)\.([A-Za-z0-9]+)$", f.name)

        if m_split:
            num = int(m_split.group(1))
            if only_set is not None and num not in only_set:
                continue
            suffix = m_split.group(2)
            ext = m_split.group(3)
            if num not in recordings:
                recordings[num] = {"videos": [], "audios": []}
            if _is_audio_candidate(suffix, ext):
                recordings[num]["audios"].append((f, suffix, ext))
            else:
                recordings[num]["videos"].append((f, suffix, ext))
        elif m_merged:
            # We'll handle "already merged" skipping below
            continue
    
    # Also check for already merged files to skip
    for f in output_path.glob("Recording_*.mp4"):
        if re.match(r"Recording_\d+\.mp4$", f.name):
            num = int(re.search(r"Recording_(\d+)\.mp4$", f.name).group(1))
            if only_set is not None and num not in only_set:
                continue
            if num in recordings:
                print(f"  Recording {num:02d}: Already merged, skipping")
                del recordings[num]
    
    # Merge each pair
    for num, files in sorted(recordings.items()):
        if not files.get("videos") or not files.get("audios"):
            if files.get("videos") and not files.get("audios"):
                print(f"  Recording {num:02d}: Video only, no audio file found")
            elif files.get("audios") and not files.get("videos"):
                print(f"  Recording {num:02d}: Audio only, no video file found")
            continue

        # Choose best candidates
        video_file, video_suffix, video_ext = sorted(
            files["videos"], key=lambda t: _video_score(t[1]), reverse=True
        )[0]
        audio_file, audio_suffix, audio_ext = sorted(
            files["audios"], key=lambda t: _audio_score(t[1]), reverse=True
        )[0]
        
        # Check for .part files (incomplete downloads)
        if (output_path / f"{audio_file.name}.part").exists():
            print(f"  Recording {num:02d}: Audio still downloading (.part file exists), skipping")
            continue
        if (output_path / f"{video_file.name}.part").exists():
            print(f"  Recording {num:02d}: Video still downloading (.part file exists), skipping")
            continue
        
        output_file = output_path / f"Recording_{num:02d}.mp4"
        
        print(f"  Recording {num:02d}: Merging video + audio...")
        print(f"    Video: {video_file.name}")
        print(f"    Audio: {audio_file.name}")
        
        # Use ffmpeg to merge
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(video_file),
            "-i", str(audio_file),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",  # Copy video codec (no re-encoding)
            "-c:a", "aac",   # Encode audio to AAC for compatibility
            "-b:a", "192k",  # Audio bitrate
            "-strict", "experimental",
            "-shortest",
            "-movflags", "+faststart",
            str(output_file)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            if result.returncode == 0 and output_file.exists():
                # Verify the output file is reasonable size
                if output_file.stat().st_size > 1000000:  # > 1MB
                    print(f"    ✓ Merged successfully: {output_file.name}")
                    
                    # Remove the split files
                    video_file.unlink()
                    audio_file.unlink()
                    print(f"    ✓ Cleaned up split files")
                    merged_count += 1
                else:
                    print(f"    ✗ Merge produced invalid file, keeping originals")
                    output_file.unlink()
            else:
                print(f"    ✗ Merge failed: {result.stderr[:200] if result.stderr else 'Unknown error'}")
                
        except Exception as e:
            print(f"    ✗ Error during merge: {e}")
    
    # Clean up any .ytdl temp files
    for ytdl_file in output_path.glob("*.ytdl"):
        try:
            ytdl_file.unlink()
        except:
            pass
    
    if merged_count > 0:
        print(f"\n  Successfully merged {merged_count} recording(s)")
    else:
        print(f"\n  No files needed merging")
    
    return merged_count


def check_credentials():
    """Verify that credentials are configured."""
    # Debug: Show what was loaded
    print(f"  Loaded email: {CODECADEMY_EMAIL[:10]}..." if CODECADEMY_EMAIL else "  Loaded email: (empty)")
    print(f"  Loaded password: {'*' * min(len(CODECADEMY_PASSWORD), 8)}..." if CODECADEMY_PASSWORD else "  Loaded password: (empty)")
    
    if not CODECADEMY_EMAIL or not CODECADEMY_PASSWORD:
        print("\nError: Credentials not configured!")
        print("\nPlease create a .env file with your credentials:")
        print("  1. Copy env.example.txt to .env")
        print("  2. Edit .env and add your email and password")
        print("\nExample .env contents:")
        print("  CODECADEMY_EMAIL=your_email@example.com")
        print("  CODECADEMY_PASSWORD=your_password")
        
        # Check if .env file exists
        env_path = SCRIPT_DIR / ".env"
        if env_path.exists():
            print(f"\n  .env file exists at: {env_path}")
            print("  But credentials are empty - check the file format!")
        else:
            print(f"\n  .env file NOT found at: {env_path}")
        return False
    
    if CODECADEMY_EMAIL == "your_email@example.com":
        print("\nError: You're still using the example email!")
        print("Please edit the .env file with your actual credentials.")
        return False
        
    return True


def save_cookies(context, filepath):
    """Save browser cookies to a file."""
    cookies = context.cookies()
    with open(filepath, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  Cookies saved to {filepath}")


def load_cookies(context, filepath):
    """Load cookies from file into browser context."""
    if filepath.exists():
        with open(filepath, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print(f"  Loaded cookies from {filepath}")
        return True
    return False


def login_to_codecademy(page, headless=False):
    """
    Log in to Codecademy using email and password.
    Returns True if login successful, False otherwise.
    """
    print("\n[1/4] Logging in to Codecademy...")
    
    try:
        # Navigate to login page
        login_url = "https://www.codecademy.com/login"
        print(f"  Navigating to {login_url}")
        page.goto(login_url, wait_until="networkidle", timeout=60000)
        
        # Wait for the login form to be visible
        time.sleep(2)  # Brief pause for any redirects
        
        # Check if already logged in (redirected to dashboard or similar)
        if "login" not in page.url.lower():
            print("  Already logged in!")
            return True
        
        # Fill in email (Codecademy uses user[login] as the field name)
        print("  Entering email...")
        email_selector = '#user_login, input[name="user[login]"]'
        page.wait_for_selector(email_selector, timeout=15000)
        page.fill(email_selector, CODECADEMY_EMAIL)
        time.sleep(0.5)
        
        # Fill in password (Codecademy uses user[password] as the field name)
        print("  Entering password...")
        password_selector = '#login__user_password, input[name="user[password]"]'
        page.wait_for_selector(password_selector, timeout=10000)
        page.fill(password_selector, CODECADEMY_PASSWORD)
        time.sleep(0.5)
        
        # Submit the form by pressing Enter on the password field
        print("  Submitting login form...")
        page.press(password_selector, "Enter")
        
        # Wait for navigation after login
        print("  Waiting for login to complete...")
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(3)  # Extra wait for any post-login processing
        
        # Debug: show current URL
        print(f"  Current URL after login: {page.url}")
        
        # Check for successful login by looking for logged-in UI elements
        logged_in_selectors = [
            'a:has-text("Dashboard")',
            'a:has-text("My learning")',
            '[class*="Dashboard"]',
            'nav a[href*="learn"]',
        ]
        
        for selector in logged_in_selectors:
            try:
                elem = page.query_selector(selector)
                if elem:
                    print("  Login successful! Found dashboard elements.")
                    return True
            except:
                pass
        
        # Also check if we're no longer on the login page
        if "/login" not in page.url:
            print("  Login successful! Redirected away from login page.")
            return True
        
        # If still on login page, check for error messages
        error_selectors = [
            '.error', 
            '.alert-danger', 
            '[role="alert"]', 
            '.notification--error',
        ]
        for selector in error_selectors:
            try:
                error_elem = page.query_selector(selector)
                if error_elem:
                    error_text = error_elem.inner_text()
                    if error_text.strip():
                        print(f"  Login error: {error_text}")
            except:
                pass
        
        # Take a screenshot to help debug
        screenshot_path = SCRIPT_DIR / "login_debug.png"
        page.screenshot(path=str(screenshot_path))
        print(f"  Debug screenshot saved to: {screenshot_path}")
        print("  Warning: Could not confirm login success")
        return False
        
        print("  Login successful!")
        return True
        
    except PlaywrightTimeout as e:
        print(f"  Timeout during login: {e}")
        return False
    except Exception as e:
        print(f"  Error during login: {e}")
        return False


def extract_video_url(page, recording_url):
    """
    Navigate to recording page and extract the video URL.
    Returns a tuple of (video_url, use_referer) where use_referer indicates
    if we need to pass the recording page as a referer for embed-only videos.
    """
    try:
        print(f"  Navigating to {recording_url}")
        page.goto(recording_url, wait_until="networkidle", timeout=60000)
        time.sleep(3)  # Wait for video player to initialize
        
        # Method 1: Check for direct video elements
        video_elem = page.query_selector("video source, video")
        if video_elem:
            video_url = video_elem.get_attribute("src")
            if video_url:
                print(f"  Found video element source")
                return video_url, False
        
        # Method 2: Check for iframe embeds (Vimeo, YouTube, Wistia, etc.)
        # For embed-only videos, we return the page URL and let yt-dlp extract from there
        iframe_selectors = [
            'iframe[src*="vimeo"]',
            'iframe[src*="youtube"]',
            'iframe[src*="wistia"]',
            'iframe[src*="player"]',
        ]
        for selector in iframe_selectors:
            iframe = page.query_selector(selector)
            if iframe:
                iframe_src = iframe.get_attribute("src")
                if iframe_src:
                    print(f"  Found embedded video iframe: {iframe_src[:50]}...")
                    # For Vimeo embed-only videos, use the page URL with referer
                    if "vimeo" in iframe_src:
                        print(f"  Vimeo embed detected - using page URL for yt-dlp")
                        return recording_url, True
                    return iframe_src, False
        
        # Method 3: Look for video player containers with data attributes
        player_selectors = [
            '[data-video-url]',
            '[data-src]',
            '.video-player',
            '.wistia_embed',
            '.vimeo-player',
        ]
        for selector in player_selectors:
            elem = page.query_selector(selector)
            if elem:
                for attr in ['data-video-url', 'data-src', 'data-video-id']:
                    url = elem.get_attribute(attr)
                    if url:
                        print(f"  Found video URL in player container")
                        return url, False
        
        # Method 4: Return the page URL itself for yt-dlp to handle
        print(f"  No direct video source found, will try page URL with yt-dlp")
        return recording_url, True
        
    except Exception as e:
        print(f"  Error extracting video URL: {e}")
        return recording_url, True  # Fall back to page URL


def export_cookies_for_ytdlp(context):
    """Export cookies in Netscape format for yt-dlp."""
    cookies = context.cookies()
    cookie_file = SCRIPT_DIR / "cookies_netscape.txt"
    
    with open(cookie_file, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
        f.write("# This is a generated file! Do not edit.\n\n")
        
        for cookie in cookies:
            # Netscape cookie format:
            # domain, include_subdomains, path, secure, expiry, name, value
            domain = cookie.get("domain", "")
            if not domain.startswith("."):
                domain = "." + domain
            
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"
            
            # Handle session cookies (expires=-1 or 0) - set to far future
            expires = cookie.get("expires", 0)
            if expires <= 0:
                # Set session cookies to expire in 1 year
                expiry = str(int(time.time()) + 31536000)
            else:
                expiry = str(int(expires))
            
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            
            f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
    
    return cookie_file


def download_video_with_ytdlp(video_url, output_path, cookies_file, video_num, referer_url=None):
    """
    Download video using yt-dlp.
    Returns True if successful, False otherwise.
    """
    output_template = str(output_path / f"Recording_{video_num:02d}.%(ext)s")
    
    cmd = [
        "yt-dlp",
        "--cookies", str(cookies_file),
        "-o", output_template,
        "--progress",
        "--newline",
        # Get best quality available, prefer mp4
        "-f", "bv*+ba/b",
        # Merge to mp4 if needed
        "--merge-output-format", "mp4",
        # Retry on errors
        "--retries", "3",
    ]
    
    # Add referer header for embed-only videos
    if referer_url:
        cmd.extend(["--referer", referer_url])
    
    cmd.append(video_url)
    
    print(f"  Running yt-dlp...")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            cwd=str(SCRIPT_DIR)
        )
        
        if result.returncode == 0:
            print(f"  Download completed successfully!")
            return True
        else:
            print(f"  yt-dlp exited with code {result.returncode}")
            return False
            
    except FileNotFoundError:
        print("  Error: yt-dlp is not installed or not in PATH")
        print("  Run: pip install yt-dlp")
        return False
    except Exception as e:
        print(f"  Error running yt-dlp: {e}")
        return False


def check_already_downloaded(output_path, video_num):
    """Check if a video has already been downloaded."""
    patterns = [
        f"Recording_{video_num:02d}.mp4",
        f"Recording_{video_num:02d}.webm",
        f"Recording_{video_num:02d}.mkv",
    ]
    for pattern in patterns:
        if (output_path / pattern).exists():
            return True
    return False


def download_recordings(start_num, end_num, headless=False, force=False, merge_only=False, allow_split=False):
    """
    Main function to download a range of recordings.
    """
    print_banner()
    
    # Check for ffmpeg
    print("[0/4] Checking dependencies...")
    ffmpeg_available = check_ffmpeg()
    
    # Create output directory
    output_path = SCRIPT_DIR / OUTPUT_DIR
    output_path.mkdir(exist_ok=True)
    print(f"\nOutput directory: {output_path}")
    
    # If merge_only mode, just merge existing files and exit
    if merge_only:
        if not ffmpeg_available:
            print("\nError: Cannot merge files without ffmpeg installed!")
            return False
        merge_split_files(output_path)
        return True

    # Typical behavior: require ffmpeg so outputs are always merged MP4s.
    # Users can override with --allow-split to keep separate audio/video files.
    if not ffmpeg_available and not allow_split:
        print("\n" + "=" * 60)
        print("  ERROR: ffmpeg is required for normal downloads")
        print("=" * 60)
        print("\n  This script downloads best-quality streams, which are often split")
        print("  into separate video+audio files unless ffmpeg is available to merge them.")
        print("\n  Fix: Install ffmpeg and restart your terminal, then re-run the script.")
        print("  Or:  Re-run with --allow-split to keep separate audio/video files.\n")
        return False
    
    # Check credentials
    if not check_credentials():
        return False
    
    # Track results
    successful = []
    failed = []
    skipped = []
    
    with sync_playwright() as p:
        # Launch browser (visible for first login, can use headless after cookies saved)
        print("\n[1/4] Launching browser...")
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        # Try to load existing cookies
        cookies_loaded = load_cookies(context, COOKIES_FILE)
        
        # Login to Codecademy
        if not login_to_codecademy(page, headless):
            # If login failed and we had cookies, they might be expired
            if cookies_loaded:
                print("  Cookies may be expired, trying fresh login...")
                # Clear cookies and retry
                context.clear_cookies()
                if not login_to_codecademy(page, headless):
                    print("\nLogin failed! Please check your credentials.")
                    browser.close()
                    return False
            else:
                print("\nLogin failed! Please check your credentials.")
                browser.close()
                return False
        
        # Save cookies for future use
        print("\n[2/4] Saving session cookies...")
        save_cookies(context, COOKIES_FILE)
        cookies_file = export_cookies_for_ytdlp(context)
        print(f"  Netscape cookies saved to {cookies_file}")
        
        # Download each recording
        print(f"\n[3/4] Downloading recordings {start_num} to {end_num}...")
        total = end_num - start_num + 1
        
        for i, num in enumerate(range(start_num, end_num + 1), 1):
            print(f"\n--- Recording {num} ({i}/{total}) ---")
            
            # Check if already downloaded
            if not force and check_already_downloaded(output_path, num):
                print(f"  Already downloaded, skipping (use --force to re-download)")
                skipped.append(num)
                continue
            
            # Build recording URL
            recording_url = f"{BASE_URL}/{num}"
            
            # Extract video URL
            print(f"  Extracting video from recording page...")
            video_url, needs_referer = extract_video_url(page, recording_url)
            
            if not video_url:
                print(f"  Could not find video URL")
                failed.append(num)
                continue
            
            # Download with yt-dlp
            referer = recording_url if needs_referer else None
            if download_video_with_ytdlp(video_url, output_path, cookies_file, num, referer):
                successful.append(num)
                # If user interrupted later, we still want completed recordings merged.
                if ffmpeg_available:
                    merge_split_files(output_path, only_nums=num)
            else:
                failed.append(num)
        
        browser.close()
    
    # Summary
    print("\n" + "=" * 60)
    print("[4/4] Download Summary")
    print("=" * 60)
    print(f"  Successful: {len(successful)} videos")
    if successful:
        print(f"    {successful}")
    print(f"  Skipped:    {len(skipped)} videos (already downloaded)")
    if skipped:
        print(f"    {skipped}")
    print(f"  Failed:     {len(failed)} videos")
    if failed:
        print(f"    {failed}")
    print(f"\nVideos saved to: {output_path}")
    
    # Post-download: merge any remaining split files if ffmpeg is available
    if ffmpeg_available:
        merge_split_files(output_path)
    elif allow_split:
        # Check if there are split files that need merging
        split_files = list(output_path.glob("Recording_*.fhls-*.mp4"))
        if split_files:
            print("\n" + "=" * 60)
            print("  NOTE: Split audio/video files detected!")
            print("=" * 60)
            print(f"  {len(split_files)} split files found that need merging.")
            print("  Install ffmpeg and run: python downloader.py --merge")
    
    return len(failed) == 0


def main():
    """Parse arguments and run the downloader."""
    parser = argparse.ArgumentParser(
        description="Download Codecademy bootcamp video recordings for offline viewing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python downloader.py --start 1 --end 25    Download recordings 1-25
  python downloader.py --video 5             Download only recording 5
  python downloader.py --start 10 --end 15   Download recordings 10-15
  python downloader.py --start 1 --end 5 --force   Re-download even if exists
  python downloader.py --merge               Merge any split audio/video files

Setup:
  1. Install dependencies: pip install -r requirements.txt
  2. Install Playwright browser: playwright install chromium
  3. Install ffmpeg: winget install ffmpeg (or choco install ffmpeg)
  4. Copy env.example.txt to .env and add your credentials
  5. Run the script with desired video range
        """
    )
    
    # Video selection arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--video", "-v",
        type=int,
        help="Download a single video by number"
    )
    group.add_argument(
        "--start", "-s",
        type=int,
        help="Starting video number (use with --end)"
    )
    group.add_argument(
        "--merge", "-m",
        action="store_true",
        help="Merge any split audio/video files (requires ffmpeg)"
    )
    
    parser.add_argument(
        "--end", "-e",
        type=int,
        help="Ending video number (use with --start)"
    )
    
    # Optional arguments
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)"
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-download even if video already exists"
    )

    parser.add_argument(
        "--allow-split",
        action="store_true",
        help="Allow downloads without ffmpeg (leaves separate audio/video files)"
    )
    
    args = parser.parse_args()
    
    # Handle merge-only mode
    if args.merge:
        success = download_recordings(
            start_num=0,
            end_num=0,
            merge_only=True
        )
        sys.exit(0 if success else 1)
    
    # Validate arguments
    if args.video:
        start_num = args.video
        end_num = args.video
    else:
        if not args.end:
            parser.error("--end is required when using --start")
        if args.start > args.end:
            parser.error("--start must be less than or equal to --end")
        start_num = args.start
        end_num = args.end
    
    if start_num < 1:
        parser.error("Video numbers must be positive")
    
    # Run the downloader
    success = download_recordings(
        start_num=start_num,
        end_num=end_num,
        headless=args.headless,
        force=args.force,
        allow_split=args.allow_split
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()