import yt_dlp
import json
import time

url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'noplaylist': True,
    'extract_flat': False
}

start = time.time()
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    all_formats = info.get('formats', [])
    progressive_formats = []
    
    for f in all_formats:
        vcodec = f.get('vcodec')
        acodec = f.get('acodec')
        ext = f.get('ext')
        print(f"Format: id={f.get('format_id')} ext={ext} vcodec={vcodec} acodec={acodec} resolution={f.get('resolution')} height={f.get('height')}")
        
        if vcodec and vcodec != 'none' and acodec and acodec != 'none':
            progressive_formats.append(f)

    print(f"\nFound {len(progressive_formats)} progressive formats")
    print(f"Time taken: {time.time() - start:.2f}s")
    
except Exception as e:
    import traceback
    traceback.print_exc()
