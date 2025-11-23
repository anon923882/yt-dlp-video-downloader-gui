import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yt_dlp
import threading
import os

class VideoDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader")
        self.root.geometry("700x500")
        self.root.resizable(False, False)
        
        # Variables
        self.url_var = tk.StringVar()
        self.download_path = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.formats = []
        self.selected_format = tk.StringVar()
        
        # Create GUI elements
        self.create_widgets()
        
    def create_widgets(self):
        # URL Frame
        url_frame = ttk.LabelFrame(self.root, text="Video URL", padding=10)
        url_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(url_frame, text="Enter URL:").pack(side="left", padx=5)
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=50)
        url_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        fetch_btn = ttk.Button(url_frame, text="Fetch Formats", command=self.fetch_formats)
        fetch_btn.pack(side="left", padx=5)
        
        # Download Path Frame
        path_frame = ttk.LabelFrame(self.root, text="Download Location", padding=10)
        path_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Entry(path_frame, textvariable=self.download_path, width=60).pack(side="left", padx=5)
        ttk.Button(path_frame, text="Browse", command=self.browse_folder).pack(side="left", padx=5)
        
        # Format Selection Frame
        format_frame = ttk.LabelFrame(self.root, text="Available Formats", padding=10)
        format_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Listbox with scrollbar
        scrollbar = ttk.Scrollbar(format_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.format_listbox = tk.Listbox(format_frame, yscrollcommand=scrollbar.set, height=10)
        self.format_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.format_listbox.yview)
        
        # Progress Frame
        progress_frame = ttk.Frame(self.root, padding=10)
        progress_frame.pack(fill="x", padx=10, pady=10)
        
        self.progress_label = ttk.Label(progress_frame, text="Ready")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress_bar.pack(fill="x", pady=5)
        
        # Download Button
        self.download_btn = ttk.Button(self.root, text="Download Selected Format", 
                                       command=self.download_video, state="disabled")
        self.download_btn.pack(pady=10)
        
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_path.set(folder)
    
    def fetch_formats(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL")
            return
        
        self.progress_label.config(text="Fetching available formats...")
        self.progress_bar.start()
        self.format_listbox.delete(0, tk.END)
        
        thread = threading.Thread(target=self._fetch_formats_thread, args=(url,))
        thread.start()
    
    def _fetch_formats_thread(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Extract and organize formats
                self.formats = []
                format_list = []
                
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        # Combined video+audio format
                        height = f.get('height', 'N/A')
                        ext = f.get('ext', 'N/A')
                        filesize = f.get('filesize', 0)
                        size_mb = f"{filesize / (1024*1024):.1f} MB" if filesize else "Unknown size"
                        fps = f.get('fps', 'N/A')
                        format_id = f.get('format_id')
                        
                        format_str = f"{height}p | {ext} | {size_mb} | {fps} fps"
                        format_list.append(format_str)
                        self.formats.append(format_id)
                
                # Update UI in main thread
                self.root.after(0, self._update_format_list, format_list, info.get('title', 'Video'))
                
        except Exception as e:
            self.root.after(0, self._show_error, f"Error fetching formats: {str(e)}")
    
    def _update_format_list(self, format_list, title):
        self.progress_bar.stop()
        
        if not format_list:
            self.progress_label.config(text="No formats available")
            messagebox.showinfo("Info", "No combined video+audio formats found. Try different options.")
            return
        
        for fmt in format_list:
            self.format_listbox.insert(tk.END, fmt)
        
        self.progress_label.config(text=f"Found {len(format_list)} formats for: {title[:50]}")
        self.download_btn.config(state="normal")
    
    def _show_error(self, message):
        self.progress_bar.stop()
        self.progress_label.config(text="Error occurred")
        messagebox.showerror("Error", message)
    
    def download_video(self):
        selection = self.format_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a format to download")
            return
        
        format_id = self.formats[selection[0]]
        url = self.url_var.get().strip()
        download_path = self.download_path.get()
        
        self.progress_label.config(text="Downloading...")
        self.progress_bar.start()
        self.download_btn.config(state="disabled")
        
        thread = threading.Thread(target=self._download_thread, args=(url, format_id, download_path))
        thread.start()
    
    def _download_thread(self, url, format_id, download_path):
        try:
            ydl_opts = {
                'format': format_id,
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            self.root.after(0, self._download_complete)
            
        except Exception as e:
            self.root.after(0, self._show_error, f"Download error: {str(e)}")
            self.root.after(0, lambda: self.download_btn.config(state="normal"))
    
    def progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            self.root.after(0, lambda: self.progress_label.config(
                text=f"Downloading: {percent} | Speed: {speed}"))
        elif d['status'] == 'finished':
            self.root.after(0, lambda: self.progress_label.config(text="Processing..."))
    
    def _download_complete(self):
        self.progress_bar.stop()
        self.progress_label.config(text="Download completed!")
        self.download_btn.config(state="normal")
        messagebox.showinfo("Success", "Video downloaded successfully!")

def main():
    root = tk.Tk()
    app = VideoDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
