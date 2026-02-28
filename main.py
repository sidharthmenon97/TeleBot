import os
import re
import asyncio
import shutil
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded
import subprocess

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Globals
client = None

state = {
    "status": "idle",
    "filename": "",
    "progress": 0.0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "active_clients": 0
}

# Use absolute paths if inside docker, otherwise relative for local dev
BASE_MEDIA_DIR = "/mnt/hdd/Movies" if os.path.exists("/.dockerenv") else "media"
SESSION_DIR = "/session" if os.path.exists("/.dockerenv") else "session"
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(BASE_MEDIA_DIR, exist_ok=True)

state = {
    "status": "idle",
    "filename": "",
    "progress": 0.0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "active_clients": 0,
    "download_path": BASE_MEDIA_DIR,
    "rename_smart": True,
    "debug_mode": False,
    "queue": [],
    "cancel_current": False
}

internal_queue = asyncio.Queue()
worker_task = None

def session_exists():
    return os.path.exists(os.path.join(SESSION_DIR, "user.session")) or \
           os.path.exists(os.path.join(SESSION_DIR, "user.session-journal"))

class LoginData(BaseModel):
    api_id: str
    api_hash: str
    phone: str

class VerifyData(BaseModel):
    phone_code_hash: str
    phone_code: str
    phone: str
    password: str = ""

class ConfigData(BaseModel):
    download_path: str = None
    rename_smart: bool = None
    debug_mode: bool = None

@app.on_event("startup")
async def startup_event():
    if session_exists():
        asyncio.create_task(start_userbot())

async def queue_worker():
    global state
    while True:
        message, final_title, final_filename = await internal_queue.get()
        
        # Remove from UI queue
        if state["queue"] and final_filename in state["queue"]:
            state["queue"].remove(final_filename)
            
        await process_item(message, final_title, final_filename)
        internal_queue.task_done()

async def process_item(message, final_title, final_filename):
    global state
    temp_download_path = os.path.join(state["download_path"], final_filename)
    
    if state["debug_mode"]:
        print(f"[DEBUG] Starting Pyrogram download temporarily to: {temp_download_path}")
    
    state["status"] = "downloading"
    state["filename"] = final_filename
    state["progress"] = 0.0
    state["downloaded_bytes"] = 0
    state["total_bytes"] = 0
    state["cancel_current"] = False
    
    async def progress(current, total):
        if state.get("cancel_current"):
            raise Exception("DOWNLOAD_CANCELLED_BY_USER")
            
        if state["active_clients"] > 0:
            state["progress"] = (current / total) * 100 if total else 0
            state["downloaded_bytes"] = current
            state["total_bytes"] = total
    
    try:
        await message.download(file_name=temp_download_path, progress=progress)
        
        target_dir = os.path.join(state["download_path"], final_title)
        if state["debug_mode"]:
            print(f"[DEBUG] Download completed. Creating target directory: {target_dir}")
            
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, final_filename)
        
        if state["debug_mode"]:
            print(f"[DEBUG] Moving file from {temp_download_path} to {target_path}")
            
        shutil.move(temp_download_path, target_path)
        
        if state["debug_mode"]:
            print(f"[DEBUG] Move completed successfully. Passing to pipeline.")
            
        await run_pipeline(target_path)
    except Exception as e:
        if str(e) == "DOWNLOAD_CANCELLED_BY_USER":
            print(f"[INFO] Download of {final_filename} was cancelled.")
        else:
            print(f"[ERROR] Download or Move failed: {e}")
            
        # Clean up partial temp file if exists
        try:
            if os.path.exists(temp_download_path):
                os.remove(temp_download_path)
        except Exception as cleanup_err:
            print(f"[ERROR] Failed to clean up temp file: {cleanup_err}")
            
        state["status"] = "idle"

async def start_userbot():
    global client, worker_task
    if client is None:
        client = Client("user", workdir=SESSION_DIR)
        
    if worker_task is None:
        worker_task = asyncio.create_task(queue_worker())
    
    @client.on_message(filters.forwarded & (filters.document | filters.video))
    async def media_handler(c: Client, message):
        global state
        
        if state["debug_mode"]:
            print(f"[DEBUG] Received forwarded message. Has document: {bool(message.document)}, Has video: {bool(message.video)}")
            
        # Extract filename
        if message.document:
            filename = message.document.file_name
        elif message.video:
            filename = message.video.file_name
        else:
            if state["debug_mode"]:
                print("[DEBUG] Message had no valid document or video attachment. Ignoring.")
            return
            
        if state["debug_mode"]:
            print(f"[DEBUG] Extracted raw filename: {filename}")
            
        if not filename:
            filename = "unknown_file.bin"
            
        # Clean filename logic specifically for Movie (Year)
        clean_name = re.sub(r'\[.*?\]', '', filename)
        clean_name = re.sub(r'@\w+', '', clean_name)
        
        ext = ""
        if '.' in clean_name:
            parts = clean_name.rsplit('.', 1)
            ext = "." + parts[-1]
            base_name = parts[0]
        else:
            base_name = clean_name
            
        base_name = base_name.replace('_', ' ').replace('.', ' ')
        
        # Try to find a year (e.g. 19xx or 20xx)
        if state["rename_smart"]:
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', base_name)
            if year_match:
                year = year_match.group(1)
                # Split string at the year
                name_part = base_name.split(year)[0]
                
                # Broadly clean: 
                # 1. Remove rogue parenthesis or brackets entirely from the title portion.
                name_part = re.sub(r'[()\[\]]', ' ', name_part)
                
                # 2. Strip leading characters that aren't letters or numbers (like dashes '- Padakkalam')
                name_part = re.sub(r'^[^a-zA-Z0-9]+', '', name_part)
                
                # 3. Strip trailing punctuation/spaces (dashes, dots, hyphens) next to the year boundary
                name_part = re.sub(r'[^a-zA-Z0-9]+$', '', name_part)
                
                # Remove extra spaces inside the title if any were left by removing brackets
                name_part = re.sub(r'\s+', ' ', name_part).strip()
                
                final_title = f"{name_part} ({year})"
            else:
                final_title = re.sub(r'\s+', ' ', base_name).strip()
        else:
            final_title = re.sub(r'\s+', ' ', base_name).strip()
        
        final_filename = final_title + ext
        
        if state["debug_mode"]:
            print(f"[DEBUG] Final parsed title: '{final_title}', Final filename: '{final_filename}'")
            print(f"[DEBUG] Adding to queue.")
            
        state["queue"].append(final_filename)
        await internal_queue.put((message, final_title, final_filename))

    print("Starting Pyrogram Userbot...")
    await client.start()

async def run_pipeline(target_path):
    global state
    state["status"] = "processing"
    
    abs_path = os.path.abspath(target_path)
    if state["debug_mode"]:
        print(f"[DEBUG] Executing pipeline script explicitly via bash with arg: {abs_path}")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "./pipeline.sh" if not os.path.exists("/.dockerenv") else "/app/pipeline.sh", 
            abs_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if state["debug_mode"]:
            print(f"[DEBUG] Pipeline script exit code: {proc.returncode}")
            if stdout:
                print(f"[DEBUG] Pipeline STDOUT:\n{stdout.decode()}")
            if stderr:
                print(f"[DEBUG] Pipeline STDERR:\n{stderr.decode()}")
                
    except Exception as e:
        print(f"[ERROR] Pipeline execution failed natively: {e}")
    finally:
        state["status"] = "idle"

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    if not session_exists():
        return templates.TemplateResponse("setup.html", {"request": request})
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/send_code")
async def send_code(data: LoginData):
    global client
    try:
        client = Client("user", api_id=int(data.api_id), api_hash=data.api_hash, workdir=SESSION_DIR)
        await client.connect()
        sent_code = await client.send_code(data.phone)
        return {"phone_code_hash": sent_code.phone_code_hash}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
async def login(data: VerifyData):
    global client
    if not client:
        raise HTTPException(status_code=400, detail="Client not initialized. Refresh and try again.")
        
    try:
        await client.sign_in(
            phone_number=data.phone,
            phone_code_hash=data.phone_code_hash,
            phone_code=data.phone_code
        )
    except SessionPasswordNeeded:
        if data.password:
            try:
                await client.check_password(data.password)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail="2FA Password required")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Save the session natively done by Pyrogram
    await client.disconnect()
    
    # Start the background listener
    asyncio.create_task(start_userbot())
    return {"status": "ok"}

@app.post("/config")
async def update_config(data: ConfigData):
    global state
    
    if data.rename_smart is not None:
        state["rename_smart"] = data.rename_smart
        
    if data.debug_mode is not None:
        state["debug_mode"] = data.debug_mode
        if state["debug_mode"]:
            print("[DEBUG] Debug Mode Enabled via API")
        
    if data.download_path is not None:
        new_path = data.download_path.strip()
        if new_path:
            try:
                os.makedirs(new_path, exist_ok=True)
                state["download_path"] = new_path
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to set path: {e}")
                
    return {"status": "ok", "state": state}
    
@app.post("/cancel")
async def cancel_download():
    global state
    if state["status"] == "downloading":
        state["cancel_current"] = True
        if state["debug_mode"]:
            print("[DEBUG] User triggered download cancellation.")
        return {"status": "cancelled"}
    return {"status": "ignored"}

# --- WebSocket ---
@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    await websocket.accept()
    global state
    state["active_clients"] += 1
    
    try:
        while True:
            await websocket.send_json(state)
            # Only poll/update intensely if there are active clients
            # (In this design, we just loop and broadcast state, Pyrogram updates the global state asynchronously)
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        state["active_clients"] -= 1

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=36168, log_level="info")
