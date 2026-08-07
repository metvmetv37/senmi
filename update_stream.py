#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOUTUBE STREAM KURTARICI - M3U ENTEGRASYONU
Tüm YouTube kanallarının gerçek stream URL'lerini çeker ve M3U dosyalarını günceller.
Bot korumasını aşmak için çoklu yöntem kullanır.
"""

import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ KONFIGÜRASYON ============
PLAYLIST_DIR = Path("playlist")
CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.txt"
TIMEOUT = 120
MAX_RETRIES = 3
WORKERS = 4  # Paralel işlem için

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

# ============ YARDIMCI FONKSİYONLAR ============

def load_config() -> Dict:
    """config.json'dan kanal listesini yükler."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[HATA] Config yüklenemedi: {e}")
        return {"channels": []}

def get_channel_type(channel: Dict) -> str:
    """Kanal tipini belirler: 'youtube', 'direct', 'eurostar', 'showturk'"""
    name = channel.get("name", "")
    url = channel.get("url") or channel.get("youtube_url", "")
    
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "eurostar" in name.lower() or "euro" in name.lower():
        return "eurostar"
    if "show_turk" in name.lower() or "showturk" in name.lower():
        return "showturk"
    if url.endswith(".m3u8") or "m3u8" in url:
        return "direct"
    return "unknown"

def clean_cookie_file() -> bool:
    """Cookie dosyasını temizler ve geçersiz cookie'leri kaldırır."""
    cookie_path = Path(COOKIE_FILE)
    if not cookie_path.exists():
        return False
    
    blocked = ["CONSISTENCY", "ST-sbra4i", "OTZ", "__Secure-YEC", "__Secure-YENID"]
    try:
        content = cookie_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        cleaned = []
        cookie_count = 0
        for line in lines:
            if line.startswith("#"):
                cleaned.append(line)
                continue
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5].strip()
                if name not in blocked:
                    cleaned.append(line)
                    cookie_count += 1
        if cookie_count > 0:
            cookie_path.write_text("\n".join(cleaned), encoding="utf-8")
            print(f"[COOKIE] {cookie_count} geçerli cookie korundu.")
            return True
        else:
            cookie_path.write_text("", encoding="utf-8")
            print("[COOKIE] Tüm cookie'ler temizlendi, dosya boşaltıldı.")
            return False
    except Exception as e:
        print(f"[COOKIE] Temizleme hatası: {e}")
        return False

def get_cookies_from_browser(browser: str = "chrome") -> bool:
    """Tarayıcıdan cookie çeker."""
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser,
        "--cookies", COOKIE_FILE,
        "--simulate",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ]
    try:
        subprocess.run(cmd, check=True, timeout=30, capture_output=True)
        print(f"[COOKIE] {browser} üzerinden cookie çekildi.")
        return True
    except Exception as e:
        print(f"[COOKIE] Tarayıcıdan cookie çekilemedi: {e}")
        return False

def ensure_cookies() -> bool:
    """Cookie'lerin varlığını ve geçerliliğini kontrol eder."""
    cookie_path = Path(COOKIE_FILE)
    if cookie_path.exists() and cookie_path.stat().st_size > 100:
        clean_cookie_file()
        if cookie_path.stat().st_size > 50:
            print("[COOKIE] Mevcut cookie'ler kullanılıyor.")
            return True
    
    # Cookie yok veya çok küçük, tarayıcıdan dene
    print("[COOKIE] Cookie dosyası geçersiz, tarayıcıdan çekiliyor...")
    for browser in ["chrome", "firefox", "brave", "edge"]:
        if get_cookies_from_browser(browser):
            return True
    
    print("[UYARI] Cookie alınamadı, cookiesiz devam ediliyor.")
    return False

# ============ YOUTUBE STREAM ALMA ============

def get_youtube_stream_with_ytdlp(video_url: str, quality: str = "best[height<=1080][fps<=50]/best") -> Optional[str]:
    """yt-dlp ile YouTube stream URL'sini alır."""
    cookie_arg = ["--cookies", COOKIE_FILE] if Path(COOKIE_FILE).exists() else []
    
    # Farklı client'ler ve yöntemler
    methods = [
        # 1. Deno + ejs + default client
        {
            "name": "deno/ejs/default",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                *cookie_arg,
                "--js-runtimes", "deno",
                "--remote-components", "ejs:github",
                "--extractor-args", "youtube:player_client=default",
                "-f", quality,
                "-g",
                video_url
            ]
        },
        # 2. Deno + ejs + android client (genelde işe yarar)
        {
            "name": "deno/ejs/android",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                *cookie_arg,
                "--js-runtimes", "deno",
                "--remote-components", "ejs:github",
                "--extractor-args", "youtube:player_client=android",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 3. Deno + ejs + ios client
        {
            "name": "deno/ejs/ios",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                *cookie_arg,
                "--js-runtimes", "deno",
                "--remote-components", "ejs:github",
                "--extractor-args", "youtube:player_client=ios",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 4. Klasik yöntem - android
        {
            "name": "classic/android",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                *cookie_arg,
                "--extractor-args", "youtube:player_client=android",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 5. Klasik yöntem - default (cookie'siz de dene)
        {
            "name": "classic/default",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                "--extractor-args", "youtube:player_client=default",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 6. Klasik yöntem - tv client
        {
            "name": "classic/tv",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                *cookie_arg,
                "--extractor-args", "youtube:player_client=tv",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        }
    ]
    
    for method in methods:
        try:
            print(f"   ▶️ {method['name']}")
            result = subprocess.run(
                method["cmd"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                for line in lines:
                    if line.startswith("http") and (".m3u8" in line or "manifest" in line or "googlevideo" in line):
                        print(f"   ✅ {method['name']} başarılı")
                        return line
            # Hata mesajını kısaca göster
            if result.stderr:
                err = result.stderr[:150].replace("\n", " ")
                print(f"   ⚠️ {err}")
        except subprocess.TimeoutExpired:
            print(f"   ⏱️ {method['name']} zaman aşımı")
        except Exception as e:
            print(f"   ❌ {method['name']} hata: {e}")
    
    return None

def get_eurostar_token() -> Optional[str]:
    """EuroStar TV 1080p stream URL'sini alır."""
    headers = {"User-Agent": CHROME_UA}
    try:
        import requests
        html = requests.get("https://www.eurostartv.com.tr/canli-izle", headers=headers, timeout=15).text
        match = re.search(r"var liveUrl = 'https://dygvideo\.dygdigital\.com/live/hls/staravrupa\?token=([a-f0-9]+)';", html)
        if match:
            token = match.group(1)
            token_url = f"https://dygvideo.dygdigital.com/live/hls/staravrupa?token={token}"
            resp = requests.get(token_url, headers=headers, allow_redirects=False, timeout=10)
            if resp.status_code == 302 and "Location" in resp.headers:
                master = resp.headers["Location"]
                # 1080p'ye yönlendir
                match2 = re.match(r"(.*/)live\.m3u8\?(.*)", master)
                if match2:
                    return f"{match2.group(1)}live_1080p3000000kbps/index.m3u8?{match2.group(2)}"
                return master
        return None
    except Exception as e:
        print(f"[EUROSTAR] Hata: {e}")
        return None

def get_showturk_token() -> Optional[str]:
    """Show Türk stream URL'sini alır."""
    try:
        import requests
        html = requests.get("https://www.showturk.com.tr/canli-yayin", timeout=15).text
        match = re.search(r'playlist\.m3u8\?e=(\d+)&st=([^"\s&]+)', html)
        if match:
            e, st = match.groups()
            return f"https://ciner-live.ercdn.net/showturk/playlist.m3u8?e={e}&st={st}&tv=1"
        return None
    except Exception as e:
        print(f"[SHOWTURK] Hata: {e}")
        return None

# ============ M3U DOSYALARINI GÜNCELLE ============

def update_m3u_file(filepath: Path, stream_url: str) -> bool:
    """M3U dosyasını günceller."""
    if not filepath.exists():
        return False
    
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        new_lines = []
        url_found = False
        
        for line in lines:
            if line.strip().startswith("http") and not url_found:
                new_lines.append(stream_url)
                url_found = True
            else:
                new_lines.append(line)
        
        # Eğer URL yoksa sonuna ekle
        if not url_found:
            new_lines.append(stream_url)
        
        filepath.write_text("\n".join(new_lines), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[HATA] {filepath.name} güncellenemedi: {e}")
        return False

def update_m3u_direct(filepath: Path, stream_url: str) -> bool:
    """M3U dosyasını sadece stream URL olarak günceller (minimal)."""
    try:
        content = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720\n" + stream_url
        filepath.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[HATA] {filepath.name} yazılamadı: {e}")
        return False

def process_channel(channel: Dict, index: int, total: int) -> Tuple[str, Optional[str]]:
    """Tek bir kanalı işler, stream URL'sini alır."""
    name = channel.get("name", f"Kanal_{index}")
    url = channel.get("url") or channel.get("youtube_url", "")
    
    print(f"\n🔄 [{index}/{total}] {name}")
    
    if not url:
        print(f"   ⚠️ URL yok, atlanıyor.")
        return (name, None)
    
    channel_type = get_channel_type(channel)
    
    if channel_type == "eurostar":
        stream_url = get_eurostar_token()
    elif channel_type == "showturk":
        stream_url = get_showturk_token()
    elif channel_type == "direct":
        stream_url = url
    else:
        # YouTube veya bilinmeyen
        stream_url = get_youtube_stream_with_ytdlp(url)
    
    if stream_url:
        print(f"   ✅ Stream URL alındı: {stream_url[:60]}...")
    else:
        print(f"   ❌ Stream URL alınamadı!")
    
    return (name, stream_url)

def main() -> int:
    print("=" * 70)
    print(" YOUTUBE STREAM KURTARICI - M3U ENTEGRASYONU")
    print(f" Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 1. Cookie'leri kontrol et
    ensure_cookies()
    
    # 2. Config yükle
    config = load_config()
    channels = config.get("channels", [])
    if not channels:
        print("[HATA] config.json'da kanal bulunamadı!")
        return 1
    
    print(f"\n[INFO] {len(channels)} kanal işlenecek.")
    
    # 3. Tüm kanalları işle
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(process_channel, ch, idx, len(channels)): idx 
            for idx, ch in enumerate(channels, 1)
        }
        for future in as_completed(futures):
            results.append(future.result())
    
    # 4. Sonuçları işle ve M3U dosyalarını güncelle
    success_count = 0
    for name, stream_url in results:
        if not stream_url:
            continue
        
        # Dosya adını bul
        filename = safe_filename(name)
        m3u_file = PLAYLIST_DIR / f"{filename}.m3u"
        
        # Eğer dosya yoksa oluştur
        if not m3u_file.exists():
            update_m3u_direct(m3u_file, stream_url)
            print(f"   [YENİ] {m3u_file.name} oluşturuldu.")
        else:
            update_m3u_file(m3u_file, stream_url)
            print(f"   [GÜNCELLE] {m3u_file.name} güncellendi.")
        
        success_count += 1
    
    # 5. Ana playlist'i yeniden oluştur
    print("\n[INFO] Ana playlist oluşturuluyor...")
    generate_main_playlist()
    
    print(f"\n[OK] {success_count}/{len(channels)} kanal başarıyla güncellendi.")
    print(f"[OK] İşlem tamamlandı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0

def safe_filename(name: str) -> str:
    """Kanal adını güvenli dosya adına çevirir."""
    replacements = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
        " ": "_", "'": "", '"': "", "?": "", "!": "", ",": "", ".": "",
        ";": "", ":": "", "(": "", ")": "", "[": "", "]": ""
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("_")
    return name if name else "kanal"

def generate_main_playlist():
    """Ana playlist'i yeniden oluşturur."""
    output_file = PLAYLIST_DIR / "playerlist.m3u"
    github_base = "https://raw.githubusercontent.com/metvmetv37/senmi/refs/heads/main/playlist"
    
    files = list(PLAYLIST_DIR.glob("*.m3u"))
    files = [f for f in files if f.name not in ["playerlist.m3u", "playlist.m3u8"]]
    
    lines = ["#EXTM3U"]
    for f in sorted(files):
        name = f.stem.replace("_", " ").strip()
        lines.append(f"#EXTINF:0,{name}")
        lines.append(f"{github_base}/{f.name}")
    
    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Aynısını playlist.m3u8 olarak da kaydet
    (PLAYLIST_DIR / "playlist.m3u8").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] {output_file.name} oluşturuldu, {len(files)} kanal.")

if __name__ == "__main__":
    sys.exit(main())
