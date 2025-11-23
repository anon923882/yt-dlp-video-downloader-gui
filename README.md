# YT-DLP Video Downloader GUI

A user-friendly GUI application for downloading videos using yt-dlp with resolution selection options.

## Features

- 🎥 Fetch available video formats/resolutions
- ✅ Select preferred quality before download
- 📁 Custom download location
- 📊 Real-time progress with speed indication
- 🌐 Supports all yt-dlp compatible sites

## Installation

### Prerequisites
- Python 3.8 or higher
- tkinter (usually included with Python)

### Install Dependencies

```bash
pip install yt-dlp
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python video_downloader.py
```

2. Enter a video URL in the input field
3. Click **"Fetch Formats"** to retrieve available resolutions
4. Select your preferred resolution from the list
5. Choose a download folder (optional)
6. Click **"Download Selected Format"** to start downloading

## Features Explained

### Format Selection
The application displays available formats with detailed information:
- Resolution (e.g., 720p, 1080p, 4K)
- File format/extension (mp4, webm, etc.)
- File size
- Frame rate (fps)

### Progress Tracking
- Real-time download progress percentage
- Download speed indicator
- Visual progress bar

### Supported Sites
This tool supports all websites compatible with yt-dlp, including:
- YouTube
- Vimeo
- Dailymotion
- And many more...

For a complete list, visit: [yt-dlp supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## Requirements

- Python 3.8+
- yt-dlp
- tkinter (standard library)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - feel free to use this project for personal or commercial purposes.

## Disclaimer

Please respect copyright laws and terms of service of the websites you download from. This tool is for personal use only.
