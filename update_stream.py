#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOUTUBE STREAM KURTARICI - TAM ÇÖZÜM
PO Token, Visitor Data ve Cookie desteği ile tüm YouTube kanallarını kurtarır.
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
CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.txt"
PO_TOKEN_FILE = "po_token.txt"
VISITOR_DATA_FILE = "visitor_data.txt"
PLAYLIST_DIR = Path("playlist")
BROWSER = "chrome"  # chrome, firefox, brave, edge, opera
TIMEOUT = 120
MAX_RETRIES = 3
WORKERS = 4

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/148.0.0.0 Safari/537.36")

# ============ COOKIE YÖNETİMİ ============

def clean_cookie_file() -> bool:
    """Geçersiz cookie'leri temizler."""
    path = Path(COOKIE_FILE)
    if not path.exists():
        return False
    
    blocked = ["CONSISTENCY", "ST-sbra4i", "OTZ", "__Secure-YEC", "__Secure-YENID"]
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        cleaned = []
        cookie_count = 0
        
        for line in lines:
            if line.startswith("#") or not line.strip():
                cleaned.append(line)
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5].strip()
                if name not in blocked:
                    cleaned.append(line)
                    cookie_count += 1
        
        if cookie_count > 0:
            path.write_text("\n".join(cleaned), encoding="utf-8")
            print(f"[COOKIE] {cookie_count} geçerli cookie korundu.")
            return True
        else:
            path.write_text("", encoding="utf-8")
            print("[COOKIE] Tüm cookie'ler temizlendi, dosya boşaltıldı.")
            return False
    except Exception as e:
        print(f"[COOKIE] Temizleme hatası: {e}")
        return False

def export_cookies_from_browser() -> bool:
    """Tarayıcıdan YouTube cookie'lerini çeker."""
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", BROWSER,
        "--cookies", COOKIE_FILE,
        "--simulate",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ]
    try:
        subprocess.run(cmd, check=True, timeout=30, capture_output=True)
        if Path(COOKIE_FILE).exists() and Path(COOKIE_FILE).stat().st_size > 100:
            print(f"[COOKIE] {BROWSER} üzerinden cookie çekildi.")
            clean_cookie_file()
            return True
    except Exception as e:
        print(f"[COOKIE] Tarayıcıdan çekilemedi: {e}")
    return False

def ensure_cookies() -> bool:
    """Cookie'lerin varlığını ve geçerliliğini kontrol eder."""
    cookie_path = Path(COOKIE_FILE)
    
    # Mevcut cookie'leri kontrol et
    if cookie_path.exists() and cookie_path.stat().st_size > 100:
        clean_cookie_file()
        if cookie_path.stat().st_size > 50:
            print("[COOKIE] Mevcut cookie'ler kullanılıyor.")
            return True
    
    # Cookie yok veya geçersiz, tarayıcıdan dene
    print("[COOKIE] Cookie dosyası geçersiz, tarayıcıdan çekiliyor...")
    for browser in ["chrome", "firefox", "brave", "edge"]:
        if export_cookies_from_browser():
            return True
    
    # Manuel export yönlendirmesi
    print("\n[MANUEL] Cookie export edilemedi. Lütfen şu adımları izleyin:")
    print("   1) Chrome'da 'Get cookies.txt LOCALLY' eklentisini yükleyin.")
    print("   2) Gizli pencere açın ve YouTube'a giriş yapın.")
    print("   3) https://www.youtube.com/robots.txt adresine gidin.")
    print("   4) Cookie'leri export edip 'cookies.txt' olarak kaydedin.")
    
    input("\nCookie dosyasını kaydettikten sonra ENTER tuşuna basın...")
    
    if cookie_path.exists() and cookie_path.stat().st_size > 100:
        clean_cookie_file()
        return True
    
    print("[UYARI] Cookie alınamadı, sadece PO Token ile devam ediliyor.")
    return False

# ============ PO TOKEN YÖNETİMİ ============

def get_po_token_and_visitor_data() -> Tuple[Optional[str], Optional[str]]:
    """YouTube PO Token ve Visitor Data alır."""
    try:
        cookie_arg = ["--cookies", COOKIE_FILE] if Path(COOKIE_FILE).exists() else []
        
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", CHROME_UA,
            *cookie_arg,
            "--extractor-args", "youtube:skip=webpage,dash,hls,dashmanifest",
            "--print", "extractor:potoken",
            "--print", "extractor:visitor_data",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"[PO_TOKEN] Alınamadı: {result.stderr[:150]}")
            return None, None
        
        lines = result.stdout.strip().splitlines()
        po_token = None
        visitor_data = None
        
        for line in lines:
            if line.startswith("po_token="):
                po_token = line.replace("po_token=", "").strip()
            elif line.startswith("visitor_data="):
                visitor_data = line.replace("visitor_data=", "").strip()
        
        if po_token:
            Path(PO_TOKEN_FILE).write_text(po_token, encoding="utf-8")
            print(f"[PO_TOKEN] Token alındı: {po_token[:20]}...")
        if visitor_data:
            Path(VISITOR_DATA_FILE).write_text(visitor_data, encoding="utf-8")
            print(f"[VISITOR_DATA] Visitor Data alındı: {visitor_data[:20]}...")
        
        return po_token, visitor_data
        
    except Exception as e:
        print(f"[PO_TOKEN] Hata: {e}")
        return None, None

def load_po_token() -> Tuple[Optional[str], Optional[str]]:
    """Kaydedilmiş PO Token ve Visitor Data'yı yükler."""
    po_token = None
    visitor_data = None
    
    if Path(PO_TOKEN_FILE).exists():
        po_token = Path(PO_TOKEN_FILE).read_text(encoding="utf-8").strip()
    if Path(VISITOR_DATA_FILE).exists():
        visitor_data = Path(VISITOR_DATA_FILE).read_text(encoding="utf-8").strip()
    
    if po_token:
        print(f"[PO_TOKEN] Kayıtlı token yüklendi: {po_token[:20]}...")
    if visitor_data:
        print(f"[VISITOR_DATA] Kayıtlı visitor data yüklendi: {visitor_data[:20]}...")
    
    return po_token, visitor_data

# ============ YOUTUBE STREAM ALMA ============

def get_youtube_stream_with_po_token(video_url: str, quality: str = "best[height<=1080][fps<=50]/best") -> Optional[str]:
    """PO Token ve Visitor Data kullanarak YouTube stream URL'sini alır."""
    
    # PO Token ve Visitor Data'yı yükle
    po_token, visitor_data = load_po_token()
    
    # Eğer token yoksa almayı dene
    if not po_token:
        po_token, visitor_data = get_po_token_and_visitor_data()
    
    # Cookie kontrolü
    cookie_arg = ["--cookies", COOKIE_FILE] if Path(COOKIE_FILE).exists() else []
    
    # Extractor args oluştur
    extractor_parts = ["youtube:player_client=mweb,android,ios,web"]
    if po_token:
        extractor_parts.append(f"youtube:po_token={po_token}")
    if visitor_data:
        extractor_parts.append(f"youtube:visitor_data={visitor_data}")
    
    extractor_str = ";".join(extractor_parts)
    print(f"   🔑 Extractor: {extractor_str[:100]}...")
    
    # Denenecek yöntemler
    methods = []
    
    # 1. PO Token + mweb (önerilen)
    methods.append({
        "name": "potoken/mweb",
        "cmd": [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", CHROME_UA,
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
            *cookie_arg,
            "--extractor-args", extractor_str,
            "-f", quality,
            "-g",
            video_url
        ]
    })
    
    # 2. Deno + ejs (PO Token ile)
    methods.append({
        "name": "deno/potoken",
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
            "--extractor-args", extractor_str + ";youtube:player_client=mweb",
            "-f", quality,
            "-g",
            video_url
        ]
    })
    
    # 3. Sadece android client
    methods.append({
        "name": "android",
        "cmd": [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", CHROME_UA,
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
            *cookie_arg,
            "--extractor-args", f"youtube:player_client=android",
            "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
            "-g",
            video_url
        ]
    })
    
    # 4. Skip yöntemi
    methods.append({
        "name": "skip/mweb",
        "cmd": [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", CHROME_UA,
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
            *cookie_arg,
            "--extractor-args", "youtube:skip=webpage,dash,hls;youtube:player_client=mweb",
            "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
            "-g",
            video_url
        ]
    })
    
    # 5. Classic (cookiesiz son çare)
    if cookie_arg:
        methods.append({
            "name": "no-cookie/default",
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
        })
    
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
                if "ERROR" in err:
                    print(f"   ⚠️ {err}")
                    
        except subprocess.TimeoutExpired:
            print(f"   ⏱️ {method['name']} zaman aşımı")
        except Exception as e:
            print(f"   ❌ {method['name']} hata: {e}")
    
    print("   ❌ Tüm yöntemler başarısız oldu.")
    return None

# ============ KANAL TİPİ TESPİTİ ============

def get_channel_type(channel: Dict) -> str:
    """Kanal tipini belirler."""
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

def get_eurostar_token() -> Optional[str]:
    """EuroStar TV stream URL'sini alır."""
    try:
        import requests
        headers = {"User-Agent": CHROME_UA}
        html = requests.get("https://www.eurostartv.com.tr/canli-izle", headers=headers, timeout=15).text
        match = re.search(r"var liveUrl = 'https://dygvideo\.dygdigital\.com/live/hls/staravrupa\?token=([a-f0-9]+)';", html)
        if match:
            token = match.group(1)
            token_url = f"https://dygvideo.dygdigital.com/live/hls/staravrupa?token={token}"
            resp = requests.get(token_url, headers=headers, allow_redirects=False, timeout=10)
            if resp.status_code == 302 and "Location" in resp.headers:
                master = resp.headers["Location"]
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

# ============ M3U DOSYA YÖNETİMİ ============

def safe_filename(name: str) -> str:
    """Kanal adını güvenli dosya adına çevirir."""
    replacements = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
        " ": "_", "'": "", '"': "", "?": "", "!": "", ",": "", ".": "",
        ";": "", ":": "", "(": "", ")": "", "[": "", "]": "",
        "{": "", "}": "", "&": ""
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("_")
    return name if name else "kanal"

def update_m3u_file(filepath: Path, stream_url: str) -> bool:
    """M3U dosyasını günceller."""
    try:
        content = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720\n"
            f"{stream_url}\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[HATA] {filepath.name} güncellenemedi: {e}")
        return False

def create_m3u_file(filepath: Path, stream_url: str) -> bool:
    """Yeni M3U dosyası oluşturur."""
    try:
        content = (
            "#EXTM3U\n"
            f"#EXTINF:0,{filepath.stem}\n"
            f"{stream_url}\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[HATA] {filepath.name} oluşturulamadı: {e}")
        return False

def generate_main_playlist() -> bool:
    """Ana playlist'i yeniden oluşturur."""
    try:
        github_base = "https://raw.githubusercontent.com/metvmetv37/senmi/refs/heads/main/playlist"
        output_file = PLAYLIST_DIR / "playerlist.m3u"
        
        files = list(PLAYLIST_DIR.glob("*.m3u"))
        files = [f for f in files if f.name not in ["playerlist.m3u", "playlist.m3u8"]]
        
        lines = ["#EXTM3U"]
        for f in sorted(files):
            name = f.stem.replace("_", " ").strip()
            lines.append(f"#EXTINF:0,{name}")
            lines.append(f"{github_base}/{f.name}")
        
        content = "\n".join(lines) + "\n"
        output_file.write_text(content, encoding="utf-8")
        (PLAYLIST_DIR / "playlist.m3u8").write_text(content, encoding="utf-8")
        
        print(f"[OK] Ana playlist oluşturuldu: {len(files)} kanal")
        return True
    except Exception as e:
        print(f"[HATA] Ana playlist oluşturulamadı: {e}")
        return False

# ============ KANAL İŞLEME ============

def process_channel(channel: Dict, index: int, total: int) -> Tuple[str, bool, Optional[str]]:
    """Tek bir kanalı işler."""
    name = channel.get("name", f"Kanal_{index}")
    url = channel.get("url") or channel.get("youtube_url", "")
    
    print(f"\n🔄 [{index}/{total}] {name}")
    
    if not url:
        print(f"   ⚠️ URL yok, atlanıyor.")
        return (name, False, None)
    
    channel_type = get_channel_type(channel)
    
    if channel_type == "eurostar":
        stream_url = get_eurostar_token()
    elif channel_type == "showturk":
        stream_url = get_showturk_token()
    elif channel_type == "direct":
        stream_url = url
    elif channel_type == "youtube":
        print(f"   📌 YouTube URL: {url}")
        stream_url = get_youtube_stream_with_po_token(url)
    else:
        print(f"   ⚠️ Bilinmeyen kanal tipi, atlanıyor.")
        return (name, False, None)
    
    if stream_url:
        print(f"   ✅ Stream URL alındı: {stream_url[:60]}...")
        return (name, True, stream_url)
    else:
        print(f"   ❌ Stream URL alınamadı!")
        return (name, False, None)

def main() -> int:
    print("=" * 70)
    print(" YOUTUBE STREAM KURTARICI - TAM ÇÖZÜM v2.0")
    print(f" Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 1. Cookie'leri kontrol et
    if not ensure_cookies():
        print("[UYARI] Cookie olmadan devam ediliyor, bazı kanallar çalışmayabilir.")
    
    # 2. PO Token al
    po_token, visitor_data = get_po_token_and_visitor_data()
    if not po_token:
        print("[UYARI] PO Token alınamadı, bazı yöntemler çalışmayabilir.")
    
    # 3. Config yükle
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            channels = config.get("channels", [])
    except Exception as e:
        print(f"[HATA] Config yüklenemedi: {e}")
        return 1
    
    if not channels:
        print("[HATA] config.json'da kanal bulunamadı!")
        return 1
    
    print(f"\n[INFO] {len(channels)} kanal işlenecek.")
    
    # 4. Playlist klasörünü oluştur
    PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
    
    # 5. Tüm kanalları işle (paralel)
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(process_channel, ch, idx, len(channels)): idx
            for idx, ch in enumerate(channels, 1)
        }
        for future in as_completed(futures):
            results.append(future.result())
    
    # 6. Sonuçları işle ve M3U dosyalarını güncelle
    success_count = 0
    for name, success, stream_url in results:
        if not success or not stream_url:
            continue
        
        filename = safe_filename(name)
        m3u_file = PLAYLIST_DIR / f"{filename}.m3u"
        
        if m3u_file.exists():
            update_m3u_file(m3u_file, stream_url)
        else:
            create_m3u_file(m3u_file, stream_url)
        
        success_count += 1
    
    # 7. Ana playlist'i oluştur
    if success_count > 0:
        generate_main_playlist()
    
    # 8. Özet
    print(f"\n" + "=" * 70)
    print(f" İŞLEM TAMAMLANDI")
    print(f" Başarılı: {success_count}/{len(channels)}")
    print(f" Başarısız: {len(channels) - success_count}/{len(channels)}")
    print(f" Bitiş: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
