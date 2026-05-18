import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
from pathlib import Path
import time
from PIL import Image

from utils import (
    load_settings, 
    save_settings, 
    load_history, 
    add_to_history, 
    open_folder, 
    open_file, 
    fetch_thumbnail,
    load_playlists,
    save_playlists
)
from downloader import VeloDownloader
from clipper import process_clip

# --- THEME CONFIGURATION ---
# Colors are defined as (Light Mode, Dark Mode)
BG_COLOR = ("#F0F2F5", "#0B0B0F")
SIDEBAR_COLOR = ("#FFFFFF", "#16161D")
CARD_COLOR = ("#FFFFFF", "#1C1C24")
ACCENT_COLOR = ("#0066FF", "#00D2FF")
ACCENT_HOVER = ("#0052CC", "#00B4D8")
DANGER_COLOR = ("#DC2626", "#E63946")
DANGER_HOVER = ("#B91C1C", "#C1121F")
TEXT_MAIN = ("#111827", "#FFFFFF")
TEXT_SUB = ("#6B7280", "#A0A0B0")

FONT_MAIN = "Inter"

class AppUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Velo - Viral Content Engine")
        self.geometry("1000x800")
        self.minsize(900, 700)
        self.configure(fg_color=BG_COLOR)
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.settings = load_settings()
        self.history = load_history()
        
        # Apply saved theme mode or default to system
        saved_mode = self.settings.get("appearance_mode", "Dark")
        ctk.set_appearance_mode(saved_mode)
        
        self.downloader = VeloDownloader(
            on_progress=self.handle_progress,
            on_success=self.handle_success,
            on_error=self.handle_error,
            on_info_fetched=self.handle_info_fetched
        )
        
        self.current_video_info = None
        self.last_download_path = None
        self.selected_playlist_items = None
        self.playlist_progress_map = {}
        
        self.setup_ui()

    def create_card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color=("#E5E7EB", "#2A2A35"))

    def setup_ui(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=SIDEBAR_COLOR)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)
        
        try:
            logo_img_path = Path(__file__).parent / "static" / "logo.png"
            logo_img_data = Image.open(logo_img_path)
            self.logo_image = ctk.CTkImage(light_image=logo_img_data, dark_image=logo_img_data, size=(40, 40))
            self.logo_label = ctk.CTkLabel(self.sidebar_frame, text=" Velo", image=self.logo_image, compound="left", font=ctk.CTkFont(family=FONT_MAIN, size=24, weight="bold"), text_color=TEXT_MAIN)
        except Exception:
            self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Velo 🚀", font=ctk.CTkFont(family=FONT_MAIN, size=26, weight="bold"), text_color=TEXT_MAIN)
            
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        btn_font = ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold")
        
        def create_nav_btn(text, command, row):
            btn = ctk.CTkButton(self.sidebar_frame, text=text, command=command, font=btn_font,
                                fg_color="transparent", hover_color=CARD_COLOR, anchor="w", 
                                text_color=TEXT_SUB, height=40)
            btn.grid(row=row, column=0, padx=20, pady=5, sticky="ew")
            return btn
            
        self.nav_home_btn = create_nav_btn("Home", self.show_home, 1)
        self.nav_history_btn = create_nav_btn("History", self.show_history, 2)
        self.nav_clipper_btn = create_nav_btn("Clip Maker", self.show_clipper, 3)
        self.nav_playlists_btn = create_nav_btn("Smart Playlists", self.show_playlists, 4)
        self.nav_settings_btn = create_nav_btn("Settings", self.show_settings, 5)
        
        self.reset_app_btn = ctk.CTkButton(self.sidebar_frame, text="Reset Session", command=self.reset_app, 
                                           font=btn_font, fg_color="transparent", hover_color=DANGER_HOVER, 
                                           border_width=1, border_color=DANGER_COLOR, text_color=DANGER_COLOR, height=40)
        self.reset_app_btn.grid(row=6, column=0, padx=20, pady=(40, 10), sticky="ew")
        
        self.appearance_mode_var = ctk.StringVar(value=self.settings.get("appearance_mode", "Dark"))
        self.theme_switch = ctk.CTkSwitch(self.sidebar_frame, text="Dark Mode", command=self.toggle_theme, 
                                          variable=self.appearance_mode_var, onvalue="Dark", offvalue="Light",
                                          progress_color=ACCENT_COLOR, text_color=TEXT_MAIN, font=ctk.CTkFont(family=FONT_MAIN, size=12))
        self.theme_switch.grid(row=7, column=0, padx=20, pady=(20, 0), sticky="s")
        
        import shutil
        ffmpeg_available = shutil.which("ffmpeg") is not None
        
        notice_text = "Only download videos\nyou have rights to."
        notice_color = TEXT_SUB
        if not ffmpeg_available:
            notice_text = "⚠️ FFmpeg is missing!\nAudio extraction & clipping\nwill be unavailable."
            notice_color = ("#DC2626", "#F87171")
            
        self.notice_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text=notice_text,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold" if not ffmpeg_available else "normal"),
            text_color=notice_color,
            justify="center"
        )
        self.notice_label.grid(row=8, column=0, padx=20, pady=20, sticky="s")
        
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=30, pady=30)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)
        
        self.init_home_view()
        self.init_history_view()
        self.init_settings_view()
        self.init_clipper_view()
        self.init_playlists_view()
        
        self.show_home()

    def toggle_theme(self):
        new_mode = self.appearance_mode_var.get()
        ctk.set_appearance_mode(new_mode)
        self.settings["appearance_mode"] = new_mode
        save_settings(self.settings)

    def reset_app(self):
        self.downloader.cancel()
        self.current_video_info = None
        self.last_download_path = None
        self.selected_playlist_items = None
        
        self.url_entry.configure(state="normal")
        self.url_entry.delete(0, 'end')
        self.fetch_btn.configure(state="normal")
        
        self.thumbnail_label.configure(image=None, text="No Video Selected")
        self.title_label.configure(text="Title: -")
        self.channel_label.configure(text="Channel: -")
        self.duration_label.configure(text="Duration: -")
        
        self.status_label.configure(text="Ready", text_color=TEXT_SUB)
        self.progress_bar.set(0)
        self.stats_label.configure(text="0% | 0 MB/s | ETA: 0s")
        
        self.download_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.open_file_btn.pack_forget()
        self.open_folder_btn.pack_forget()
        
        self.show_home()

    def reset_nav_buttons(self):
        for btn in [self.nav_home_btn, self.nav_history_btn, self.nav_clipper_btn, self.nav_playlists_btn, self.nav_settings_btn]:
            btn.configure(fg_color="transparent", text_color=TEXT_SUB)

    def hide_all_views(self):
        self.home_frame.grid_remove()
        self.history_frame.grid_remove()
        self.settings_frame.grid_remove()
        self.clipper_frame.grid_remove()
        if hasattr(self, 'playlists_frame'):
            self.playlists_frame.grid_remove()

    def show_home(self):
        self.hide_all_views()
        self.reset_nav_buttons()
        self.nav_home_btn.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.home_frame.grid(row=0, column=0, sticky="nsew")

    def show_history(self):
        self.hide_all_views()
        self.refresh_history()
        self.reset_nav_buttons()
        self.nav_history_btn.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.history_frame.grid(row=0, column=0, sticky="nsew")

    def show_settings(self):
        self.hide_all_views()
        self.reset_nav_buttons()
        self.nav_settings_btn.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.settings_frame.grid(row=0, column=0, sticky="nsew")

    def show_playlists(self):
        self.hide_all_views()
        self.reset_nav_buttons()
        self.nav_playlists_btn.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.playlists_frame.grid(row=0, column=0, sticky="nsew")
        self.refresh_playlists_list()

    def show_clipper(self):
        self.hide_all_views()
        self.reset_nav_buttons()
        self.nav_clipper_btn.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.clipper_frame.grid(row=0, column=0, sticky="nsew")

    def init_home_view(self):
        self.home_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.home_frame.grid_columnconfigure(0, weight=1)
        self.home_frame.grid_rowconfigure(3, weight=1)
        
        title_font = ctk.CTkFont(family=FONT_MAIN, size=28, weight="bold")
        ctk.CTkLabel(self.home_frame, text="Download Media", font=title_font, text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        self.url_frame = self.create_card(self.home_frame)
        self.url_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        self.url_frame.grid_columnconfigure(0, weight=1)
        
        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="Paste YouTube link here...", 
                                      height=45, font=ctk.CTkFont(family=FONT_MAIN, size=14), border_width=0, fg_color=BG_COLOR, text_color=TEXT_MAIN)
        self.url_entry.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="ew")
        
        self.paste_btn = ctk.CTkButton(self.url_frame, text="Paste", width=80, height=45, command=self.paste_url,
                                       fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN)
        self.paste_btn.grid(row=0, column=1, padx=5, pady=20)
        
        self.fetch_btn = ctk.CTkButton(self.url_frame, text="Fetch Info", width=120, height=45, command=self.start_fetch,
                                       fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"), font=ctk.CTkFont(weight="bold"))
        self.fetch_btn.grid(row=0, column=2, padx=(5, 20), pady=20)
        
        self.info_frame = self.create_card(self.home_frame)
        self.info_frame.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        self.info_frame.grid_columnconfigure(1, weight=1)
        
        self.thumbnail_label = ctk.CTkLabel(self.info_frame, text="No Video Selected", width=200, height=112, 
                                            fg_color=BG_COLOR, corner_radius=10, text_color=TEXT_SUB)
        self.thumbnail_label.grid(row=0, column=0, rowspan=3, padx=20, pady=20)
        
        self.title_label = ctk.CTkLabel(self.info_frame, text="Title: -", font=ctk.CTkFont(family=FONT_MAIN, size=18, weight="bold"), 
                                        text_color=TEXT_MAIN, anchor="w", justify="left", wraplength=400)
        self.title_label.grid(row=0, column=1, sticky="ew", padx=10, pady=(20, 5))
        
        self.channel_label = ctk.CTkLabel(self.info_frame, text="Channel: -", font=ctk.CTkFont(family=FONT_MAIN, size=14), text_color=TEXT_SUB, anchor="w")
        self.channel_label.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        self.duration_label = ctk.CTkLabel(self.info_frame, text="Duration: -", font=ctk.CTkFont(family=FONT_MAIN, size=14), text_color=TEXT_SUB, anchor="w")
        self.duration_label.grid(row=2, column=1, sticky="ew", padx=10, pady=(5, 20))
        
        self.options_frame = self.create_card(self.home_frame)
        self.options_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 20))
        self.options_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.options_frame, text="Format:", font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"), text_color=TEXT_MAIN).grid(row=0, column=0, padx=20, pady=(20,10), sticky="w")
        self.format_var = ctk.StringVar(value=self.settings.get("default_format", "video"))
        self.format_menu = ctk.CTkOptionMenu(self.options_frame, values=["video", "audio"], variable=self.format_var, command=self.on_format_change,
                                             fg_color=BG_COLOR, button_color=SIDEBAR_COLOR, button_hover_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.format_menu.grid(row=0, column=1, padx=10, pady=(20,10), sticky="w")
        
        ctk.CTkLabel(self.options_frame, text="Quality:", font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"), text_color=TEXT_MAIN).grid(row=0, column=2, padx=10, pady=(20,10), sticky="w")
        self.quality_var = ctk.StringVar(value=self.settings.get("default_quality", "best"))
        self.quality_menu = ctk.CTkOptionMenu(self.options_frame, values=["best", "1080p", "720p", "360p"], variable=self.quality_var,
                                              fg_color=BG_COLOR, button_color=SIDEBAR_COLOR, button_hover_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.quality_menu.grid(row=0, column=3, padx=20, pady=(20,10), sticky="w")
        
        ctk.CTkLabel(self.options_frame, text="Save to:", font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"), text_color=TEXT_MAIN).grid(row=1, column=0, padx=20, pady=10, sticky="w")
        self.folder_var = ctk.StringVar(value=self.settings.get("download_folder", str(Path.home() / "Downloads")))
        self.folder_entry = ctk.CTkEntry(self.options_frame, textvariable=self.folder_var, state="readonly", border_width=0, fg_color=BG_COLOR, text_color=TEXT_MAIN)
        self.folder_entry.grid(row=1, column=1, columnspan=2, padx=10, pady=10, sticky="ew")
        
        self.browse_btn = ctk.CTkButton(self.options_frame, text="Browse", width=80, command=self.browse_folder, fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN)
        self.browse_btn.grid(row=1, column=3, padx=20, pady=10, sticky="w")
        
        self.single_video_var = ctk.BooleanVar(value=True)
        self.single_video_checkbox = ctk.CTkCheckBox(self.options_frame, text="Single Video Only (Ignore Playlist)", variable=self.single_video_var, text_color=TEXT_MAIN)
        self.single_video_checkbox.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="w")
        
        self.download_transcript_var = ctk.BooleanVar(value=False)
        self.download_transcript_checkbox = ctk.CTkCheckBox(self.options_frame, text="Download Transcript to MD", variable=self.download_transcript_var, text_color=TEXT_MAIN)
        self.download_transcript_checkbox.grid(row=2, column=2, columnspan=2, padx=10, pady=10, sticky="w")

        self.sponsorblock_var = ctk.BooleanVar(value=False)
        self.sponsorblock_checkbox = ctk.CTkCheckBox(self.options_frame, text="SponsorBlock Ad-Skipping", variable=self.sponsorblock_var, text_color=TEXT_MAIN)
        self.sponsorblock_checkbox.grid(row=3, column=0, columnspan=2, padx=20, pady=10, sticky="w")

        self.embed_metadata_var = ctk.BooleanVar(value=False)
        self.embed_metadata_checkbox = ctk.CTkCheckBox(self.options_frame, text="Embed Cover Art & Metadata", variable=self.embed_metadata_var, text_color=TEXT_MAIN)
        self.embed_metadata_checkbox.grid(row=3, column=2, columnspan=2, padx=10, pady=10, sticky="w")

        self.download_archive_var = ctk.BooleanVar(value=False)
        self.download_archive_checkbox = ctk.CTkCheckBox(self.options_frame, text="Smart Sync (Only download new)", variable=self.download_archive_var, text_color=TEXT_MAIN)
        self.download_archive_checkbox.grid(row=4, column=0, columnspan=2, padx=20, pady=(10, 20), sticky="w")
        
        self.action_frame = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        self.action_frame.grid(row=4, column=0, sticky="sew")
        self.action_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(self.action_frame, text="Ready", text_color=TEXT_SUB, font=ctk.CTkFont(family=FONT_MAIN, size=13))
        self.status_label.grid(row=0, column=0, columnspan=2, pady=(0, 5))
        
        self.progress_bar = ctk.CTkProgressBar(self.action_frame, progress_color=ACCENT_COLOR)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress_bar.set(0)
        
        self.stats_label = ctk.CTkLabel(self.action_frame, text="0% | 0 MB/s | ETA: 0s", font=ctk.CTkFont(family=FONT_MAIN, size=12), text_color=TEXT_SUB)
        self.stats_label.grid(row=2, column=0, columnspan=2, pady=(0, 15))
        
        self.btn_frame = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        self.btn_frame.grid(row=3, column=0, columnspan=2)
        
        self.download_btn = ctk.CTkButton(self.btn_frame, text="Start Download", command=self.start_download, 
                                          fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"), 
                                          font=ctk.CTkFont(size=16, weight="bold"), height=50, width=200)
        self.download_btn.pack(side="left", padx=10)
        
        self.cancel_btn = ctk.CTkButton(self.btn_frame, text="Cancel", command=self.cancel_download, state="disabled", 
                                        fg_color="transparent", hover_color=DANGER_HOVER, text_color=DANGER_COLOR, 
                                        border_width=1, border_color=DANGER_COLOR, height=50, width=120)
        self.cancel_btn.pack(side="left", padx=10)
        
        self.open_file_btn = ctk.CTkButton(self.btn_frame, text="Open File", command=self.open_downloaded_file, state="disabled", fg_color=SIDEBAR_COLOR, text_color=TEXT_MAIN, height=50)
        self.open_folder_btn = ctk.CTkButton(self.btn_frame, text="Open Folder", command=self.open_downloaded_folder, state="disabled", fg_color=SIDEBAR_COLOR, text_color=TEXT_MAIN, height=50)

    def init_clipper_view(self):
        self.clipper_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.clipper_frame.grid_columnconfigure(0, weight=1)
        
        title_font = ctk.CTkFont(family=FONT_MAIN, size=28, weight="bold")
        ctk.CTkLabel(self.clipper_frame, text="Viral Clip Maker", font=title_font, text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        card = self.create_card(self.clipper_frame)
        card.grid(row=1, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        
        label_font = ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold")
        
        ctk.CTkLabel(card, text="Video URL:", font=label_font, text_color=TEXT_MAIN).grid(row=0, column=0, padx=30, pady=(30,10), sticky="w")
        self.clip_url_var = ctk.StringVar()
        ctk.CTkEntry(card, textvariable=self.clip_url_var, height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0).grid(row=0, column=1, padx=(0,30), pady=(30,10), sticky="ew")
        
        time_frame = ctk.CTkFrame(card, fg_color="transparent")
        time_frame.grid(row=1, column=1, padx=(0,30), pady=10, sticky="ew")
        time_frame.grid_columnconfigure(1, weight=1)
        time_frame.grid_columnconfigure(3, weight=1)
        
        ctk.CTkLabel(card, text="Trim (Seconds):", font=label_font, text_color=TEXT_MAIN).grid(row=1, column=0, padx=30, pady=10, sticky="w")
        ctk.CTkLabel(time_frame, text="Start:", text_color=TEXT_MAIN).grid(row=0, column=0, padx=(0,10))
        self.clip_start_var = ctk.StringVar()
        ctk.CTkEntry(time_frame, textvariable=self.clip_start_var, height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0).grid(row=0, column=1, sticky="ew")
        
        ctk.CTkLabel(time_frame, text="End:", text_color=TEXT_MAIN).grid(row=0, column=2, padx=10)
        self.clip_end_var = ctk.StringVar()
        ctk.CTkEntry(time_frame, textvariable=self.clip_end_var, height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0).grid(row=0, column=3, sticky="ew")
        
        ctk.CTkLabel(card, text="Top Text:", font=label_font, text_color=TEXT_MAIN).grid(row=2, column=0, padx=30, pady=10, sticky="w")
        self.clip_top_var = ctk.StringVar()
        ctk.CTkEntry(card, textvariable=self.clip_top_var, height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0).grid(row=2, column=1, padx=(0,30), pady=10, sticky="ew")
        
        ctk.CTkLabel(card, text="Bottom Text:", font=label_font, text_color=TEXT_MAIN).grid(row=3, column=0, padx=30, pady=10, sticky="w")
        self.clip_bottom_var = ctk.StringVar()
        ctk.CTkEntry(card, textvariable=self.clip_bottom_var, height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0).grid(row=3, column=1, padx=(0,30), pady=10, sticky="ew")
        
        ctk.CTkLabel(card, text="Export Format:", font=label_font, text_color=TEXT_MAIN).grid(row=4, column=0, padx=30, pady=(10,30), sticky="w")
        self.clip_format_var = ctk.StringVar(value="Short (9:16 MP4)")
        ctk.CTkOptionMenu(card, values=["Short (9:16 MP4)", "Meme GIF", "Standard Clip"], variable=self.clip_format_var,
                          height=45, fg_color=BG_COLOR, button_color=SIDEBAR_COLOR, button_hover_color=CARD_COLOR, text_color=TEXT_MAIN).grid(row=4, column=1, padx=(0,30), pady=(10,30), sticky="w")
        
        self.clip_btn = ctk.CTkButton(self.clipper_frame, text="Generate Clip 🔥", command=self.generate_clip,
                                      height=60, font=ctk.CTkFont(size=18, weight="bold"),
                                      fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"))
        self.clip_btn.grid(row=2, column=0, pady=30, sticky="ew")
        
        self.clip_status_label = ctk.CTkLabel(self.clipper_frame, text="Ready", text_color=TEXT_SUB, font=ctk.CTkFont(size=14))
        self.clip_status_label.grid(row=3, column=0)

    def init_history_view(self):
        self.history_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.history_frame.grid_columnconfigure(0, weight=1)
        self.history_frame.grid_rowconfigure(1, weight=1)
        
        title_font = ctk.CTkFont(family=FONT_MAIN, size=28, weight="bold")
        ctk.CTkLabel(self.history_frame, text="Download History", font=title_font, text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        self.history_scroll = ctk.CTkScrollableFrame(self.history_frame, fg_color="transparent")
        self.history_scroll.grid(row=1, column=0, sticky="nsew")

    def refresh_history(self):
        for widget in self.history_scroll.winfo_children():
            widget.destroy()
            
        self.history = load_history()
        
        if not self.history:
            ctk.CTkLabel(self.history_scroll, text="No download history yet.", text_color=TEXT_SUB).pack(pady=40)
            return
            
        for item in self.history:
            card = self.create_card(self.history_scroll)
            card.pack(fill="x", pady=5, padx=5)
            card.grid_columnconfigure(0, weight=1)
            
            title = ctk.CTkLabel(card, text=item.get("title", "Unknown"), font=ctk.CTkFont(family=FONT_MAIN, weight="bold", size=14), text_color=TEXT_MAIN, anchor="w")
            title.grid(row=0, column=0, sticky="w", padx=20, pady=(15, 5))
            
            detail = ctk.CTkLabel(card, text=f"{item.get('channel', '')} | {item.get('timestamp', '')[:10]}", font=ctk.CTkFont(family=FONT_MAIN, size=12), text_color=TEXT_SUB, anchor="w")
            detail.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 15))
            
            btn = ctk.CTkButton(card, text="Open File", width=100, height=35, command=lambda p=item.get('filepath'): open_file(p),
                                fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN)
            btn.grid(row=0, column=1, rowspan=2, padx=20, pady=15)

    def init_settings_view(self):
        self.settings_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.settings_frame.grid_columnconfigure(0, weight=1)
        
        title_font = ctk.CTkFont(family=FONT_MAIN, size=28, weight="bold")
        ctk.CTkLabel(self.settings_frame, text="Settings", font=title_font, text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        card = self.create_card(self.settings_frame)
        card.grid(row=1, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(card, text="Default Download Folder:", font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"), text_color=TEXT_MAIN).grid(row=0, column=0, padx=30, pady=30, sticky="w")
        self.settings_folder_var = ctk.StringVar(value=self.settings.get("download_folder", ""))
        ctk.CTkEntry(card, textvariable=self.settings_folder_var, state="readonly", height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0).grid(row=0, column=1, padx=(0,10), pady=30, sticky="ew")
        ctk.CTkButton(card, text="Change", width=100, height=45, command=self.change_default_folder, fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN).grid(row=0, column=2, padx=(0,30), pady=30)

    def init_playlists_view(self):
        self.playlists_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.playlists_frame.grid_columnconfigure(0, weight=1)
        self.playlists_frame.grid_rowconfigure(3, weight=1)
        
        title_font = ctk.CTkFont(family=FONT_MAIN, size=28, weight="bold")
        ctk.CTkLabel(self.playlists_frame, text="Smart Playlists", font=title_font, text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        # 1. Top Panel: Installer Form
        installer_card = self.create_card(self.playlists_frame)
        installer_card.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        installer_card.grid_columnconfigure(1, weight=1)
        
        label_font = ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold")
        
        # Playlist URL entry row
        ctk.CTkLabel(installer_card, text="Playlist URL:", font=label_font, text_color=TEXT_MAIN).grid(row=0, column=0, padx=30, pady=(25, 10), sticky="w")
        self.pl_url_var = ctk.StringVar()
        self.pl_url_entry = ctk.CTkEntry(installer_card, textvariable=self.pl_url_var, placeholder_text="Paste YouTube playlist URL here...", height=45, fg_color=BG_COLOR, text_color=TEXT_MAIN, border_width=0)
        self.pl_url_entry.grid(row=0, column=1, padx=(0, 10), pady=(25, 10), sticky="ew")
        
        self.pl_install_btn = ctk.CTkButton(installer_card, text="Install Playlist", width=140, height=45, command=self.install_playlist,
                                            fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"), font=ctk.CTkFont(weight="bold"))
        self.pl_install_btn.grid(row=0, column=2, padx=(0, 30), pady=(25, 10))
        
        # Options row frame
        options_subframe = ctk.CTkFrame(installer_card, fg_color="transparent")
        options_subframe.grid(row=1, column=0, columnspan=3, padx=30, pady=(10, 25), sticky="ew")
        options_subframe.grid_columnconfigure((1, 3), weight=1)
        
        ctk.CTkLabel(options_subframe, text="Format:", font=label_font, text_color=TEXT_MAIN).grid(row=0, column=0, padx=(0, 10), pady=10, sticky="w")
        self.pl_format_var = ctk.StringVar(value="video")
        self.pl_format_menu = ctk.CTkOptionMenu(options_subframe, values=["video", "audio"], variable=self.pl_format_var, command=self.on_pl_format_change,
                                                fg_color=BG_COLOR, button_color=SIDEBAR_COLOR, button_hover_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.pl_format_menu.grid(row=0, column=1, padx=(0, 20), pady=10, sticky="w")
        
        ctk.CTkLabel(options_subframe, text="Quality:", font=label_font, text_color=TEXT_MAIN).grid(row=0, column=2, padx=10, pady=10, sticky="w")
        self.pl_quality_var = ctk.StringVar(value="best")
        self.pl_quality_menu = ctk.CTkOptionMenu(options_subframe, values=["best", "1080p", "720p", "480p", "360p"], variable=self.pl_quality_var,
                                                 fg_color=BG_COLOR, button_color=SIDEBAR_COLOR, button_hover_color=CARD_COLOR, text_color=TEXT_MAIN)
        self.pl_quality_menu.grid(row=0, column=3, padx=(0, 20), pady=10, sticky="w")
        
        self.pl_sponsorblock_var = ctk.BooleanVar(value=False)
        self.pl_sponsorblock_cb = ctk.CTkCheckBox(options_subframe, text="SponsorBlock", variable=self.pl_sponsorblock_var, font=ctk.CTkFont(size=12), text_color=TEXT_MAIN)
        self.pl_sponsorblock_cb.grid(row=0, column=4, padx=10, pady=10, sticky="w")
        
        self.pl_metadata_var = ctk.BooleanVar(value=False)
        self.pl_metadata_cb = ctk.CTkCheckBox(options_subframe, text="Embed Metadata", variable=self.pl_metadata_var, font=ctk.CTkFont(size=12), text_color=TEXT_MAIN)
        self.pl_metadata_cb.grid(row=0, column=5, padx=10, pady=10, sticky="w")

        # 2. Sync All & Stats Header
        header_frame = ctk.CTkFrame(self.playlists_frame, fg_color="transparent")
        header_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)
        
        self.playlists_count_label = ctk.CTkLabel(header_frame, text="Your Playlists (0)", font=ctk.CTkFont(family=FONT_MAIN, size=18, weight="bold"), text_color=TEXT_MAIN)
        self.playlists_count_label.grid(row=0, column=0, sticky="w")
        
        self.sync_all_btn = ctk.CTkButton(header_frame, text="Sync All", width=120, command=self.sync_all_playlists,
                                          fg_color=SIDEBAR_COLOR, hover_color=CARD_COLOR, text_color=TEXT_MAIN, font=ctk.CTkFont(weight="bold"))
        self.sync_all_btn.grid(row=0, column=1)

        # 3. Bottom Panel: Scrollable container for Playlists Grid/List
        self.playlists_scroll = ctk.CTkScrollableFrame(self.playlists_frame, fg_color="transparent")
        self.playlists_scroll.grid(row=3, column=0, sticky="nsew", pady=(0, 10))

        # Sync Worker Queue Setup
        import queue
        self.playlist_sync_queue = queue.Queue()
        self.is_playlist_syncing = False
        self.playlist_syncing_thread = None
        self.active_sync_id = None

    def on_pl_format_change(self, choice):
        if choice == "audio":
            self.pl_quality_menu.configure(state="disabled")
        else:
            self.pl_quality_menu.configure(state="normal")

    def install_playlist(self):
        url = self.pl_url_var.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a playlist URL.")
            return
            
        self.pl_install_btn.configure(state="disabled")
        self.pl_url_entry.configure(state="disabled")
        
        def worker():
            try:
                import yt_dlp
                # Fetch full flat entries list
                ydl_opts = {
                    'extract_flat': True,
                    'skip_download': True,
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                if not info or ('entries' not in info and info.get('_type') != 'playlist'):
                    raise Exception("Provided link is not a valid playlist.")
                    
                entries = info.get('entries', [])
                if not entries:
                    raise Exception("No videos found in this playlist.")
                    
                # Show popup selector to choose videos!
                self.after(0, lambda: self.show_playlist_install_selector(info, entries))
                
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Could not load playlist: {e}"))
                self.after(0, self.reset_pl_install_ui)
                
        threading.Thread(target=worker, daemon=True).start()

    def show_playlist_install_selector(self, info, entries):
        selector = ctk.CTkToplevel(self)
        selector.title("Select Videos to Install")
        selector.geometry("600x650")
        selector.transient(self)
        selector.grab_set()
        
        selector.configure(fg_color=BG_COLOR)
        
        title_font = ctk.CTkFont(family=FONT_MAIN, size=18, weight="bold")
        sub_font = ctk.CTkFont(family=FONT_MAIN, size=12)
        
        header_frame = ctk.CTkFrame(selector, fg_color="transparent")
        header_frame.pack(fill="x", padx=25, pady=(20, 10))
        
        title_text = info.get('title') or "Select Videos"
        uploader_text = info.get('uploader') or info.get('uploader_id') or "Unknown Channel"
        
        ctk.CTkLabel(header_frame, text=title_text, font=title_font, text_color=TEXT_MAIN, anchor="w", justify="left").pack(fill="x")
        ctk.CTkLabel(header_frame, text=f"{uploader_text} • Choose which videos to download and sync", font=sub_font, text_color=TEXT_SUB, anchor="w").pack(fill="x", pady=(2, 0))
        
        toolbar = ctk.CTkFrame(selector, fg_color="transparent")
        toolbar.pack(fill="x", padx=25, pady=5)
        
        selected_count_label = ctk.CTkLabel(toolbar, text=f"Selected: {len(entries)} / {len(entries)}", font=ctk.CTkFont(family=FONT_MAIN, weight="bold", size=12), text_color=TEXT_MAIN)
        selected_count_label.pack(side="left")
        
        checkbox_vars = {}
        
        def update_count():
            count = sum(1 for v in checkbox_vars.values() if v.get())
            selected_count_label.configure(text=f"Selected: {count} / {len(entries)}")
            
        def select_all():
            for var in checkbox_vars.values():
                var.set(True)
            update_count()
            
        def select_none():
            for var in checkbox_vars.values():
                var.set(False)
            update_count()
            
        ctk.CTkButton(toolbar, text="Clear All", width=80, height=26, fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN, command=select_none).pack(side="right", padx=5)
        ctk.CTkButton(toolbar, text="Select All", width=80, height=26, fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN, command=select_all).pack(side="right")
        
        list_scroll = ctk.CTkScrollableFrame(selector, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color=BORDER_COLOR)
        list_scroll.pack(fill="both", expand=True, padx=25, pady=10)
        
        for idx, entry in enumerate(entries):
            var = ctk.BooleanVar(value=True)
            checkbox_vars[idx + 1] = var
            
            entry_title = entry.get('title') or f"Video {idx + 1}"
            
            item_cb = ctk.CTkCheckBox(
                list_scroll, 
                text=f"{idx + 1}. {entry_title}", 
                variable=var, 
                font=ctk.CTkFont(size=13), 
                text_color=TEXT_MAIN,
                command=update_count
            )
            item_cb.pack(fill="x", padx=15, pady=8, anchor="w")
            
        actions = ctk.CTkFrame(selector, fg_color="transparent")
        actions.pack(fill="x", padx=25, pady=20)
        
        def confirm():
            selected_indices = [idx for idx, var in checkbox_vars.items() if var.get()]
            if not selected_indices:
                messagebox.showwarning("Warning", "Please select at least one video to track.")
                return
                
            selector.destroy()
            
            title = info.get('title') or "YouTube Playlist"
            uploader = info.get('uploader') or info.get('uploader_id') or "Unknown"
            url = info.get('original_url') or info.get('webpage_url') or self.pl_url_var.get().strip()
            
            import re
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()
            safe_title = re.sub(r'\s+', '_', safe_title)
            
            base_folder = Path(self.settings.get("download_folder", str(Path.home() / "Downloads")))
            playlist_folder = base_folder / safe_title
            playlist_folder.mkdir(parents=True, exist_ok=True)
            
            playlists = load_playlists()
            playlist_id = info.get('id') or safe_title
            
            if any(p["id"] == playlist_id for p in playlists):
                messagebox.showinfo("Info", "Playlist is already installed!")
                self.reset_pl_install_ui()
                return
                
            sorted_items = ",".join(str(i) for i in sorted(selected_indices))
            
            new_playlist = {
                "id": playlist_id,
                "title": title,
                "uploader": uploader,
                "url": url,
                "format": self.pl_format_var.get(),
                "quality": self.pl_quality_var.get(),
                "download_transcript": False,
                "sponsorblock": self.pl_sponsorblock_var.get(),
                "embed_metadata": self.pl_metadata_var.get(),
                "download_folder": str(playlist_folder),
                "total_count": len(selected_indices),
                "downloaded_count": 0,
                "playlist_items": sorted_items,
                "last_sync": "Never",
                "status": "idle"
            }
            
            playlists.append(new_playlist)
            save_playlists(playlists)
            
            messagebox.showinfo("Success", f"Installed Playlist: {title}")
            self.pl_url_var.set("")
            self.refresh_playlists_list()
            self.reset_pl_install_ui()
            
        def cancel():
            selector.destroy()
            self.reset_pl_install_ui()
            
        ctk.CTkButton(actions, text="Cancel", width=120, height=40, fg_color="transparent", hover_color=DANGER_HOVER, border_width=1, border_color=DANGER_COLOR, text_color=DANGER_COLOR, command=cancel).pack(side="left")
        ctk.CTkButton(actions, text="Confirm & Install", width=160, height=40, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"), font=ctk.CTkFont(weight="bold"), command=confirm).pack(side="right")

    def reset_pl_install_ui(self):
        self.pl_install_btn.configure(state="normal")
        self.pl_url_entry.configure(state="normal")

    def refresh_playlists_list(self):
        for widget in self.playlists_scroll.winfo_children():
            widget.destroy()
            
        playlists = load_playlists()
        self.playlists_count_label.configure(text=f"Your Playlists ({len(playlists)})")
        
        if not playlists:
            ctk.CTkLabel(self.playlists_scroll, text="No playlists installed yet.\nPaste a playlist URL above to subscribe.", text_color=TEXT_SUB, font=ctk.CTkFont(size=14)).pack(pady=50)
            return
            
        for pl in playlists:
            card = self.create_card(self.playlists_scroll)
            card.pack(fill="x", pady=8, padx=5)
            card.grid_columnconfigure(0, weight=1)
            
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=15)
            info_frame.grid_columnconfigure(0, weight=1)
            
            # Status tag & details
            badge_text = pl.get("status", "idle").upper()
            badge_color = ACCENT_COLOR if badge_text == "SYNCING" else DANGER_COLOR if badge_text == "ERROR" else TEXT_SUB
            
            badges_subframe = ctk.CTkFrame(info_frame, fg_color="transparent")
            badges_subframe.grid(row=0, column=0, sticky="w", pady=(0, 5))
            
            status_lbl = ctk.CTkLabel(badges_subframe, text=f" {badge_text} ", fg_color=badge_color, text_color="#FFFFFF" if badge_text in ("SYNCING", "ERROR") else TEXT_MAIN, font=ctk.CTkFont(size=10, weight="bold"), corner_radius=5)
            status_lbl.pack(side="left", padx=(0, 10))
            
            fmt_lbl = ctk.CTkLabel(badges_subframe, text=f" {pl.get('format', 'video').upper()} ", fg_color=SIDEBAR_COLOR, text_color=TEXT_MAIN, font=ctk.CTkFont(size=10, weight="bold"), corner_radius=5)
            fmt_lbl.pack(side="left", padx=5)
            
            q_lbl = ctk.CTkLabel(badges_subframe, text=f" {pl.get('quality', 'best').upper()} ", fg_color=SIDEBAR_COLOR, text_color=TEXT_MAIN, font=ctk.CTkFont(size=10, weight="bold"), corner_radius=5)
            q_lbl.pack(side="left", padx=5)
            
            title_lbl = ctk.CTkLabel(info_frame, text=pl.get("title", "YouTube Playlist"), font=ctk.CTkFont(family=FONT_MAIN, weight="bold", size=16), text_color=TEXT_MAIN, anchor="w", justify="left")
            title_lbl.grid(row=1, column=0, sticky="w", pady=(5, 2))
            
            uploader_lbl = ctk.CTkLabel(info_frame, text=pl.get("uploader", "Unknown"), font=ctk.CTkFont(family=FONT_MAIN, size=12), text_color=TEXT_SUB, anchor="w")
            uploader_lbl.grid(row=2, column=0, sticky="w", pady=(0, 10))
            
            # Progress bar
            dl = pl.get("downloaded_count", 0)
            tot = pl.get("total_count", 0)
            percent = dl / tot if tot else 0
            
            prog_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            prog_frame.grid(row=3, column=0, sticky="ew", pady=5)
            prog_frame.grid_columnconfigure(0, weight=1)
            
            prog_bar = ctk.CTkProgressBar(prog_frame, progress_color=ACCENT_COLOR)
            prog_bar.grid(row=0, column=0, sticky="ew", padx=(0, 15))
            prog_bar.set(percent)
            
            prog_lbl = ctk.CTkLabel(prog_frame, text=f"{dl} / {tot}", font=ctk.CTkFont(family=FONT_MAIN, weight="bold", size=12), text_color=TEXT_MAIN)
            prog_lbl.grid(row=0, column=1, sticky="e")
            
            # Real-time status update from progress map
            pid = pl["id"]
            if pid in self.playlist_progress_map:
                pm = self.playlist_progress_map[pid]
                status_lbl.configure(text=" SYNCING ")
                prog_lbl.configure(text=f"{pm['percent']} ({dl}/{tot})")
                meta_text = f"Status: {pm['message']}  |  Folder: {pl.get('download_folder', '')}"
            else:
                meta_text = f"Synced: {pl.get('last_sync', 'Never')}  |  Folder: {pl.get('download_folder', '')}"
                
            meta_lbl = ctk.CTkLabel(info_frame, text=meta_text, font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_SUB, anchor="w")
            meta_lbl.grid(row=4, column=0, sticky="w", pady=(5, 0))
            
            # Right actions
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.grid(row=0, column=1, sticky="ns", padx=20, pady=15)
            
            sync_btn_text = "Sync Now" if pl.get("status") != "syncing" else "Syncing..."
            sync_btn_state = "disabled" if pl.get("status") == "syncing" else "normal"
            sync_btn = ctk.CTkButton(btn_frame, text=sync_btn_text, state=sync_btn_state, width=110, height=35, command=lambda pid=pl["id"]: self.sync_single_playlist(pid),
                                     fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"), font=ctk.CTkFont(weight="bold"))
            sync_btn.pack(pady=5)
            
            fold_btn = ctk.CTkButton(btn_frame, text="Folder", width=110, height=35, command=lambda path=pl["download_folder"]: open_folder(path),
                                     fg_color=SIDEBAR_COLOR, hover_color=BG_COLOR, text_color=TEXT_MAIN)
            fold_btn.pack(pady=5)
            
            delete_btn = ctk.CTkButton(btn_frame, text="Uninstall", state=sync_btn_state, width=110, height=35, command=lambda pid=pl["id"]: self.uninstall_playlist(pid),
                                       fg_color="transparent", hover_color=DANGER_HOVER, border_width=1, border_color=DANGER_COLOR, text_color=DANGER_COLOR)
            delete_btn.pack(pady=5)

    def sync_single_playlist(self, playlist_id):
        self.playlist_sync_queue.put(playlist_id)
        self.start_playlist_sync_worker()
        messagebox.showinfo("Queued", "Playlist queued for sequential sync!")
        self.refresh_playlists_list()

    def sync_all_playlists(self):
        playlists = load_playlists()
        if not playlists:
            return
        for pl in playlists:
            self.playlist_sync_queue.put(pl["id"])
        self.start_playlist_sync_worker()
        messagebox.showinfo("Queued", "All playlists queued for sync!")
        self.refresh_playlists_list()

    def start_playlist_sync_worker(self):
        if not self.is_playlist_syncing:
            self.is_playlist_syncing = True
            self.playlist_syncing_thread = threading.Thread(target=self.playlist_sync_worker, daemon=True)
            self.playlist_syncing_thread.start()

    def playlist_sync_worker(self):
        while not self.playlist_sync_queue.empty():
            playlist_id = self.playlist_sync_queue.get()
            self.active_sync_id = playlist_id
            try:
                self.run_playlist_sync(playlist_id)
            except Exception as e:
                print(f"Error syncing playlist {playlist_id} in GUI: {e}")
            finally:
                self.playlist_sync_queue.task_done()
                
        self.is_playlist_syncing = False
        self.active_sync_id = None
        self.after(0, self.refresh_playlists_list)

    def run_playlist_sync(self, playlist_id):
        playlists = load_playlists()
        target_pl = None
        for pl in playlists:
            if pl["id"] == playlist_id:
                pl["status"] = "syncing"
                target_pl = pl
                break
                
        if not target_pl:
            return
            
        save_playlists(playlists)
        self.after(0, self.refresh_playlists_list)
        
        event = threading.Event()
        
        def c_prog(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                dl = d.get('downloaded_bytes', 0)
                percent = (dl / total) * 100 if total else 0
                
                pl_index = d.get('playlist_index')
                pl_count = d.get('playlist_count')
                video_title = d.get('info_dict', {}).get('title', 'Video')
                
                msg = f"Downloading: {video_title}"
                if pl_index and pl_count:
                    msg = f"Downloading {pl_index}/{pl_count}: {video_title}"
                    
                self.playlist_progress_map[playlist_id] = {
                    'percent': f"{percent:.1f}%",
                    'message': msg
                }
                self.after(0, self.refresh_playlists_list)
                
        def c_succ(filepath, info):
            print(f"Synced item successfully: {info.get('title')}")
            
        def c_err(msg):
            print(f"Error syncing item: {msg}")
            
        sync_dl = VeloDownloader(on_progress=c_prog, on_success=c_succ, on_error=c_err)
        
        def on_sync_finished(filepath, info):
            folder = Path(target_pl["download_folder"])
            archive_file = folder / "velo_archive.txt"
            dl_count = 0
            if archive_file.exists():
                try:
                    dl_count = len(archive_file.read_text(encoding='utf-8').splitlines())
                except Exception:
                    pass
                    
            from datetime import datetime
            current_playlists = load_playlists()
            for pl in current_playlists:
                if pl["id"] == playlist_id:
                    pl["status"] = "idle"
                    pl["last_sync"] = datetime.now().isoformat(timespec="seconds").split("T")[0] + " " + datetime.now().isoformat(timespec="seconds").split("T")[1][:5]
                    pl["downloaded_count"] = dl_count
                    pl["total_count"] = info.get('playlist_count') or len(info.get('entries', [])) or pl["total_count"]
                    break
            save_playlists(current_playlists)
            
            if playlist_id in self.playlist_progress_map:
                del self.playlist_progress_map[playlist_id]
                
            self.after(0, self.refresh_playlists_list)
            event.set()
            
        def on_sync_failed(msg):
            current_playlists = load_playlists()
            for pl in current_playlists:
                if pl["id"] == playlist_id:
                    pl["status"] = "error"
                    break
            save_playlists(current_playlists)
            
            if playlist_id in self.playlist_progress_map:
                del self.playlist_progress_map[playlist_id]
                
            self.after(0, self.refresh_playlists_list)
            self.after(0, lambda: messagebox.showerror("Sync Error", f"Sync failed for {target_pl['title']}: {msg}"))
            event.set()
            
        sync_dl.on_success = on_sync_finished
        sync_dl.on_error = on_sync_failed
        
        threading.Thread(
            target=sync_dl.download,
            args=(target_pl["url"], target_pl["download_folder"]),
            kwargs={
                'format_type': target_pl["format"],
                'quality': target_pl["quality"],
                'single_video': False,
                'sponsorblock': target_pl["sponsorblock"],
                'embed_metadata': target_pl["embed_metadata"],
                'download_archive': True,
                'playlist_items': target_pl.get("playlist_items")
            },
            daemon=True
        ).start()
        
        event.wait()

    def uninstall_playlist(self, playlist_id):
        playlists = load_playlists()
        target_pl = None
        for pl in playlists:
            if pl["id"] == playlist_id:
                target_pl = pl
                break
                
        if not target_pl:
            return
            
        confirm = messagebox.askyesnocancel(
            "Uninstall Playlist", 
            f"Are you sure you want to remove '{target_pl['title']}'?\n\nClick Yes to remove playlist tracking and delete all downloaded files.\nClick No to remove tracking but keep the downloaded files.\nClick Cancel to do nothing.",
            icon='warning'
        )
        
        if confirm is None:
            return
            
        new_playlists = [p for p in playlists if p["id"] != playlist_id]
        save_playlists(new_playlists)
        
        if confirm is True:
            import shutil
            folder_path = Path(target_pl["download_folder"])
            if folder_path.exists():
                try:
                    shutil.rmtree(folder_path)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not delete download folder: {e}")
                    
        messagebox.showinfo("Success", "Playlist uninstalled successfully.")
        self.refresh_playlists_list()

    def paste_url(self):
        try:
            clipboard = self.clipboard_get()
            self.url_entry.delete(0, 'end')
            self.url_entry.insert(0, clipboard)
        except Exception:
            pass

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)

    def change_default_folder(self):
        folder = filedialog.askdirectory(initialdir=self.settings_folder_var.get())
        if folder:
            self.settings_folder_var.set(folder)
            self.settings["download_folder"] = folder
            save_settings(self.settings)
            self.folder_var.set(folder)

    def on_format_change(self, choice):
        if choice == "audio":
            self.quality_menu.configure(state="disabled")
        else:
            self.quality_menu.configure(state="normal")

    def format_time(self, seconds):
        if not seconds:
            return "Unknown"
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def start_fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a YouTube URL.")
            return
            
        self.fetch_btn.configure(state="disabled")
        self.status_label.configure(text="Fetching video info...", text_color=ACCENT_COLOR)
        self.current_video_info = None
        
        self.thumbnail_label.configure(image=None, text="Loading...")
        self.title_label.configure(text="Title: -")
        self.channel_label.configure(text="Channel: -")
        self.duration_label.configure(text="Duration: -")
        self.open_file_btn.pack_forget()
        self.open_folder_btn.pack_forget()
        
        single_video = self.single_video_var.get() if hasattr(self, 'single_video_var') else True
        self.downloader.fetch_info(url, single_video=single_video)

    def handle_info_fetched(self, info):
        self.current_video_info = info
        self.selected_playlist_items = None
        
        is_playlist = info.get('_type') == 'playlist' or 'entries' in info
        
        if is_playlist:
            entries = info.get('entries', [])
            title = info.get('title', 'Unknown Playlist')
            channel = info.get('uploader', 'Unknown Channel')
            
            quality_options = ["best", "1080p", "720p", "480p", "360p"]
            
            if len(title) > 60:
                title = title[:57] + "..."
                
            def update_ui_playlist():
                self.title_label.configure(text=f"{title}")
                self.channel_label.configure(text=f"{channel}")
                self.duration_label.configure(text=f"{len(entries)} videos")
                self.status_label.configure(text="Playlist info fetched successfully.", text_color=("#10B981", "#00FF88"))
                self.fetch_btn.configure(state="normal")
                
                self.quality_menu.configure(values=quality_options)
                default_q = self.settings.get("default_quality", "best")
                if default_q in quality_options:
                    self.quality_var.set(default_q)
                else:
                    self.quality_var.set("best")
                    
                self.thumbnail_label.configure(text="Playlist", image=None)
                
                self.show_playlist_selector(entries)
                
            self.after(0, update_ui_playlist)
            return

        formats = info.get('formats', [])
        available_heights = set()
        for f in formats:
            h = f.get('height')
            if h and h > 0:
                available_heights.add(h)
        
        sorted_heights = sorted(list(available_heights), reverse=True)
        quality_options = [f"{h}p" for h in sorted_heights]
        
        if not quality_options:
            quality_options = ["best"]
        else:
            if "best" not in quality_options:
                quality_options.insert(0, "best")

        title = info.get('title', 'Unknown Title')
        if len(title) > 60:
            title = title[:57] + "..."
            
        def update_ui():
            self.title_label.configure(text=f"{title}")
            self.channel_label.configure(text=f"{info.get('uploader', 'Unknown')}")
            self.duration_label.configure(text=f"{self.format_time(info.get('duration'))}")
            self.status_label.configure(text="Info fetched successfully. Ready to download.", text_color=("#10B981", "#00FF88"))
            self.fetch_btn.configure(state="normal")
            
            self.quality_menu.configure(values=quality_options)
            
            default_q = self.settings.get("default_quality", "best")
            if default_q in quality_options:
                self.quality_var.set(default_q)
            else:
                self.quality_var.set("best")

            thumb_url = info.get('thumbnail')
            if thumb_url:
                threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()
            else:
                self.thumbnail_label.configure(text="No Thumbnail")

        self.after(0, update_ui)

    def show_playlist_selector(self, entries):
        self.selector_window = ctk.CTkToplevel(self)
        self.selector_window.title("Select Playlist Videos")
        self.selector_window.geometry("600x700")
        self.selector_window.configure(fg_color=BG_COLOR)
        self.selector_window.grab_set() 
        
        ctk.CTkLabel(self.selector_window, text="Select Videos", text_color=TEXT_MAIN, font=ctk.CTkFont(family=FONT_MAIN, size=24, weight="bold")).pack(pady=(20,10))
        
        btn_frame = ctk.CTkFrame(self.selector_window, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)
        
        self.playlist_vars = []
        
        def select_all():
            for v in self.playlist_vars: v.set(True)
        def deselect_all():
            for v in self.playlist_vars: v.set(False)
            
        ctk.CTkButton(btn_frame, text="Select All", width=120, height=35, command=select_all, fg_color=SIDEBAR_COLOR, text_color=TEXT_MAIN).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Deselect All", width=120, height=35, command=deselect_all, fg_color=SIDEBAR_COLOR, text_color=TEXT_MAIN).pack(side="left", padx=5)
        
        scroll_frame = ctk.CTkScrollableFrame(self.selector_window, fg_color=CARD_COLOR, corner_radius=10)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        for idx, entry in enumerate(entries):
            var = ctk.BooleanVar(value=True)
            self.playlist_vars.append(var)
            title = entry.get('title', f"Video {idx+1}")
            cb = ctk.CTkCheckBox(scroll_frame, text=f"{idx+1}. {title}", variable=var, font=ctk.CTkFont(family=FONT_MAIN, size=13), text_color=TEXT_MAIN)
            cb.pack(fill="x", pady=8, padx=10, anchor="w")
            
        def confirm_selection():
            selected_indices = []
            for idx, var in enumerate(self.playlist_vars):
                if var.get():
                    selected_indices.append(str(idx + 1))
            
            if not selected_indices:
                messagebox.showwarning("Warning", "No videos selected!")
                return
                
            self.selected_playlist_items = ",".join(selected_indices)
            self.selector_window.destroy()
            
        ctk.CTkButton(self.selector_window, text="Confirm Selection", command=confirm_selection, 
                      height=50, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=("#FFFFFF", "#000000"), font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=20)

    def _load_thumbnail(self, url):
        img = fetch_thumbnail(url)
        if img:
            img.thumbnail((200, 112))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(200, 112))
            self.after(0, lambda: self.thumbnail_label.configure(image=ctk_img, text=""))
        else:
            self.after(0, lambda: self.thumbnail_label.configure(text="Failed to load thumbnail"))

    def start_download(self):
        url = self.url_entry.get().strip()
        folder = self.folder_var.get()
        fmt = self.format_var.get()
        quality = self.quality_var.get()
        single_video = self.single_video_var.get() if hasattr(self, 'single_video_var') else True
        download_transcript = self.download_transcript_var.get() if hasattr(self, 'download_transcript_var') else False
        sponsorblock = self.sponsorblock_var.get() if hasattr(self, 'sponsorblock_var') else False
        embed_metadata = self.embed_metadata_var.get() if hasattr(self, 'embed_metadata_var') else False
        download_archive = self.download_archive_var.get() if hasattr(self, 'download_archive_var') else False
        
        if not url:
            messagebox.showwarning("Warning", "Please enter a URL first.")
            return
            
        if not Path(folder).exists():
            messagebox.showerror("Error", "Selected folder does not exist.")
            return
            
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.fetch_btn.configure(state="disabled")
        self.url_entry.configure(state="disabled")
        
        self.progress_bar.set(0)
        self.stats_label.configure(text="Starting download...")
        self.status_label.configure(text="Downloading...", text_color=ACCENT_COLOR)
        
        self.open_file_btn.pack_forget()
        self.open_folder_btn.pack_forget()
        
        self.downloader.download(
            url, folder, fmt, quality, 
            single_video=single_video, 
            playlist_items=self.selected_playlist_items, 
            download_transcript=download_transcript,
            sponsorblock=sponsorblock,
            embed_metadata=embed_metadata,
            download_archive=download_archive
        )

    def cancel_download(self):
        self.downloader.cancel()
        self.status_label.configure(text="Cancelling...", text_color=("#D97706", "#FFB300"))
        self.cancel_btn.configure(state="disabled")

    def handle_progress(self, d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            if total > 0:
                percent = downloaded / total
                percent_str = f"{percent * 100:.1f}%"
            else:
                percent = 0
                percent_str = "N/A"
                
            speed_mb = speed / 1024 / 1024 if speed else 0
            
            def update_ui():
                self.progress_bar.set(percent)
                self.stats_label.configure(text=f"{percent_str} | {speed_mb:.2f} MB/s | ETA: {self.format_time(eta)}")
                
            self.after(0, update_ui)
            
        elif d['status'] == 'finished':
            self.after(0, lambda: self.status_label.configure(text="Processing file (merging/converting)...", text_color=ACCENT_COLOR))

    def handle_success(self, filepath, info):
        self.last_download_path = filepath
        
        video_info = self.current_video_info if self.current_video_info else info
        add_to_history(video_info, filepath)
        
        def update_ui():
            self.status_label.configure(text="Download complete!", text_color=("#10B981", "#00FF88"))
            self.progress_bar.set(1.0)
            self.stats_label.configure(text="100% | Done")
            self.reset_download_buttons()
            
            self.open_file_btn.configure(state="normal")
            self.open_folder_btn.configure(state="normal")
            self.open_file_btn.pack(side="left", padx=10)
            self.open_folder_btn.pack(side="left", padx=10)
            
        self.after(0, update_ui)

    def handle_error(self, message):
        def update_ui():
            self.status_label.configure(text=message, text_color=DANGER_COLOR)
            self.reset_download_buttons()
            if "cancelled" not in message.lower():
                messagebox.showerror("Download Error", message)
                
        self.after(0, update_ui)

    def reset_download_buttons(self):
        self.download_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.fetch_btn.configure(state="normal")
        self.url_entry.configure(state="normal")

    def open_downloaded_file(self):
        if self.last_download_path:
            open_file(self.last_download_path)

    def open_downloaded_folder(self):
        if self.last_download_path:
            open_folder(self.last_download_path)

    def generate_clip(self):
        url = self.clip_url_var.get().strip()
        start_txt = self.clip_start_var.get().strip()
        end_txt = self.clip_end_var.get().strip()
        
        if not url or not start_txt or not end_txt:
            messagebox.showwarning("Warning", "URL, Start Time, and End Time are required.")
            return
            
        try:
            start_sec = int(start_txt)
            end_sec = int(end_txt)
        except ValueError:
            messagebox.showerror("Error", "Start and End times must be integers (seconds).")
            return
            
        self.clip_btn.configure(state="disabled")
        self.clip_status_label.configure(text="Downloading segment...", text_color=ACCENT_COLOR)
        
        original_success = self.downloader.on_success
        original_error = self.downloader.on_error
        
        def clip_on_success(filepath, info):
            self.after(0, lambda: self.clip_status_label.configure(text="Processing via ffmpeg..."))
            
            format_type = self.clip_format_var.get()
            is_short = format_type == "Short (9:16 MP4)"
            is_gif = format_type == "Meme GIF"
            top_text = self.clip_top_var.get()
            bottom_text = self.clip_bottom_var.get()
            
            output_file = str(Path(filepath).with_name(f"clip_{Path(filepath).name}"))
            
            success, msg_or_path = process_clip(
                filepath, output_file, 
                start_time=None, end_time=None, 
                top_text=top_text, bottom_text=bottom_text, 
                is_short=is_short, is_gif=is_gif
            )
            
            self.downloader.on_success = original_success
            self.downloader.on_error = original_error
            
            if success:
                def update_ui():
                    self.clip_status_label.configure(text=f"Success!", text_color=("#10B981", "#00FF88"))
                    self.clip_btn.configure(state="normal")
                    open_folder(msg_or_path)
                self.after(0, update_ui)
            else:
                def update_ui():
                    self.clip_status_label.configure(text="FFmpeg Error", text_color=DANGER_COLOR)
                    self.clip_btn.configure(state="normal")
                    messagebox.showerror("Error", msg_or_path)
                self.after(0, update_ui)
                
        def clip_on_error(message):
            self.downloader.on_success = original_success
            self.downloader.on_error = original_error
            def update_ui():
                self.clip_status_label.configure(text=message, text_color=DANGER_COLOR)
                self.clip_btn.configure(state="normal")
            self.after(0, update_ui)
            
        self.downloader.on_success = clip_on_success
        self.downloader.on_error = clip_on_error
        
        folder = self.settings.get("download_folder", str(Path.home() / "Downloads"))
        self.downloader.download(url, folder, format_type='video', quality='best', single_video=True, clip_start=start_sec, clip_end=end_sec)


if __name__ == "__main__":
    app = AppUI()
    app.mainloop()
