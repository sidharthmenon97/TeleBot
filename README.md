# TeleBot - Telegram Media Downloader

TeleBot is a powerful, self-hosted, Pyrogram-based media downloader. It leverages a Telegram "Userbot" approach to completely bypass standard 50MB Bot API file size limits, allowing you to seamlessly forward and download massive premium media files (Movies, TV Shows, etc.) directly to your home server or NAS.

It features a modern WebSocket-driven web dashboard, an intelligent queuing system, and full Docker containerization for instant deployment.

## ✨ Features

- **No File Size Limits:** Uses MTProto under the hood (via Pyrogram) acting as a normal user account to download files up to 2GB (or 4GB for Telegram Premium).
- **Beautiful Web Interface:** Fully responsive, dark-mode dashboard built with vanilla CSS.
- **Smart Queue & Real-Time Tracking:** Forwards are dropped into an async queue processing exactly one item at a time. The web UI shows progress bars, current bandwidth stats, and what's up next in the queue instantly via WebSockets.
- **Atomic Move & Smart Renaming:** Automatically strips spam tags (`[@handles]`, `[SiteName]`) and extracts release years to format folders beautifully as `Movie Name (Year)`. It only moves files to their permanent location *after* they hit 100% to prevent media servers (like Plex) from scanning corrupted partial downloads.
- **Post-Processing Pipeline:** Automatically triggers an executable `pipeline.sh` bash script on completion. Perfect for triggering Handbrake transcodes, ML upscalers, or push notifications to your phone!
- **100% Containerized:** Ready to run anywhere Docker is installed.

---

## 🚀 Quick Start (Docker)

The recommended way to run TeleBot is via Docker Compose.

### 1. Clone the repository

```bash
git clone https://github.com/sidharthmenon97/TeleBot.git
cd TeleBot
```

### 2. Configure Paths

The included `docker-compose.yml` automatically mounts your host's `/mnt` folder to the container's `/mnt` folder. If your media drives are located at `/mnt/hdd/Movies`, you do not need to change anything!
If your media drives are located elsewhere (like `/data` or `C:\Movies`), edit the `docker-compose.yml` volumes section appropriately:

```yaml
    volumes:
      - ./session:/session
      - .:/app
      - /your/host/path:/your/host/path
```

### 3. Start the Container

```bash
docker-compose up --build -d
```

### 4. Authenticate & Dashboard

1. Open up `http://<your-server-ip>:36168` in your browser.
2. If this is your first time booting, the app will ask for your Telegram `api_id`, `api_hash` (grab these from my.telegram.org), and your Phone Number.
3. Once authenticated through the UI, the real-time Dashboard will appear.
4. **Simply forward any `.mkv`, `.mp4`, or document file into your "Saved Messages" on Telegram to start the download!**

---

## 🛠 Configurations (Web UI)

The web dashboard allows you to configure several runtime variables dynamically without restarting the container:

- **Download Path:** Instruct TeleBot exactly where to save completed files on your server (e.g. `/mnt/storage/Movies`).
- **Smart Rename Toggle:** Turn the `Movie (Year)` regex parser on or off.
- **Verbose Debugging:** Turn on heavy logging directly to standard out (`docker logs -f teledrop_app`).

## 📜 License

This project is open-source and free to use.
