from flask import Flask, request, jsonify, render_template, Response, stream_with_context, send_file
from flask_cors import CORS
from urllib.request import Request, urlopen
import yt_dlp
import time
import os
import re
import threading
import uuid
from datetime import datetime, timedelta

# ── Cookie file config ───────────────────────────────────────────────────────
# Set these environment variables to point to Netscape-format cookie files
# exported from a logged-in browser session. Leave unset to skip session auth.
INSTAGRAM_COOKIES_FILE = os.environ.get('IG_COOKIES_FILE', None)
YOUTUBE_COOKIES_FILE   = os.environ.get('YT_COOKIES_FILE', None)
# ─────────────────────────────────────────────────────────────────────────────

IG_DOMAINS = re.compile(r'https?://(www\.)?instagram\.com', re.IGNORECASE)
YT_DOMAINS = re.compile(r'https?://(www\.|m\.)?youtube\.com|https?://youtu\.be', re.IGNORECASE)

# Error substrings that indicate YouTube wants a login for this specific video
_YT_LOGIN_ERRORS = (
    'sign in',
    'login required',
    'age-restricted',
    'age restricted',
    'this video is not available',
    'private video',
    'members only',
    'youtube kids',
)

def _needs_ig_session(url: str) -> bool:
    """True only for Instagram Stories / Highlights — not public posts."""
    if not IG_DOMAINS.match(url):
        return False
    return bool(re.search(r'/(stories|highlights)/', url, re.IGNORECASE))

def _is_yt_restricted_error(exc: Exception) -> bool:
    """True when a yt-dlp error signals that this video needs a YT session."""
    msg = str(exc).lower()
    return any(kw in msg for kw in _YT_LOGIN_ERRORS)

def _build_ydl_opts(url: str, extra: dict | None = None, use_yt_cookies: bool = False) -> dict:
    """
    Build yt-dlp options for a given URL.
    - Instagram Stories/Highlights: inject IG session cookies.
    - YouTube restricted (on retry): inject YT session cookies.
    - All other URLs / first attempts: no cookies at all.
    Does NOT set skip_download — callers must set it themselves.
    """
    opts: dict = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    # Instagram: inject only for Stories / Highlights
    if _needs_ig_session(url) and INSTAGRAM_COOKIES_FILE and os.path.isfile(INSTAGRAM_COOKIES_FILE):
        opts['cookiefile'] = INSTAGRAM_COOKIES_FILE
        print(f'[IG SESSION] Injecting cookies for: {url}')
    # YouTube: inject only when the caller explicitly requests it (after a restriction error)
    elif use_yt_cookies and YT_DOMAINS.match(url) and YOUTUBE_COOKIES_FILE and os.path.isfile(YOUTUBE_COOKIES_FILE):
        opts['cookiefile'] = YOUTUBE_COOKIES_FILE
        print(f'[YT SESSION] Injecting cookies for restricted video: {url}')
    if extra:
        opts.update(extra)
    return opts

def _extract_info_with_fallback(url: str) -> dict:
    """
    Extract video info without cookies first.
    If the video is age-restricted or requires login on YouTube,
    automatically retry using the YT session cookies for that video only.
    """
    opts = _build_ydl_opts(url, {'skip_download': True})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as first_err:
        # Only retry for YouTube restriction errors when a cookies file is configured
        if _is_yt_restricted_error(first_err) and YT_DOMAINS.match(url) and \
                YOUTUBE_COOKIES_FILE and os.path.isfile(YOUTUBE_COOKIES_FILE):
            print(f'[YT FALLBACK] First attempt failed ("{first_err}") — retrying with session.')
            retry_opts = _build_ydl_opts(url, {'skip_download': True}, use_yt_cookies=True)
            with yt_dlp.YoutubeDL(retry_opts) as ydl:
                return ydl.extract_info(url, download=False)
        raise  # Re-raise for non-YT or unconfigured cases

app = Flask(__name__)
CORS(app)

# Simple rate limiter using IP addresses
rate_limit_cache = {}
RATE_LIMIT_DURATION = 10  # Seconds
MAX_REQUESTS_PER_DURATION = 3

# Server Temporary Download Management
TEMP_DIR = os.path.join(os.getcwd(), 'temp_downloads')
os.makedirs(TEMP_DIR, exist_ok=True)

# Global tracker for real-time progress syncing
active_downloads = {}

def cleanup_temp_files():
    """Background daemon to purge files older than 20 minutes to save server storage."""
    while True:
        try:
            now = time.time()
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.isfile(filepath):
                    if now - os.path.getmtime(filepath) > 1200: # 1200 seconds = 20 mins
                        os.remove(filepath)
                        print(f"[CLEANUP] Deleted old temporary file: {filename}")
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")
        time.sleep(300) # Sleep for 5 mins

# Start cleanup daemon
threading.Thread(target=cleanup_temp_files, daemon=True).start()

def is_rate_limited(ip):
    now = datetime.now()
    if ip not in rate_limit_cache:
        rate_limit_cache[ip] = []
    
    # Remove old requests
    rate_limit_cache[ip] = [req_time for req_time in rate_limit_cache[ip] if now - req_time < timedelta(seconds=RATE_LIMIT_DURATION)]
    
    if len(rate_limit_cache[ip]) >= MAX_REQUESTS_PER_DURATION:
        return True
        
    rate_limit_cache[ip].append(now)
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        return jsonify({'error': 'Rate limit exceeded. Please wait a few seconds.'}), 429

    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']

    try:
        info = _extract_info_with_fallback(url)

        # Extract title and thumbnail
        title = info.get('title', 'Unknown Title')
        thumbnail = info.get('thumbnail', '')
        all_formats = info.get('formats', [])

        # Extract all complete resolutions (combining video+audio)
        extracted_formats = []
        seen_heights = {}

        for f in all_formats:
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            ext = f.get('ext', '')
            height = f.get('height')
            
            # Skip non-video streams
            if vcodec == 'none' or not height:
                continue
                
            is_progressive = (acodec != 'none')
            
            # Prefer standard formats
            if ext not in ['mp4', 'webm']: 
                continue

            # Track the best variant for each height
            if height not in seen_heights:
                seen_heights[height] = f
            else:
                current = seen_heights[height]
                curr_is_prog = (current.get('acodec') != 'none')
                
                # Progressive takes strict precedence to save server FFmpeg merges!
                if is_progressive and not curr_is_prog:
                    seen_heights[height] = f
                elif is_progressive == curr_is_prog:
                    if ext == 'mp4' and current.get('ext') != 'mp4': # MP4 preferred
                        seen_heights[height] = f

        # Compile final user-facing formats
        for height, f in seen_heights.items():
            is_progressive = (f.get('acodec') != 'none')
            format_id = f.get('format_id')
            
            # If adaptive, we instruct yt-dlp to grab format_id + the absolute best audio
            download_format = format_id if is_progressive else f"{format_id}+bestaudio"
            ext = 'mp4' if f.get('ext') == 'mp4' or not is_progressive else 'webm'
            
            extracted_formats.append({
                'resolution': f"{height}p",
                'is_progressive': is_progressive,
                'format_id': download_format,
                'ext': ext,
                'url': f.get('url') if is_progressive else None,
                'filesize': f.get('filesize'),
                'is_premium': (isinstance(height, int) and height > 1080)
            })

        # Sort descending by resolution quality
        extracted_formats.sort(key=lambda x: int(x['resolution'].replace('p', '')), reverse=True)

        # ── Auto-unlock fallback ──────────────────────────────────────────────
        # If every detected format is locked (premium) the user would have zero
        # downloadable options.  In that case, automatically unlock the lowest
        # available resolution so there is always at least one free option.
        if extracted_formats and all(f['is_premium'] for f in extracted_formats):
            lowest = extracted_formats[-1]   # list is sorted high → low, so last = lowest
            lowest['is_premium'] = False
            print(f"[AUTO-UNLOCK] All formats locked — unlocked {lowest['resolution']} as fallback.")
        # ─────────────────────────────────────────────────────────────────────

        return jsonify({
            'title': title,
            'thumbnail': thumbnail,
            'formats': extracted_formats
        })

    except Exception as e:
        # Handle invalid URLs or yt-dlp errors
        print(f"[EXTRACT ERROR] {e}")
        return jsonify({'error': 'Extraction failed. Please check the URL and try again.'}), 500

@app.route('/proxy', methods=['GET'])
def proxy_download():
    video_url = request.args.get('url')
    title = request.args.get('title', 'video')
    ext = request.args.get('ext', 'mp4')
    
    if not video_url:
        return "No URL provided", 400
        
    try:
        req = Request(video_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        response = urlopen(req)
        
        def generate():
            while True:
                chunk = response.read(65536) # Read in 64KB chunks
                if not chunk:
                    break
                yield chunk
                
        # Force 'Save As' download behavior in browsers
        headers = {
            'Content-Disposition': f'attachment; filename="{title}.{ext}"'
        }
        
        return Response(stream_with_context(generate()), 
                       content_type=response.info().get_content_type(),
                       headers=headers)
    except Exception as e:
        return str(e), 500

def my_hook(d, job_id):
    if job_id not in active_downloads:
        return
        
    if d['status'] == 'downloading':
        try:
            # yt-dlp includes ansi color codes in _percent_str sometimes in terminal, but passing directly is okay
            percent_str = d.get('_percent_str', '1%').strip()
            eta_str = d.get('_eta_str', 'Unknown')
            
            # Clean ANSI escape sequences
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            percent_str = ansi_escape.sub('', percent_str)
            eta_str = ansi_escape.sub('', eta_str)
            
            active_downloads[job_id]['status'] = 'downloading'
            active_downloads[job_id]['percent'] = percent_str
            active_downloads[job_id]['eta'] = eta_str
        except Exception as e:
            print("[HOOK ERROR]", e)
    elif d['status'] == 'finished':
        # Download done, now FFmpeg merge begins
        active_downloads[job_id]['status'] = 'merging'
        active_downloads[job_id]['percent'] = '100%'

@app.route('/api/start_merge', methods=['POST'])
def api_start_merge():
    data = request.json
    src_url = data.get('url')
    format_id = data.get('format_id')
    title = data.get('title', 'video')
    
    if not src_url or not format_id:
        return jsonify({'error': 'Missing arguments'}), 400
        
    job_id = str(uuid.uuid4())
    active_downloads[job_id] = {
        'status': 'starting', 
        'percent': '0%', 
        'eta': '...', 
        'title': title
    }
    
    def run_yt_dlp(job_id, src_url, format_id):
        out_tmpl = os.path.join(TEMP_DIR, f"{job_id}.%(ext)s")
        download_extra = {
            'format': format_id,
            'outtmpl': out_tmpl,
            'merge_output_format': 'mp4',
            'nocolor': True,
            'progress_hooks': [lambda d: my_hook(d, job_id)]
        }

        def _attempt(use_yt_cookies=False):
            opts = _build_ydl_opts(src_url, download_extra, use_yt_cookies=use_yt_cookies)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([src_url])

        try:
            print(f"[SERVER MERGE STARTED] Job {job_id} for format '{format_id}'")
            try:
                _attempt(use_yt_cookies=False)
            except Exception as first_err:
                if _is_yt_restricted_error(first_err) and YT_DOMAINS.match(src_url) and \
                        YOUTUBE_COOKIES_FILE and os.path.isfile(YOUTUBE_COOKIES_FILE):
                    print(f'[YT FALLBACK DL] Retrying download with session for job {job_id}')
                    _attempt(use_yt_cookies=True)
                else:
                    raise
                
            final_path = os.path.join(TEMP_DIR, f"{job_id}.mp4")
            if not os.path.exists(final_path):
                final_path = os.path.join(TEMP_DIR, f"{job_id}.webm")
                
            if os.path.exists(final_path):
                print(f"[SERVER MERGE FINISHED] Job {job_id} success.")
                active_downloads[job_id]['filepath'] = final_path
                active_downloads[job_id]['status'] = 'finished'
            else:
                active_downloads[job_id]['status'] = 'error'
                active_downloads[job_id]['message'] = 'FFmpeg merge failed producing no output file.'
                
        except Exception as e:
            if job_id in active_downloads:
                active_downloads[job_id]['status'] = 'error'
                active_downloads[job_id]['message'] = str(e)
                print("[BACKGROUND ERROR]", str(e))

    threading.Thread(target=run_yt_dlp, args=(job_id, src_url, format_id), daemon=True).start()
    return jsonify({'job_id': job_id})

@app.route('/api/progress/<job_id>', methods=['GET'])
def api_progress(job_id):
    if job_id not in active_downloads:
        return jsonify({'error': 'Job not found'}), 404
        
    return jsonify(active_downloads[job_id])

@app.route('/api/get_file/<job_id>', methods=['GET'])
def api_get_file(job_id):
    if job_id not in active_downloads:
        return "Job not found", 404
        
    job_data = active_downloads[job_id]
    if job_data.get('status') == 'finished':
        file_path = job_data.get('filepath')
        title = job_data.get('title', 'video')
        # Return file dynamically
        return send_file(file_path, as_attachment=True, download_name=f"{title}.mp4")
    else:
        return "File is not finished downloading yet.", 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)
