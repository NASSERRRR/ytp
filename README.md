# **YouTube Content Downloader**

A user-friendly desktop application built with CustomTkinter that allows you to effortlessly download YouTube videos and playlists as MP3 audio files or MP4 video files. It features extensive metadata tagging for MP3s, including intelligent artist and album recognition, cover art embedding, and even lyrics scraping.

## **Features**

* **YouTube Video & Playlist Downloads**: Download content from single URLs or entire playlists.  
* **Multiple Output Formats**: Choose between MP3 (audio) or MP4 (video) formats.  
* **Customizable Quality**: Select desired MP3 audio quality (128k, 192k, 256k, 320k) and MP4 video quality (up to 2160p or best available).  
* **Intelligent Metadata Tagging (MP3)**:  
  * **Title, Artist, Album, Year, Track Number**: Automatically extracts and embeds relevant tags.  
  * **Multi-Artist Support**: Parses multiple artists correctly (e.g., "Artist1 ft. Artist2").  
  * **Smart Album Naming**: Derives album names for singles or uses playlist titles for albums.  
* **Album Art Embedding**: Fetches and embeds high-quality cover art into MP3 files.  
* **Lyrics Scraping**: Attempts to extract lyrics from video descriptions or scrapes them from online sources (e.g., Genius, AZLyrics) and embeds them into MP3s.  
* **Customizable Output Directory**: Set your preferred download location.  
* **Download Queue**: Manage multiple downloads sequentially.  
* **Real-time Activity Log**: Monitor download progress and application events.  
* **Download Abort Functionality**: Stop ongoing downloads if needed.  
* **Configurable Settings**: Easily adjust FFmpeg path, default output directory, quality settings, and metadata options.  
* **Dark/Light/System Appearance Modes**: Customize the GUI theme.  
* **Help & Bug Reporting**: Direct links to the GitHub README and Issue Tracker from within the app.  
* **Clipboard Paste**: Quickly paste YouTube URLs from your clipboard.  
* **Progress Bar**: Visual feedback on download progress (toggleable in settings).

## **Installation**

### **Download Pre-packaged Executable (Recommended for Users)**

For the easiest way to get started, download the ready-to-use executable for your operating system from the GitHub Releases page. FFmpeg is already included in these packages, so no separate installation is required.

1. Go to the [GitHub Releases page](https://github.com/NASSERRRR/ytp/releases) for this project.  
2. Download the appropriate file for your OS (e.g., .dmg for macOS, .exe for Windows, .tar.gz for Linux).  
3. Run the executable.

### **Building from Source (for Developers)**

If you wish to run the application directly from the Python script, contribute to the project, or build your own executable, follow these steps.

#### **Prerequisites**

1. **Python 3.x**: Ensure you have Python 3.7 or newer installed.  
   * Download from: [python.org](https://www.python.org/downloads/)  
2. **FFmpeg**: This tool is essential for video/audio conversion and merging.  
   * **For Development (Running from Python script)**: If you're running the ytpgui4.5.py script directly, place the ffmpeg (or ffmpeg.exe for Windows) executable in the same directory as your script. You can download static builds from [ffmpeg.org/download.html](https://ffmpeg.org/download.html).  
   * **For Packaged Application**: No manual FFmpeg installation is required as it's included within the application bundle. If you need to revert to the bundled FFmpeg after changing the path, use the "Reset to Default" button in the settings.

#### **Application Setup**

1. **Clone the Repository**:  
   git clone https://github.com/NASSERRRR/ytp.git  
   cd ytp

2. **Prepare FFmpeg for Bundling (if you plan to package yourself)**:  
   * If you intend to create your own executable later, ensure you've placed the ffmpeg (or ffmpeg.exe) file directly into your ytp project's root directory, next to your ytpgui4.5.py script.  
   * Your project structure should look something like this (after placing FFmpeg):  
     ytp/  
       ytpgui4.5.py  
       ffmpeg  (or ffmpeg.exe for Windows)  
       ytp.icns (if you added your icon)  
       README.md  
       ...other project files...

3. **Create a Virtual Environment (Recommended)**:  
   python \-m venv venv  
   \# On Windows:  
   venv\\Scripts\\activate  
   \# On macOS/Linux:  
   source venv/bin/activate

4. **Install Dependencies**:  
   pip install customtkinter Pillow requests beautifulsoup4 mutagen yt-dlp appdirs pyinstaller

## **Packaging (Creating an Executable)**

Once you've completed the setup and placed the FFmpeg executable in your project root, you can create a standalone executable using PyInstaller.

1. Navigate to your Project Directory:  
   Open your terminal or command prompt and change your directory to the ytp project folder:  
   cd path/to/your/ytp

2. **Run the PyInstaller Command**:  
   Use the following command to create a single executable file in the dist/ directory, including FFmpeg and your custom icon. Remember the separator for \--add-binary (: for macOS/Linux, ; for Windows).  
   * **For macOS/Linux**:  
     pyinstaller \--noconfirm \--onefile \--windowed \\  
       \--name "YouTubeDownloader" \\  
       \--add-binary "ffmpeg:." \\  
       \--collect-all "yt\_dlp" \\  
       \--collect-all "appdirs" \\  
       \--icon "ytp.icns" \\  
       "ytpgui4.5.py"

   * **For Windows**:  
     pyinstaller \--noconfirm \--onefile \--windowed \\  
       \--name "YouTubeDownloader" \\  
       \--add-binary "ffmpeg.exe;." \\  
       \--collect-all "yt\_dlp" \\  
       \--collect-all "appdirs" \\  
       \--icon "ytp.ico" \\  
       "ytpgui4.5.py"

     (Note: For Windows, your icon file should typically be a .ico file, e.g., ytp.ico)

After running the command, your executable will be located in the dist folder.

## **Usage**

1. **Run the Application**:  
   * If running from the script: python ytpgui4.5.py  
   * If running the packaged app: Navigate to the dist folder and launch the YouTubeDownloader executable.  
2. **Configure Settings (First Time Use or Reset)**:  
   * Click the "Settings" button in the sidebar.  
   * **FFmpeg Path**: By default, this will automatically point to the bundled FFmpeg when running the packaged app. If you've changed it and want to revert, click the **"Reset to Default"** button.  
   * **Default Output Directory**: Choose where downloads will be saved.  
   * Adjust MP3/Video Quality, Lyrics/Album Art preferences, and Progress Bar visibility as desired.  
   * Click "Save".  
3. **Download Content**:  
   * Enter YouTube video or playlist URLs into the "YouTube URLs" textbox, one URL per line.  
   * Use the "Paste from Clipboard" button to quickly add URLs.  
   * Select your desired "Output Format" (Video or Audio).  
   * Click "Initiate Download".  
   * Monitor progress in the "Activity Log" and the progress bar.  
4. **Open Folders**:  
   * Use the "Open Folder" button next to the "Output Directory" to quickly navigate to your downloads.  
   * Use "Open Settings Folder" in the Settings window to manage config.json.

## **Settings**

The "Settings" window (accessible from the sidebar) allows you to customize:

* **FFmpeg Path**: Path to your FFmpeg executable. A "Reset to Default" button is provided to easily revert to using the bundled FFmpeg.  
* **Default Output Directory**: The folder where downloaded files will be saved.  
* **MP3 Quality**: Bitrate for MP3 audio (128k, 192k, 256k, 320k).  
* **Video Quality (MP4)**: Resolution for MP4 videos (e.g., 720p, 1080p, 2160p, or best).  
* **Skip Lyrics Scrape**: Disable automatic lyrics fetching and embedding.  
* **Skip Album Art Embedding**: Disable automatic cover art fetching and embedding.  
* **Show Download Progress Bar**: Toggle the visibility of the real-time progress bar.

## **Troubleshooting**

* **"FFmpeg Not Found" Error**:  
  * **For packaged app**: If you reset the path or left it default, ensure FFmpeg was correctly placed in your project root before bundling and that the PyInstaller command was correct.  
  * **For running script directly**: Ensure ffmpeg (or ffmpeg.exe) is in the same directory as your Python script, or is correctly installed and added to your system's PATH.  
  * If you manually entered a path in settings, double-check its correctness.  
* **"Download Error" / "youtube-dlp Error"**:  
  * The URL might be invalid, age-restricted, geo-restricted, or private.  
  * Check your internet connection.  
  * Sometimes YouTube's format changes, and yt-dlp might need an update. If running the script, try pip install \--upgrade yt-dlp. If running the bundled app, a new version of the app might be required.  
* **Lyrics/Album Art Not Appearing**:  
  * Ensure "Skip Lyrics Scrape" and "Skip Album Art Embedding" are unchecked in settings.  
  * The content might not have extractable lyrics/thumbnail, or the scraping logic might be broken due to website changes. Check the Activity Log for warnings.  
* **Application Crashes / Unexpected Behavior**:  
  * Check the "Activity Log" for detailed error messages.  
  * Ensure all dependencies are installed and up-to-date (pip install \-r requirements.txt \--upgrade if running the script).  
  * If issues persist, please [report a bug](https://www.google.com/search?q=https://github.com/NASSERRRR/ytp/issues/new).

## **🤝 Contributing**

Contributions are welcome\! If you have suggestions for features, improvements, or bug fixes, please feel free to:

1. Fork the repository.  
2. Create a new branch (git checkout \-b feature/your-feature-name).  
3. Make your changes.  
4. Commit your changes (git commit \-m 'Add new feature').  
5. Push to the branch (git push origin feature/your-feature-name).  
6. Open a Pull Request.

## **🐛 Report a Bug**

If you encounter any issues or unexpected behavior, please [report them on the GitHub Issues page](https://www.google.com/search?q=https://github.com/NASSERRRR/ytp/issues/new). When reporting a bug, please include:

* A clear description of the bug.  
* Steps to reproduce the bug.  
* Expected behavior vs. actual behavior.  
* Any error messages from the "Activity Log".  
* Your operating system.  
* The version of Python you are using.

## **License**

This project is licensed under the MIT License \- see the [LICENSE](https://www.google.com/search?q=https://github.com/NASSERRRR/ytp/blob/main/LICENSE) file for details.