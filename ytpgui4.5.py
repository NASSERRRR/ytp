import customtkinter as ctk
import os
import threading
from tkinter import filedialog, messagebox
import subprocess
from PIL import Image
from io import BytesIO
import requests
from bs4 import BeautifulSoup
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, APIC, USLT, ID3NoHeaderError
import yt_dlp
import re # For cleaning filenames and text
import time # For logging timestamps and simulating delays
import json # For saving/loading settings
from appdirs import user_config_dir # For cross-platform config directory
import platform # To detect OS for opening folders
import webbrowser # For opening links in a web browser
import sys # Import sys for PyInstaller checks


# --- Determine if running in a PyInstaller bundle ---
# This flag will be True if the application is running as a PyInstaller-created executable.
IS_FROZEN = getattr(sys, 'frozen', False)

# Determine the correct FFmpeg executable name based on OS
if sys.platform.startswith('win'):
    FFMPEG_EXECUTABLE_NAME = 'ffmpeg.exe'
else: # Linux, macOS
    FFMPEG_EXECUTABLE_NAME = 'ffmpeg'

# Determine the default FFmpeg path based on the execution environment
if IS_FROZEN:
    # When bundled by PyInstaller, files added with --add-binary or --add-data
    # are often placed in the root of sys._MEIPASS (for 'onefile' mode)
    # or in the directory of the executable (for 'onedir' mode).
    # sys._MEIPASS is a temporary directory created for onefile executables.
    # We prioritize sys._MEIPASS if it exists, otherwise assume 'onedir' mode
    # where resources are relative to the executable's directory.
    _base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    DEFAULT_FFMPEG_PATH_DETERMINED = os.path.join(_base_path, FFMPEG_EXECUTABLE_NAME)
else:
    # When running as a standard Python script (development environment),
    # assume FFmpeg is in the same directory as the script.
    # If you prefer to rely on system PATH during development, change this to "ffmpeg".
    DEFAULT_FFMPEG_PATH_DETERMINED = os.path.join(os.path.dirname(os.path.abspath(__file__)), FFMPEG_EXECUTABLE_NAME)


# --- Configuration ---
# This variable now holds the *initial* default FFmpeg path,
# which is dynamically set based on whether the app is bundled or not.
# User settings will always override this initial default if they have saved a custom path.
DEFAULT_FFMPEG_PATH = DEFAULT_FFMPEG_PATH_DETERMINED


# Set CustomTkinter appearance
ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

# --- youtube-dlp Custom Logger and Progress Hook ---
class YTDL_Logger(object):
    """Custom logger to pipe youtube-dlp messages to the GUI log."""
    def __init__(self, app_instance):
        self.app = app_instance

    def debug(self, msg):
        # Filter out overly verbose debug messages, keep essential ones
        if any(keyword in msg for keyword in ["Downloading webpage", "Extracting URL", "Downloading", "Destination", "ffmpeg"]):
            self.app.log_message(f"[YTDL] {msg}", level="debug")
        pass # Comment out for less verbose debug logs in GUI

    def warning(self, msg):
        self.app.log_message(f"[YTDL WARNING] {msg}", level="warning")

    def error(self, msg):
        # Errors from ytdlp should ideally trigger a GUI messagebox, not just log
        self.app.log_message(f"[YTDL ERROR] {msg}", level="error")
        self.app.after(0, lambda: self.app.show_error("youtube-dlp Error", msg))

class YTDL_Progress_Hook(object):
    """Custom progress hook to update GUI during download."""
    def __init__(self, app_instance):
        self.app = app_instance

    def __call__(self, d):
        if d['status'] == 'downloading':
            filename = d.get('filename', 'Unknown File')
            # Clean up filename for display if it's a temp file
            if filename.endswith(".part"):
                filename = filename[:-5]
            
            total_bytes_str = d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', 'N/A'))
            percent_str = d.get('_percent_str', 'N/A')
            speed_str = d.get('_speed_str', 'N/A')
            eta_str = d.get('_eta_str', 'N/A')

            log_msg = f"[DOWNLOAD] {filename}: {percent_str} of {total_bytes_str} at {speed_str} ETA: {eta_str}"
            self.app.log_message(log_msg, level="info")

            # Update progress bar if enabled
            if self.app.settings.get('show_progress_bar', False):
                try:
                    percent = float(d.get('downloaded_bytes', 0)) / float(d.get('total_bytes', 1))
                    self.app.after(0, lambda: self.app.progress_bar.set(percent))
                except Exception:
                    pass # Ignore errors if bytes info is missing

        elif d['status'] == 'finished':
            self.app.log_message(f"[DOWNLOAD] Finished processing: {d['filename']}", level="info")
            if self.app.settings.get('show_progress_bar', False):
                self.app.after(0, lambda: self.app.progress_bar.set(0)) # Reset progress bar

        elif d['status'] == 'error':
            self.app.log_message(f"[DOWNLOAD ERROR] {d.get('filename', 'Unknown File')}: {d.get('error', 'An error occurred.')}", level="error")
            if self.app.settings.get('show_progress_bar', False):
                self.app.after(0, lambda: self.app.progress_bar.set(0)) # Reset progress bar


class SettingsWindow(ctk.CTkToplevel):
    # Added default_ffmpeg_path_value to constructor
    def __init__(self, master, current_settings, save_callback, get_config_path_func, default_ffmpeg_path_value):
        super().__init__(master)
        self.title("Settings")
        self.geometry("500x650") # Adjusted height and width for new options
        self.master = master
        self.current_settings = current_settings
        self.save_callback = save_callback
        self.get_config_path_func = get_config_path_func
        self.default_ffmpeg_path_value = default_ffmpeg_path_value # Store the default value

        self.grid_columnconfigure(1, weight=1)

        # FFmpeg Path
        self.ffmpeg_label = ctk.CTkLabel(self, text="FFmpeg Path:")
        self.ffmpeg_label.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="w")
        self.ffmpeg_entry = ctk.CTkEntry(self, placeholder_text="Path to ffmpeg executable")
        self.ffmpeg_entry.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        self.ffmpeg_entry.insert(0, self.current_settings.get('ffmpeg_path', ''))
        
        # New Reset FFmpeg Path Button
        self.reset_ffmpeg_button = ctk.CTkButton(self, text="Reset to Default", command=self._reset_ffmpeg_path)
        self.reset_ffmpeg_button.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="w")


        # Output Directory
        self.output_dir_label = ctk.CTkLabel(self, text="Default Output Directory:")
        self.output_dir_label.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.output_dir_entry = ctk.CTkEntry(self, placeholder_text="Default download folder", state="readonly")
        self.output_dir_entry.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        
        # FIX: Explicitly set state to normal before inserting and then back to readonly
        self.output_dir_entry.configure(state="normal")
        self.output_dir_entry.delete(0, ctk.END)
        self.output_dir_entry.insert(0, self.current_settings.get('output_dir', os.path.join(os.path.expanduser("~"), "Downloads")))
        self.output_dir_entry.configure(state="readonly")
        
        self.browse_output_button = ctk.CTkButton(self, text="Browse", command=self._browse_output_directory)
        self.browse_output_button.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="w")

        # MP3 Quality
        self.mp3_quality_label = ctk.CTkLabel(self, text="MP3 Quality:")
        self.mp3_quality_label.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        self.mp3_quality_optionemenu = ctk.CTkOptionMenu(self, values=["128k", "192k", "256k", "320k"])
        self.mp3_quality_optionemenu.grid(row=7, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        self.mp3_quality_optionemenu.set(self.current_settings.get('mp3_quality', '320k'))

        # Video Quality
        self.video_quality_label = ctk.CTkLabel(self, text="Video Quality (MP4):")
        self.video_quality_label.grid(row=8, column=0, padx=20, pady=(10, 0), sticky="w")
        self.video_quality_optionemenu = ctk.CTkOptionMenu(self, values=["360p", "480p", "720p", "1080p", "1440p", "2160p", "best"])
        self.video_quality_optionemenu.grid(row=9, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        self.video_quality_optionemenu.set(self.current_settings.get('video_quality', '1080p'))
        
        # Skip Lyrics Scrape Checkbox
        self.skip_lyrics_var = ctk.BooleanVar(value=self.current_settings.get('skip_lyrics_scrape', False))
        self.skip_lyrics_checkbox = ctk.CTkCheckBox(self, text="Skip Lyrics Scrape", variable=self.skip_lyrics_var)
        self.skip_lyrics_checkbox.grid(row=10, column=0, columnspan=2, padx=20, pady=(10, 0), sticky="w")

        # Skip Album Art Checkbox
        self.skip_album_art_var = ctk.BooleanVar(value=self.current_settings.get('skip_album_art', False))
        self.skip_album_art_checkbox = ctk.CTkCheckBox(self, text="Skip Album Art Embedding", variable=self.skip_album_art_var)
        self.skip_album_art_checkbox.grid(row=11, column=0, columnspan=2, padx=20, pady=(5, 10), sticky="w")

        # Show Progress Bar Checkbox
        self.show_progress_bar_var = ctk.BooleanVar(value=self.current_settings.get('show_progress_bar', True)) # Default to True
        self.show_progress_bar_checkbox = ctk.CTkCheckBox(self, text="Show Download Progress Bar", variable=self.show_progress_bar_var)
        self.show_progress_bar_checkbox.grid(row=12, column=0, columnspan=2, padx=20, pady=(5, 10), sticky="w")


        # Open Settings Folder Button
        self.open_config_folder_button = ctk.CTkButton(self, text="Open Settings Folder", command=self._open_config_folder)
        self.open_config_folder_button.grid(row=13, column=0, padx=20, pady=(10, 20), sticky="w")

        # Buttons
        self.save_button = ctk.CTkButton(self, text="Save", command=self._save_settings)
        self.save_button.grid(row=14, column=0, padx=20, pady=10, sticky="w")
        self.cancel_button = ctk.CTkButton(self, text="Cancel", command=self.destroy)
        self.cancel_button.grid(row=14, column=1, padx=20, pady=10, sticky="e")

        self.grab_set() # Make this window modal

    def _browse_output_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_dir_entry.configure(state="normal")
            self.output_dir_entry.delete(0, ctk.END)
            self.output_dir_entry.insert(0, folder_selected)
            self.output_dir_entry.configure(state="readonly")

    def _open_config_folder(self):
        """Opens the directory where the config.json file is located."""
        config_dir = os.path.dirname(self.get_config_path_func())
        try:
            if platform.system() == "Windows":
                os.startfile(config_dir)
            elif platform.system() == "Darwin": # macOS
                subprocess.run(["open", config_dir])
            else: # Linux and other Unix-like systems
                subprocess.run(["xdg-open", config_dir])
            self.master.log_message(f"Opened settings folder: {config_dir}", level="info")
        except Exception as e:
            self.master.show_error("Open Folder Error", f"Could not open settings folder: {e}")
            self.master.log_message(f"Error opening settings folder: {e}", level="error")

    def _reset_ffmpeg_path(self):
        """Resets the FFmpeg path entry to the default determined path."""
        self.ffmpeg_entry.delete(0, ctk.END)
        self.ffmpeg_entry.insert(0, self.default_ffmpeg_path_value)
        self.master.log_message(f"FFmpeg path reset to default: {self.default_ffmpeg_path_value}", level="info")

    def _save_settings(self):
        new_ffmpeg_path = self.ffmpeg_entry.get().strip()
        new_output_dir = self.output_dir_entry.get().strip()
        new_mp3_quality = self.mp3_quality_optionemenu.get()
        new_video_quality = self.video_quality_optionemenu.get()
        new_skip_lyrics = self.skip_lyrics_var.get()
        new_skip_album_art = self.skip_album_art_var.get()
        new_show_progress_bar = self.show_progress_bar_var.get()

        # Basic validation for paths
        # If the path is empty, it means we're relying on the default (bundled/system PATH)
        if new_ffmpeg_path and new_ffmpeg_path != "ffmpeg" and not os.path.exists(new_ffmpeg_path):
            messagebox.showerror("Validation Error", "FFmpeg path does not exist.")
            return
        if not os.path.isdir(new_output_dir):
            messagebox.showerror("Validation Error", "Output directory does not exist or is not a valid directory.")
            return

        updated_settings = {
            'ffmpeg_path': new_ffmpeg_path,
            'output_dir': new_output_dir,
            'mp3_quality': new_mp3_quality,
            'video_quality': new_video_quality,
            'skip_lyrics_scrape': new_skip_lyrics,
            'skip_album_art': new_skip_album_art,
            'show_progress_bar': new_show_progress_bar # Save new setting
        }
        self.save_callback(updated_settings)
        self.destroy()


class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Content Downloader")
        self.geometry("900x750") # Adjusted height for new elements
        self.grid_columnconfigure(1, weight=1) # Main content column
        self.grid_rowconfigure(0, weight=1) # Main content row

        self.settings = self._load_settings() # Load settings on startup

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=140, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # For spacing widgets vertically

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="YT Downloader", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=20)

        self.settings_button = ctk.CTkButton(self.sidebar_frame, text="Settings", command=self._open_settings)
        self.settings_button.grid(row=1, column=0, padx=20, pady=10)

        # New Buttons for README and Bug Report
        self.readme_button = ctk.CTkButton(self.sidebar_frame, text="Help (README)", command=self._open_readme)
        self.readme_button.grid(row=2, column=0, padx=20, pady=10)

        self.bug_report_button = ctk.CTkButton(self.sidebar_frame, text="Report Bug", command=self._report_bug)
        self.bug_report_button.grid(row=3, column=0, padx=20, pady=10)


        self.appearance_mode_label = ctk.CTkLabel(self.sidebar_frame, text="Appearance Mode:")
        self.appearance_mode_label.grid(row=5, column=0, padx=20, pady=(10, 0))
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self.sidebar_frame, values=["System", "Dark", "Light"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=6, column=0, padx=20, pady=(10, 20))


        # --- Main Content Area ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, rowspan=4, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1) # URL entry and log expand horizontally
        self.main_frame.grid_columnconfigure(1, weight=0) # For browse/open buttons
        self.main_frame.grid_columnconfigure(2, weight=0) # For open folder button
        self.main_frame.grid_rowconfigure(9, weight=1) # Log text area will expand vertically

        # URL Queue Input
        self.url_queue_label = ctk.CTkLabel(self.main_frame, text="YouTube URLs (one per line):")
        self.url_queue_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.url_queue_textbox = ctk.CTkTextbox(self.main_frame, height=100, wrap="word") # Textbox for multiple URLs
        self.url_queue_textbox.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        
        self.clear_queue_button = ctk.CTkButton(self.main_frame, text="Clear URLs", command=lambda: self.url_queue_textbox.delete("1.0", ctk.END))
        self.clear_queue_button.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))
        
        self.paste_button = ctk.CTkButton(self.main_frame, text="Paste from Clipboard", command=self._paste_from_clipboard)
        self.paste_button.grid(row=2, column=1, sticky="w", padx=(0, 10), pady=(0, 10)) # New Paste button

        self.queue_status_label = ctk.CTkLabel(self.main_frame, text="Queue: Ready")
        self.queue_status_label.grid(row=2, column=2, sticky="e", padx=10, pady=(0, 10))


        # Output Directory
        self.output_dir_label = ctk.CTkLabel(self.main_frame, text="Output Directory:")
        self.output_dir_label.grid(row=3, column=0, sticky="w", padx=10, pady=(10, 0))
        self.output_dir_entry = ctk.CTkEntry(self.main_frame, state="readonly") # Readonly
        self.output_dir_entry.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        # Explicitly populate the output directory entry from loaded settings
        self.output_dir_entry.configure(state="normal") 
        self.output_dir_entry.delete(0, ctk.END)
        self.output_dir_entry.insert(0, self.settings['output_dir'])
        self.output_dir_entry.configure(state="readonly")
        
        self.browse_button = ctk.CTkButton(self.main_frame, text="Browse", command=self.browse_output_directory)
        self.browse_button.grid(row=4, column=1, sticky="w", padx=(0, 10), pady=(0, 10)) # Aligned with Open Folder

        self.open_output_folder_button = ctk.CTkButton(self.main_frame, text="Open Folder", command=self._open_output_folder)
        self.open_output_folder_button.grid(row=4, column=2, sticky="e", padx=10, pady=(0, 10))


        # Format Selection
        self.format_label = ctk.CTkLabel(self.main_frame, text="Output Format:")
        self.format_label.grid(row=5, column=0, sticky="w", padx=10, pady=(10, 0))
        self.format_optionemenu = ctk.CTkOptionMenu(self.main_frame, values=["Video (MP4)", "Audio (MP3)"])
        self.format_optionemenu.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.format_optionemenu.set("Audio (MP3)") # Default to MP3


        # Download and Abort Buttons
        self.download_button = ctk.CTkButton(self.main_frame, text="Initiate Download", command=self.start_download_thread)
        self.download_button.grid(row=7, column=1, sticky="e", padx=10, pady=(0, 10))
        
        self.abort_button = ctk.CTkButton(self.main_frame, text="Abort Download", command=self.abort_current_download,
                                          fg_color="red", hover_color="#CC0000")
        self.abort_button.grid(row=7, column=2, sticky="e", padx=10, pady=(0, 10))
        self.abort_button.configure(state="disabled") # Disabled by default

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.main_frame, orientation="horizontal")
        self.progress_bar.grid(row=8, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        self.progress_bar.set(0)
        # Initially hide if setting is off
        if not self.settings.get('show_progress_bar', True):
            self.progress_bar.grid_forget()


        # Activity Log
        self.log_label = ctk.CTkLabel(self.main_frame, text="Activity Log:")
        self.log_label.grid(row=9, column=0, sticky="w", padx=10, pady=(10, 0))
        self.log_textbox = ctk.CTkTextbox(self.main_frame, wrap="word")
        self.log_textbox.grid(row=10, column=0, columnspan=3, sticky="nsew", padx=10, pady=(0, 10))
        self.log_textbox.configure(state="disabled") # Make it read-only
        
        # Save Log Button
        self.save_log_button = ctk.CTkButton(self.main_frame, text="Save Log", command=self.save_log_to_file)
        self.save_log_button.grid(row=11, column=0, sticky="w", padx=10, pady=(10, 0))


    def _get_config_path(self):
        """Returns the path to the configuration file."""
        config_dir = user_config_dir("YouTubeDownloader", "MyCompany") # Vendor name optional
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config.json")

    def _load_settings(self):
        """Loads settings from the config file or returns defaults."""
        config_path = self._get_config_path()
        default_settings = {
            'ffmpeg_path': DEFAULT_FFMPEG_PATH, # Now dynamically determined
            'output_dir': os.path.join(os.path.expanduser("~"), "Downloads"),
            'mp3_quality': '320k',
            'video_quality': '1080p',
            'skip_lyrics_scrape': False,
            'skip_album_art': False,
            'show_progress_bar': True # New default
        }
        try:
            with open(config_path, 'r') as f:
                settings = json.load(f)
                # Merge with defaults to ensure all keys exist and handle new settings
                loaded_settings = {**default_settings, **settings}
                return loaded_settings
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return default_settings

    def _save_settings(self, new_settings):
        """Saves settings to the config file and updates the UI."""
        self.settings.update(new_settings)
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
            self.log_message("Settings saved successfully.", level="info")
            # Update output directory display in main window if changed
            self.output_dir_entry.configure(state="normal")
            self.output_dir_entry.delete(0, ctk.END)
            self.output_dir_entry.insert(0, self.settings['output_dir'])
            self.output_dir_entry.configure(state="readonly")
            
            # Update progress bar visibility based on new setting
            if self.settings.get('show_progress_bar', True):
                self.progress_bar.grid(row=8, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
            else:
                self.progress_bar.grid_forget()

        except IOError as e:
            self.show_error("Settings Save Error", f"Could not save settings: {e}")


    def _open_settings(self):
        """Opens the settings window."""
        # Ensure only one settings window is open at a time
        if not hasattr(self, '_settings_window') or self._settings_window is None or not self._settings_window.winfo_exists():
            # Pass the dynamically determined default FFmpeg path to the SettingsWindow
            self._settings_window = SettingsWindow(self, self.settings, self._save_settings, self._get_config_path, DEFAULT_FFMPEG_PATH_DETERMINED)
        self._settings_window.focus()

    def _open_readme(self):
        """Opens the GitHub README in the default web browser."""
        readme_url = "https://github.com/NASSERRRR/ytp/blob/main/README.md"
        try:
            webbrowser.open(readme_url)
            self.log_message(f"Opened README in browser: {readme_url}", level="info")
        except Exception as e:
            self.show_error("Open URL Error", f"Could not open README: {e}")
            self.log_message(f"Error opening README: {e}", level="error")

    def _report_bug(self):
        """Opens the GitHub Issues page for reporting bugs in the default web browser."""
        issues_url = "https://github.com/NASSERRRR/ytp/issues/new"
        try:
            webbrowser.open(issues_url)
            self.log_message(f"Opened bug report page in browser: {issues_url}", level="info")
        except Exception as e:
            self.show_error("Open URL Error", f"Could not open bug report page: {e}")
            self.log_message(f"Error opening bug report page: {e}", level="error")


    def change_appearance_mode_event(self, new_appearance_mode: str):
        """Changes the CustomTkinter appearance mode."""
        ctk.set_appearance_mode(new_appearance_mode)

    def browse_output_directory(self):
        """Opens a file dialog to select the output directory and updates main window entry."""
        folder_selected = filedialog.askdirectory(initialdir=self.settings['output_dir'])
        if folder_selected:
            self.output_dir_entry.configure(state="normal")
            self.output_dir_entry.delete(0, ctk.END)
            self.output_dir_entry.insert(0, folder_selected)
            self.output_dir_entry.configure(state="readonly")
            # Immediately save this change to settings
            self.settings['output_dir'] = folder_selected
            self._save_settings(self.settings)

    def _open_output_folder(self):
        """Opens the currently selected output directory."""
        output_dir = self.output_dir_entry.get().strip()
        if not os.path.isdir(output_dir):
            self.show_error("Open Folder Error", "Output directory does not exist or is invalid.")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin": # macOS
                subprocess.run(["open", output_dir])
            else: # Linux and other Unix-like systems
                subprocess.run(["xdg-open", output_dir])
            self.log_message(f"Opened output folder: {output_dir}", level="info")
        except Exception as e:
            self.show_error("Open Folder Error", f"Could not open output folder: {e}")
            self.log_message(f"Error opening output folder: {e}", level="error")

    def _paste_from_clipboard(self):
        """Pastes content from the clipboard into the URL queue textbox."""
        try:
            clipboard_content = self.clipboard_get()
            if clipboard_content:
                current_text = self.url_queue_textbox.get("1.0", ctk.END).strip()
                if current_text:
                    self.url_queue_textbox.delete("1.0", ctk.END)
                    # Add a newline only if there's existing content
                    self.url_queue_textbox.insert("1.0", current_text + "\n" + clipboard_content)
                else:
                    self.url_queue_textbox.insert("1.0", clipboard_content)
                self.log_message("Pasted content from clipboard.", level="info")
            else:
                self.log_message("Clipboard is empty.", level="warning")
        except Exception as e:
            self.show_error("Clipboard Error", f"Could not paste from clipboard: {e}")


    def log_message(self, message, level="info"):
        """
        Logs a message to the activity textbox.
        This method is thread-safe as it uses self.after() for GUI updates.
        """
        current_time = time.strftime("%H:%M:%S")
        formatted_message = f"[{current_time}] {level.upper()}: {message}"
        # Use after to ensure GUI updates happen on the main thread
        self.after(0, lambda: self._update_log_textbox(formatted_message))

    def _update_log_textbox(self, message):
        """Internal method to update the log textbox safely."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert(ctk.END, message + "\n")
        self.log_textbox.see(ctk.END) # Auto-scroll
        self.log_textbox.configure(state="disabled")
        self.update_idletasks() # Update GUI immediately

    def show_error(self, title, message):
        """Displays an error message box and logs it."""
        self.log_message(f"ERROR: {message}", level="error")
        self.after(0, lambda: messagebox.showerror(title, message))

    def show_info(self, title, message):
        """Displays an info message box and logs it."""
        self.log_message(f"INFO: {message}", level="info")
        self.after(0, lambda: messagebox.showinfo(title, message))

    def save_log_to_file(self):
        """Saves the content of the activity log to a text file."""
        log_content = self.log_textbox.get("1.0", ctk.END)
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Save Activity Log"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(log_content)
                self.log_message(f"Activity log saved to: {file_path}", level="info")
                self.show_info("Save Log", "Activity log saved successfully!")
            except Exception as e:
                self.show_error("Save Log Error", f"Failed to save log: {e}")
                
    def abort_current_download(self):
        """Sets the abort flag to stop the current download."""
        self.log_message("Abort signal received. Attempting to stop download queue...", level="warning")
        self.abort_download_flag.set() # Signal the download thread to stop
        # GUI will be reset by the finally block in process_download_queue


    def start_download_thread(self):
        """Initiates the download process in a separate thread."""
        urls_raw = self.url_queue_textbox.get("1.0", ctk.END).strip()
        urls = [u.strip() for u in urls_raw.split('\n') if u.strip()]

        # --- Duplicate URL Detection ---
        unique_urls = []
        seen_urls = set()
        duplicates_found = 0
        for url in urls:
            if url not in seen_urls:
                unique_urls.append(url)
                seen_urls.add(url)
            else:
                duplicates_found += 1
        
        if duplicates_found > 0:
            self.log_message(f"Removed {duplicates_found} duplicate URL(s) from the queue.", level="info")
            # Update the textbox to reflect unique URLs (optional, but good UX)
            self.url_queue_textbox.delete("1.0", ctk.END)
            self.url_queue_textbox.insert("1.0", "\n".join(unique_urls))
        
        urls_to_process = unique_urls # Use the cleaned list

        output_dir = self.output_dir_entry.get().strip()
        output_format = self.format_optionemenu.get()
        
        # Input validation
        if not urls_to_process:
            self.show_error("Input Error", "Please enter at least one unique YouTube URL in the queue.")
            return
        if not os.path.isdir(output_dir):
            self.show_error("Input Error", "Selected output directory does not exist or is invalid.")
            return
        
        # Validate all URLs in the queue (after de-duplication)
        for url in urls_to_process:
            if not (url.startswith("http://") or url.startswith("https://") and ("youtube.com/" in url or "youtu.be/" in url or "/shorts/" in url)):
                self.show_error("Input Error", f"Invalid YouTube URL found in queue: {url}. Please correct or remove it.")
                return

        # Check for ffmpeg existence using the path from settings
        ffmpeg_path_in_use = self.settings['ffmpeg_path']
        # If the path is empty, it means we're relying on the default (bundled/system PATH)
        if not ffmpeg_path_in_use:
             self.log_message(f"No custom FFmpeg path set. Attempting to use default: {DEFAULT_FFMPEG_PATH}", level="info")
             ffmpeg_path_in_use = DEFAULT_FFMPEG_PATH # Use the dynamically determined default

        if ffmpeg_path_in_use and ffmpeg_path_in_use != "ffmpeg" and not os.path.exists(ffmpeg_path_in_use):
             self.show_error("FFmpeg Not Found", f"FFmpeg not found at the configured path: '{ffmpeg_path_in_use}'. Please update it in Settings.")
             return
        elif ffmpeg_path_in_use == "ffmpeg": # If "ffmpeg", try to find it in PATH
            try:
                subprocess.run(["which", "ffmpeg"], check=True, capture_output=True) # Unix-like systems
            except subprocess.CalledProcessError:
                try:
                    subprocess.run(["where", "ffmpeg"], check=True, capture_output=True, shell=True) # Windows
                except subprocess.CalledProcessError:
                    self.show_error("FFmpeg Not Found", "FFmpeg not found in system PATH. Please ensure it's installed and accessible, or set its path in Settings.")
                    return
            except FileNotFoundError: # For 'which' or 'where' not being found
                self.show_error("FFmpeg Path Check Error", "Could not check FFmpeg path. 'which' or 'where' command not found. Ensure FFmpeg is correctly installed or set the full path in settings.")
                return


        # Prepare GUI for download
        self.download_button.configure(state="disabled", text="Downloading...")
        self.abort_button.configure(state="normal") # Enable abort button
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", ctk.END) # Clear previous logs
        self.log_textbox.configure(state="disabled")
        
        # Show progress bar if enabled in settings
        if self.settings.get('show_progress_bar', True):
            self.progress_bar.grid(row=8, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
            self.progress_bar.set(0) # Reset progress
        else:
            self.progress_bar.grid_forget()

        self.log_message("Starting download queue...")
        self.log_message(f"Total unique items in queue: {len(urls_to_process)}")
        self.log_message(f"Output Directory: {output_dir}")
        self.log_message(f"Output Format: {output_format}")

        self.abort_download_flag = threading.Event() # Re-initialize flag for new download
        self.abort_download_flag.clear() # Clear any previous abort signal

        # Store the queue for the background thread
        self.download_queue = urls_to_process

        # Run download in a separate thread to keep GUI responsive
        download_thread = threading.Thread(target=self.process_download_queue, args=(output_dir, output_format))
        download_thread.daemon = True # Allow the app to exit even if thread is running
        download_thread.start()

    def process_download_queue(self, base_output_dir, output_format):
        """
        Processes items in the download queue sequentially.
        """
        is_aborted = False
        completed_items = 0
        total_items = len(self.download_queue)

        try:
            for i, url in enumerate(self.download_queue):
                if self.abort_download_flag.is_set():
                    self.log_message(f"Download queue aborted by user at item {i+1}/{total_items}.", level="warning")
                    is_aborted = True
                    break

                self.log_message(f"\n--- Processing Item {i+1}/{total_items}: {url} ---")
                self.queue_status_label.configure(text=f"Queue: Item {i+1}/{total_items}")

                try:
                    # Determine target video format based on settings
                    if "Audio" in output_format:
                        # Best audio, then convert to MP3 with specified quality
                        format_string = 'bestaudio/best'
                        postprocessors = [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': self.settings.get('mp3_quality', '320k') # Use quality from settings
                        },
                        # Add a postprocessor to remove original file after conversion if different extension
                        # This is tricky with yt-dlp's 'outtmpl' and conversion,
                        # A direct python deletion after conversion is safer but requires tracking original filename
                        # For now, let yt-dlp manage internal temp files.
                        ]
                    else: # Video (MP4)
                        # Specific resolution if available, otherwise best MP4
                        resolution = self.settings.get('video_quality', '1080p')
                        if resolution == 'best':
                            format_string = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                        else:
                            # Use the resolution filter, fallback to general best mp4 if specific res not found
                            # Note: youtube-dlp format selection is complex; this is a basic filter
                            format_string = f'bestvideo[ext=mp4][height<={resolution.replace("p", "")}]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                        postprocessors = []


                    # Common youtube-dlp options
                    ydl_opts_base = {
                        'format': format_string,
                        'quiet': False,
                        'noprogress': True,
                        'logger': YTDL_Logger(self),
                        'progress_hooks': [YTDL_Progress_Hook(self)],
                        'ffmpeg_location': self.settings['ffmpeg_path'],
                        'writethumbnail': False, # IMPORTANT: Disable ytdlp writing thumbnail to disk
                        'outtmpl': os.path.join(base_output_dir, '%(title)s.%(ext)s'), # Default template
                        'no_warnings': True,
                        'postprocessors': postprocessors # Apply postprocessors
                    }

                    is_playlist = ("playlist?list=" in url or "/playlist/" in url) and not "/shorts/" in url # Simple heuristic
                    
                    if is_playlist:
                        self.log_message("Detected a playlist URL. Fetching playlist info...")
                        info_ydl_opts = ydl_opts_base.copy()
                        info_ydl_opts['extract_flat'] = True
                        info_ydl_opts['quiet'] = True
                        info_ydl_opts['logger'] = YTDL_Logger(self)
                        info_ydl_opts.pop('postprocessors', None) # Remove postprocessors for info extraction pass
                        info_ydl_opts.pop('format', None) # Remove format for info extraction pass

                        with yt_dlp.YoutubeDL(info_ydl_opts) as ydl:
                            playlist_info_dict = ydl.extract_info(url, download=False)

                            if 'entries' in playlist_info_dict and playlist_info_dict['entries']:
                                sub_total_items = len(playlist_info_dict['entries'])
                                playlist_title_raw = playlist_info_dict.get('title', 'Unknown Playlist')
                                playlist_title_cleaned = self.clean_name_suffix(playlist_title_raw)
                                
                                # Create a dedicated folder for the playlist within the base_output_dir
                                current_output_dir = os.path.join(base_output_dir, self.sanitize_filename(playlist_title_cleaned))
                                os.makedirs(current_output_dir, exist_ok=True)
                                self.log_message(f"Created playlist folder: '{current_output_dir}'")
                                self.log_message(f"Playlist '{playlist_title_cleaned}' has {sub_total_items} videos.")

                                for j, entry in enumerate(playlist_info_dict['entries']):
                                    if self.abort_download_flag.is_set():
                                        self.log_message(f"Download aborted by user within playlist at video {j+1}/{sub_total_items}.", level="warning")
                                        is_aborted = True
                                        break # Exit inner playlist loop

                                    video_url = entry.get('url')
                                    if not video_url:
                                        self.log_message(f"  Skipping video {j+1}/{sub_total_items}: No URL found.", level="warning")
                                        continue

                                    video_title_raw = entry.get('title', f"Untitled Video {j+1}")
                                    artist_raw = entry.get('artist', entry.get('channel', ''))
                                    clean_video_title = self.sanitize_filename(video_title_raw)
                                    # clean_artist is done in process_audio_metadata now
                                    track_num_str = f"{j+1:02d}"
                                    filename_base = f"{track_num_str} - {self.sanitize_filename(artist_raw) if artist_raw else 'Unknown Artist'} - {clean_video_title}"
                                    
                                    # Create specific ydl_opts for this video from the base, applying postprocessors and output path
                                    single_video_ydl_opts = ydl_opts_base.copy()
                                    single_video_ydl_opts['outtmpl'] = os.path.join(current_output_dir, f"{filename_base}.%(ext)s")
                                    
                                    self.log_message(f"  Downloading video {j+1}/{sub_total_items}: '{video_title_raw}'")

                                    with yt_dlp.YoutubeDL(single_video_ydl_opts) as single_ydl:
                                        single_info_dict = single_ydl.extract_info(video_url, download=True)
                                        downloaded_filepath_base = single_ydl.prepare_filename(single_info_dict)

                                        if "Audio" in output_format:
                                            mp3_final_path = os.path.splitext(downloaded_filepath_base)[0] + ".mp3"
                                            time.sleep(0.5) 
                                            if not os.path.exists(mp3_final_path):
                                                potential_mp3s = [f for f in os.listdir(current_output_dir) if f.startswith(filename_base) and f.endswith(".mp3")]
                                                if potential_mp3s:
                                                    mp3_final_path = os.path.join(current_output_dir, potential_mp3s[0])
                                                    self.log_message(f"  Found MP3 at alternative path: {mp3_final_path}")
                                                else:
                                                    self.log_message(f"  Error: Could not locate MP3 for '{video_title_raw}'. Skipping tagging.", level="error")
                                                    continue 

                                            self.process_audio_metadata(mp3_final_path, single_info_dict, True, j + 1, playlist_title_cleaned, sub_total_items)
                                        else:
                                            self.log_message(f"  Video '{video_title_raw}' downloaded to {downloaded_filepath_base}")
                                if is_aborted: # If inner loop broke due to abort, break outer loop too
                                    break
                            else:
                                self.show_error("youtube-dlp Error", "Could not extract playlist entries or playlist is empty. Is the URL valid?")
                                continue # Move to next item in queue

                    else: # Single video download
                        # Set outtmpl for single video directly in the base_output_dir
                        ydl_opts_base['outtmpl'] = os.path.join(base_output_dir, '%(title)s.%(ext)s')
                        
                        self.log_message(f"  Downloading single video: '{url}'")
                        with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
                            info_dict = ydl.extract_info(url, download=True)
                            downloaded_filepath_base = ydl.prepare_filename(info_dict)

                            if "Audio" in output_format:
                                mp3_final_path = os.path.splitext(downloaded_filepath_base)[0] + ".mp3"
                                time.sleep(0.5)
                                if not os.path.exists(mp3_final_path):
                                    base_name = self.sanitize_filename(info_dict.get('title', ''))
                                    potential_mp3s = [f for f in os.listdir(base_output_dir) if f.startswith(base_name) and f.endswith(".mp3")]
                                    if potential_mp3s:
                                        mp3_final_path = os.path.join(base_output_dir, potential_mp3s[0])
                                        self.log_message(f"  Found MP3 at alternative path: {mp3_final_path}")
                                    else:
                                        self.log_message(f"  Error: Could not locate MP3 for '{info_dict.get('title')}'. Skipping tagging.", level="error")
                                        continue

                                self.process_audio_metadata(mp3_final_path, info_dict, False, None, None, 1)
                            else:
                                self.log_message(f"Video downloaded successfully to {downloaded_filepath_base}")
                    
                    completed_items += 1 # Only increment if item successfully processed (not aborted or error)

                except yt_dlp.utils.DownloadError as de:
                    self.log_message(f"Error processing {url}: {de}", level="error")
                    self.show_error("Download Error", f"Error for {url}: {de}")
                except FileNotFoundError:
                    self.log_message(f"Error: FFmpeg not found at '{self.settings['ffmpeg_path']}'. Please check settings.", level="error")
                    self.show_error("FFmpeg Not Found", f"FFmpeg executable not found at '{self.settings['ffmpeg_path']}'. Please ensure it's installed and the path is correct in Settings.")
                    break # Critical error, stop queue
                except Exception as e:
                    self.log_message(f"An unexpected error occurred for {url}: {e}", level="error")
                    self.show_error("Unexpected Error", f"An unexpected error occurred for {url}: {e}")
                    import traceback
                    self.log_message(f"Traceback: {traceback.format_exc()}", level="error")
                    # Check abort flag again before continuing in queue
                    if self.abort_download_flag.is_set():
                        is_aborted = True
                        break # Exit queue loop
                    continue # Try next item in queue if not critical

            if not is_aborted: # Only show completion message if not aborted
                self.show_info("Queue Complete", f"Download queue finished! Processed {completed_items} of {total_items} items.")
            else:
                self.show_info("Queue Aborted", f"Download queue aborted. Processed {completed_items} of {total_items} items before stopping.")

        except Exception as e:
            self.show_error("Queue Processing Error", f"An error occurred while managing the download queue: {e}")
            import traceback
            self.log_message(f"Queue Traceback: {traceback.format_exc()}", level="error")
        finally:
            self.after(0, lambda: self.download_button.configure(state="normal", text="Initiate Download"))
            self.after(0, lambda: self.abort_button.configure(state="disabled"))
            self.after(0, lambda: self.queue_status_label.configure(text="Queue: Ready")) # Reset queue status
            if self.settings.get('show_progress_bar', True):
                 self.after(0, lambda: self.progress_bar.set(0)) # Reset progress bar on completion/abort


    def sanitize_filename(self, filename):
        """Sanitizes a string to be a valid filename for common OSes."""
        # Replace characters not allowed in filenames
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace multiple spaces/periods with single ones, strip leading/trailing spaces/periods
        filename = re.sub(r'\s+', ' ', filename).strip()
        filename = re.sub(r'\.+', '.', filename).strip('.')
        # Limit length (optional, but good practice)
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def clean_name_suffix(self, name):
        """Removes common auto-generated suffixes from artist/album names."""
        suffixes_to_remove = [
            r' - Topic$',
            r' - Official Audio$',
            r' - Official Video$',
            r'\(Official Music Video\)$',
            r'\(Official Audio\)$',
            r'\[Official Music Video\]$',
            r'\[Official Audio\]$',
            r'^Album - ', # Added for the specific issue with album prefix
        ]
        for suffix_pattern in suffixes_to_remove:
            name = re.sub(suffix_pattern, '', name, flags=re.IGNORECASE).strip()
        return name

    def parse_artists(self, artist_string):
        """
        Parses a string containing potentially multiple artists into a list.
        Handles common delimiters like ',', ' & ', ' feat. '.
        """
        if not artist_string:
            return []

        # Replace common "featuring" patterns with comma for easier splitting
        artist_string = re.sub(r'\s*feat\.\s*', ',', artist_string, flags=re.IGNORECASE)
        artist_string = re.sub(r'\s*ft\.\s*', ',', artist_string, flags=re.IGNORECASE)
        artist_string = re.sub(r'\s*&\s*', ',', artist_string, flags=re.IGNORECASE)


        # Split by comma, then clean each part
        artists = [self.clean_name_suffix(a.strip()) for a in artist_string.split(',') if a.strip()]
        return [a for a in artists if a] # Remove any empty strings after cleaning


    def process_audio_metadata(self, mp3_file_path, video_info, is_playlist_item, track_number, playlist_title, total_tracks):
        """
        Processes and embeds metadata into the MP3 file.
        """
        self.log_message(f"Processing metadata for: {os.path.basename(mp3_file_path)}")
        try:
            audio = MP3(mp3_file_path, ID3=ID3)
            # Clear existing tags to prevent duplication/conflict
            audio.clear()
            # Ensure audio.tags is an ID3 object after clearing
            if audio.tags is None:
                audio.tags = ID3()


            # --- Tagging individual fields ---
            # Title
            title = video_info.get('title', 'Unknown Title')
            audio.tags.add(TIT2(encoding=3, text=[title]))
            self.log_message(f"  Tagged Title: {title}")

            # Artist
            # Prioritize ytdlp 'artist' field, then 'channel', then try parsing
            artists_list = []
            if video_info.get('artist'):
                artists_list = self.parse_artists(video_info['artist'])
            elif video_info.get('channel'):
                artists_list = self.parse_artists(video_info['channel'])

            if not artists_list:
                artists_list = ['Unknown Artist'] # Fallback if no artist found
            
            # TPE1 (Artist) supports multiple values as a list
            audio.tags.add(TPE1(encoding=3, text=artists_list))
            self.log_message(f"  Tagged Artist(s): {', '.join(artists_list)}")


            # Album
            album = "Unknown Album" # Default fallback
            if is_playlist_item and playlist_title:
                album = self.clean_name_suffix(playlist_title)
            else:
                # For single videos:
                # 1. Try to get album directly from video_info
                if video_info.get('album'):
                    album = self.clean_name_suffix(video_info['album'])
                # 2. Fallback to channel name, but with a check to avoid redundancy or generic names
                elif video_info.get('channel'):
                    channel_name_cleaned = self.clean_name_suffix(video_info['channel'])
                    # If the channel name is identical or very similar to the main artist,
                    # and the main artist is not generic, use "YouTube Single" or a more specific album from info_dict.
                    main_artist = artists_list[0] if artists_list else ''
                    if main_artist.lower() == channel_name_cleaned.lower() and main_artist.lower() not in ["unknown artist", "various artists"]:
                        album = "YouTube Single"
                    elif 'release_date' in video_info and video_info['release_date']:
                         # If it has a release date, perhaps it's a true single
                        album = f"{main_artist} - Single ({video_info['release_date'][:4]})" if main_artist else f"Single ({video_info['release_date'][:4]})"
                    else:
                        album = channel_name_cleaned # Use channel name if it's sufficiently distinct
                else:
                    album = "YouTube Single" # Final fallback for single tracks

            audio.tags.add(TALB(encoding=3, text=[album]))
            self.log_message(f"  Tagged Album: {album}")

            # Year
            upload_date = video_info.get('upload_date') # Format:YYYYMMDD
            if upload_date and len(upload_date) >= 4:
                year = upload_date[:4]
                audio.tags.add(TDRC(encoding=3, text=[year]))
                self.log_message(f"  Tagged Year: {year}")
            else:
                self.log_message("  Warning: Could not determine year for tagging.", level="warning")

            # Track Number
            if is_playlist_item and track_number is not None:
                track_string = f"{track_number}/{total_tracks}" if total_tracks else str(track_number)
                audio.tags.add(TRCK(encoding=3, text=[track_string]))
                self.log_message(f"  Tagged Track Number: {track_string}")
            else:
                self.log_message("  Skipping track number tagging for single video or missing playlist info.")


            # --- Album Art (Cover Art) ---
            if not self.settings.get('skip_album_art', False):
                self.process_album_art(audio, video_info.get('thumbnail'))
            else:
                self.log_message("  Skipping album art embedding as per settings.")

            # --- Lyrics ---
            if not self.settings.get('skip_lyrics_scrape', False):
                lyrics = self.extract_and_scrape_lyrics(video_info.get('description', ''), title, artists_list[0] if artists_list else '')
                if lyrics:
                    # Use USLT for unsynchronized lyrics
                    audio.tags.add(USLT(encoding=3, lang='eng', desc='Lyrics', text=lyrics))
                    self.log_message("  Embedded Lyrics successfully.")
                else:
                    self.log_message("  No substantial lyrics found or scraped.", level="warning")
            else:
                self.log_message("  Skipping lyrics scraping as per settings.")

            # Save the changes
            audio.save()
            self.log_message(f"Metadata tagging complete for: {os.path.basename(mp3_file_path)}")

        except ID3NoHeaderError:
            self.show_error("Tagging Error", f"File '{os.path.basename(mp3_file_path)}' is not a valid MP3 or has no ID3 header.")
        except Exception as e:
            self.show_error("Tagging Error", f"An error occurred during metadata processing for {os.path.basename(mp3_file_path)}: {e}")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}", level="error")

    def process_album_art(self, audio, thumbnail_url):
        """Fetches, processes, and embeds album art into the MP3."""
        if not thumbnail_url:
            self.log_message("  Warning: No thumbnail URL provided for album art.", level="warning")
            return

        try:
            self.log_message(f"  Fetching thumbnail from: {thumbnail_url} (in-memory)")
            response = requests.get(thumbnail_url, timeout=10)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            img_data = response.content

            img = Image.open(BytesIO(img_data))
            original_width, original_height = img.size

            # Crop to square from center
            min_dim = min(original_width, original_height)
            left = (original_width - min_dim) / 2
            top = (original_height - min_dim) / 2
            right = (original_width + min_dim) / 2
            bottom = (original_height + min_dim) / 2
            img_cropped = img.crop((left, top, right, bottom))

            # Resize to standard high-quality resolution (e.g., 1000x1000)
            target_size = (1000, 1000)
            # Use LANCZOS for high quality downsampling
            img_resized = img_cropped.resize(target_size, Image.Resampling.LANCZOS)

            # Save to BytesIO for embedding
            img_byte_arr = BytesIO()
            # Mutagen's APIC tag prefers PNG for better compatibility and quality, though JPEG is common.
            # Convert if original is not PNG or if we want to ensure PNG.
            if img_resized.mode != 'RGB':
                img_resized = img_resized.convert('RGB')
            img_resized.save(img_byte_arr, format='JPEG', quality=90) # Use JPEG, set quality
            img_byte_arr = img_byte_arr.getvalue()

            audio.tags.add(APIC(
                encoding=3, # UTF-8
                mime='image/jpeg', # Image format
                type=3, # 3 is for Front Cover
                desc='Cover',
                data=img_byte_arr
            ))
            self.log_message("  Embedded Album Art successfully.")
        except requests.exceptions.RequestException as req_e:
            self.log_message(f"  Warning: Failed to download album art from '{thumbnail_url}': {req_e}", level="warning")
        except Exception as e:
            self.log_message(f"  Warning: Could not process or embed album art: {e}", level="warning")
            import traceback
            self.log_message(f"  Album Art Traceback: {traceback.format_exc()}", level="debug") # Use debug for less critical errors

    def extract_and_scrape_lyrics(self, description, title, artist):
        """
        Attempts to extract lyrics from video description, then scrapes online if necessary.
        """
        # 1. Prioritize extracting from description
        self.log_message("  Attempting to extract lyrics from video description...")
        lyrics_block_match = re.search(
            r'(lyrics:?[\s\r\n]+.*?)' # Capture 'lyrics:' followed by content
            r'(?:(?:\n{2,}|\r\n{2,})(?:links|socials|subscribe|copyright|produced by|video by|mixed by|mastered by|music by|album by|uploaded by))?', # Non-capturing group for common trailing text
            description, re.DOTALL | re.IGNORECASE
        )

        if lyrics_block_match:
            potential_lyrics = lyrics_block_match.group(1).strip()
            # Clean "lyrics:" prefix
            clean_lyrics = re.sub(r'^lyrics:?\s*', '', potential_lyrics, flags=re.IGNORECASE).strip()
            
            # Check for substantial content (more than 5 lines and 100 characters)
            if len(clean_lyrics.split('\n')) > 5 and len(clean_lyrics) > 100:
                self.log_message("  Lyrics found and extracted from video description.")
                return clean_lyrics
        else:
            self.log_message("  No substantial lyrics found in video description. Attempting to scrape online.")

        # 2. Scrape from an external source (e.g., Genius.com, AZLyrics.com)
        try:
            search_query = f"{title} {artist} lyrics" if artist else f"{title} lyrics"
            google_search_url = f"https://www.google.com/search?q={requests.utils.quote(search_query)}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Connection': 'keep-alive',
            }
            
            self.log_message(f"  Searching Google for lyrics: '{search_query}'")
            google_response = requests.get(google_search_url, headers=headers, timeout=10)
            google_response.raise_for_status()
            google_soup = BeautifulSoup(google_response.text, 'html.parser')

            lyrics_site_url = None
            # Prioritize Genius, then AZLyrics
            for a_tag in google_soup.find_all('a', href=True):
                href = a_tag['href']
                if "genius.com" in href and "lyrics" in href:
                    lyrics_site_url = href
                    self.log_message(f"  Found Genius.com link: {lyrics_site_url}")
                    break
                elif "azlyrics.com" in href and "lyrics" in href:
                    lyrics_site_url = href
                    self.log_message(f"  Found AZLyrics.com link: {lyrics_site_url}")
                    break

            if lyrics_site_url:
                # Clean up Google redirect URL if necessary
                if "/url?q=" in lyrics_site_url:
                    lyrics_site_url = lyrics_site_url.split("/url?q=")[1].split("&sa=")[0]
                
                self.log_message(f"  Attempting to scrape lyrics from: {lyrics_site_url}")
                lyrics_response = requests.get(lyrics_site_url, headers=headers, timeout=15)
                lyrics_response.raise_for_status()
                lyrics_soup = BeautifulSoup(lyrics_response.text, 'html.parser')
                
                full_lyrics = None

                # Logic to extract lyrics (highly site-specific and might break with website changes)
                if "genius.com" in lyrics_site_url:
                    # Genius lyrics are typically in a div with data-lyrics-container attribute or specific class
                    lyrics_divs = lyrics_soup.find_all('div', {'data-lyrics-container': 'true'})
                    if not lyrics_divs: # Fallback for older/different structures
                         lyrics_divs = lyrics_soup.find_all('div', class_=lambda x: x and 'Lyrics__Container' in x) # More flexible class matching

                    if lyrics_divs:
                        lyrics_text_parts = []
                        for lyrics_div in lyrics_divs:
                            # Use .stripped_strings to get text content and handle newlines, then re-join
                            lyrics_text_parts.extend(lyrics_div.stripped_strings)
                        
                        full_lyrics = '\n'.join(lyrics_text_parts).strip()
                        # Clean up annotations like "[Verse 1]" from Genius - keep if it's structural (like 'verse', 'chorus')
                        full_lyrics = re.sub(r'\[(.*?)\]', lambda m: m.group(0) if re.search(r'(verse|chorus|bridge|outro|intro|hook|pre-chorus|interlude|solo)', m.group(1).lower()) else '', full_lyrics)
                        full_lyrics = re.sub(r'\n{3,}', '\n\n', full_lyrics) # Reduce excessive newlines
                        
                elif "azlyrics.com" in lyrics_site_url:
                    # AZLyrics lyrics are often in a specific div after a comment or certain structure
                    # This is tricky due to ads and comments. The lyrics are typically in a <div> without a class
                    # that is a direct sibling to an ad block or a specific comment.
                    lyrics_div_container = lyrics_soup.find('div', class_='col-xs-12 col-lg-8 text-center')
                    if lyrics_div_container:
                        for sibling in lyrics_div_container.children:
                            # Look for the target div. AZLyrics often places lyrics after a specific comment.
                            if isinstance(sibling, str) and "<!-- Usage of azlyrics.com content by any third-party lyrics provider is prohibited by our licensing agreement. -->" in sibling:
                                # The very next <div> sibling usually contains the lyrics
                                actual_lyrics_div = sibling.find_next_sibling('div')
                                if actual_lyrics_div and not actual_lyrics_div.get('class'): # Check if it has no class
                                    full_lyrics = actual_lyrics_div.get_text(separator="\n").strip()
                                    break
                            elif sibling.name == 'div' and not sibling.get('class') and len(sibling.find_all('br')) > 5:
                                # Fallback: if it's a div with no class and many <br> (likely lyrics)
                                full_lyrics = sibling.get_text(separator="\n").strip()
                                break
                
                if full_lyrics and len(full_lyrics) > 100: # Simple check for substantial content
                    self.log_message(f"  Scraped lyrics successfully from {lyrics_site_url}.")
                    return full_lyrics
                else:
                    self.log_message(f"  Failed to extract substantial lyrics from {lyrics_site_url}. Content too short or structure unexpected.", level="warning")
            else:
                self.log_message("  No suitable lyrics website found in Google search results.", level="warning")

        except requests.exceptions.RequestException as req_e:
            self.log_message(f"  Error accessing lyrics website: {req_e}", level="warning")
        except Exception as e:
            self.log_message(f"  Error during lyrics scraping: {e}", level="warning")
            import traceback
            self.log_message(f"  Lyrics Scraping Traceback: {traceback.format_exc()}", level="debug")

        return None # Return None if no lyrics were found or successfully scraped


if __name__ == "__main__":
    app = YouTubeDownloaderApp()
    app.mainloop()

