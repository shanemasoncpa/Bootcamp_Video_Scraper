# Codecademy Bootcamp Video Downloader

Download your Codecademy bootcamp recorded sessions for offline viewing in VLC or any media player.

## Why This Tool?

Codecademy's browser-based video player can be unreliable for long recordings (2-3+ hours). This tool downloads the videos locally so you can:
- Watch without buffering issues
- Resume exactly where you left off
- Watch offline
- Use your preferred media player (VLC, etc.)

## Requirements

- **Python 3.10+** (tested with Python 3.13)
- **Windows, Mac, or Linux**
- **Codecademy Bootcamp enrollment** with valid login credentials

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browser

```bash
playwright install chromium
```

### 3. Install FFmpeg (for video/audio merging)

**Windows (PowerShell):**
```powershell
winget install ffmpeg
```

**Mac (Terminal):**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install ffmpeg
```

After installing ffmpeg, **restart your terminal** for the PATH to update.

### 4. Configure Your Credentials

**Windows:**
```powershell
copy env.example.txt .env
```

**Mac/Linux:**
```bash
cp env.example.txt .env
```

Edit `.env` with your Codecademy login credentials:

```
CODECADEMY_EMAIL=your_actual_email@example.com
CODECADEMY_PASSWORD=your_actual_password
```

**Important:** Do NOT use quotes around your email or password.

## Usage

### Download a Single Recording

```powershell
python downloader.py --video 5
```

### Download a Range of Recordings

```powershell
python downloader.py --start 1 --end 25
```

### Merge split audio/video files (repair)

If you previously downloaded recordings without ffmpeg installed (or if a run was interrupted), you may have separate audio/video files like:
- `Recording_02.fhls-....mp4` (video)
- `Recording_02.fhls-...audio-high-....mp4` (audio)

After installing ffmpeg (and restarting your terminal), merge everything into `Recording_XX.mp4` with:

```powershell
python downloader.py --merge
```

### Force Re-download (even if file exists)

```powershell
python downloader.py --start 1 --end 5 --force
```

### Run in Headless Mode (no browser window)

```powershell
python downloader.py --start 1 --end 10 --headless
```

### Download without ffmpeg (not recommended)

By default, this script **requires ffmpeg** so that normal downloads always end as a single merged `Recording_XX.mp4`.

If you *really* want to download without ffmpeg (leaving separate audio/video files), run:

```powershell
python downloader.py --start 1 --end 10 --allow-split
```

## Output

Videos are saved to the `downloads/` folder as:
- `Recording_01.mp4`
- `Recording_02.mp4`
- etc.

## Configuration Options

Edit the `.env` file to customize:

| Variable | Description | Default |
|----------|-------------|---------|
| `CODECADEMY_EMAIL` | Your login email | (required) |
| `CODECADEMY_PASSWORD` | Your login password | (required) |
| `BASE_URL` | Base URL for recordings | `https://www.codecademy.com/bootcamps/fullstack-8/recordings` |
| `OUTPUT_DIR` | Download folder | `downloads` |

### Changing the Bootcamp

If you're in a different bootcamp, update `BASE_URL` in your `.env` file:

```
BASE_URL=https://www.codecademy.com/bootcamps/YOUR-BOOTCAMP-ID/recordings
```

## Troubleshooting

### "Timeout during login" Error

The login page selectors may have changed. Check that:
1. Your credentials are correct in `.env`
2. You can log in manually at codecademy.com
3. There's no CAPTCHA blocking automated login

### Video/Audio Files Not Merged

Make sure ffmpeg is installed:

```bash
ffmpeg -version
```

If not found, install it (see Installation section) and restart your terminal.

If you already downloaded split files, run:

```powershell
python downloader.py --merge
```

### "Already logged in" but Download Fails

Delete the saved cookies and try again:

**Windows:**
```powershell
Remove-Item cookies.json, cookies_netscape.txt -ErrorAction SilentlyContinue
python downloader.py --video 1
```

**Mac/Linux:**
```bash
rm -f cookies.json cookies_netscape.txt
python downloader.py --video 1
```

### Browser Opens as "Guest"

Delete the browser profile folder:

**Windows:**
```powershell
Remove-Item -Recurse browser_profile -ErrorAction SilentlyContinue
```

**Mac/Linux:**
```bash
rm -rf browser_profile
```

### Download Interrupted

The tool skips already-downloaded videos. Just re-run the same command:

```powershell
python downloader.py --start 1 --end 25
```

To re-download a specific video, use `--force`:

```powershell
python downloader.py --video 5 --force
```

## How It Works

1. **Playwright** automates a Chromium browser to log into Codecademy
2. Navigates to each recording page and extracts the video embed URL
3. **yt-dlp** downloads the video from Vimeo (Codecademy's video host)
4. **ffmpeg** merges video and audio streams into a single MP4

## File Structure

```
Bootcamp Video Scraper/
├── downloader.py          # Main script
├── requirements.txt       # Python dependencies
├── env.example.txt        # Example configuration
├── .env                   # Your credentials (create this)
├── .gitignore             # Excludes sensitive files
├── README.md              # This file
├── downloads/             # Downloaded videos
├── cookies.json           # Saved session (auto-generated)
└── cookies_netscape.txt   # Cookies for yt-dlp (auto-generated)
```

## Legal Note

This tool is for personal use to download content you have legitimate access to through your Codecademy bootcamp enrollment. Please respect Codecademy's terms of service.

## License

MIT License - Use at your own risk.

