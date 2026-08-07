#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOUTUBE PO TOKEN & COOKIE BYPASS - TAM ÇÖZÜM
YouTube'un bot korumasını aşmak için PO Token, Visitor Data ve çoklu client desteği.
"""

import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime

# ============ KONFIGÜRASYON ============
COOKIE_FILE = "cookies.txt"
PO_TOKEN_FILE = "po_token.txt"  # PO Token dosyası
VISITOR_DATA_FILE = "visitor_data.json"  # Visitor Data dosyası
CONFIG_FILE = "config.json"
PLAYLIST_DIR = Path("playlist")
BROWSER = "chrome"  # chrome, firefox, brave, edge, opera

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

# ============ PO TOKEN VE VISITOR DATA ALMA ============

def get_po_token_and_visitor_data() -> Tuple[Optional[str], Optional[str]]:
    """
    YouTube PO Token ve Visitor Data alır.
    yt-dlp'nin --extractor-args ile kullanabileceği format.
    """
    try:
        # yt-dlp ile PO Token al
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", CHROME_UA,
            "--cookies-from-browser", BROWSER,
            "--extractor-args", "youtube:skip=webpage,dash,hls,dashmanifest",
            "--print", "extractor:url",
            "--print", "extractor:potoken",
            "--print", "extractor:visitor_data",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"[HATA] PO Token alınamadı: {result.stderr[:200]}")
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
            print(f"[PO_TOKEN] Token alındı: {po_token[:20]}...")
            # Token'ı dosyaya kaydet
            Path(PO_TOKEN_FILE).write_text(po_token, encoding="utf-8")
        if visitor_data:
            print(f"[VISITOR_DATA] Visitor Data alındı: {visitor_data[:20]}...")
            Path(VISITOR_DATA_FILE).write_text(visitor_data, encoding="utf-8")
        
        return po_token, visitor_data
        
    except Exception as e:
        print(f"[HATA] PO Token alınamadı: {e}")
        return None, None

def export_cookies_from_browser() -> bool:
    """
    Tarayıcıdan YouTube cookie'lerini güvenli şekilde çeker.
    Gizli pencere yöntemi önerilir.
    """
    print("[COOKIE] Tarayıcıdan cookie çekiliyor...")
    
    # 1. yt-dlp ile dene
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
            return True
    except Exception as e:
        print(f"[COOKIE] yt-dlp ile çekilemedi: {e}")
    
    # 2. Alternatif: Extension ile manuel export (kullanıcıya yönlendir)
    print("\n[MANUEL] Cookie export edilemedi. Lütfen şu adımları izleyin:")
    print("   1) Chrome'da 'Get cookies.txt LOCALLY' eklentisini yükleyin.")
    print("   2) YouTube'a giriş yapın ve cookie'leri export edin.")
    print("   3) Export edilen dosyayı 'cookies.txt' olarak kaydedin.")
    print("   4) Gizli pencere kullanın ve sadece YouTube sekmesi açık olsun.")
    
    input("\nCookie dosyasını kaydettikten sonra ENTER tuşuna basın...")
    
    if Path(COOKIE_FILE).exists() and Path(COOKIE_FILE).stat().st_size > 100:
        print("[COOKIE] Manuel cookie dosyası bulundu.")
        return True
    else:
        print("[HATA] Cookie dosyası hala mevcut değil.")
        return False

# ============ YOUTUBE STREAM ALMA (PO TOKEN DESTEKLİ) ============

def get_youtube_stream_with_po_token(video_url: str, quality: str = "best[height<=1080][fps<=50]/best") -> Optional[str]:
    """
    PO Token ve Visitor Data kullanarak YouTube stream URL'sini alır.
    """
    # PO Token ve Visitor Data'yı oku
    po_token = None
    visitor_data = None
    
    if Path(PO_TOKEN_FILE).exists():
        po_token = Path(PO_TOKEN_FILE).read_text(encoding="utf-8").strip()
    if Path(VISITOR_DATA_FILE).exists():
        visitor_data = Path(VISITOR_DATA_FILE).read_text(encoding="utf-8").strip()
    
    # Eğer token yoksa almayı dene
    if not po_token:
        po_token, visitor_data = get_po_token_and_visitor_data()
    
    # Cookie kontrolü
    cookie_arg = ["--cookies", COOKIE_FILE] if Path(COOKIE_FILE).exists() else []
    if not cookie_arg:
        print("   ⚠️ Cookie yok, sadece PO Token ile deneniyor.")
    
    # Extractor args: PO Token ve Visitor Data
    extractor_args = []
    if po_token:
        extractor_args.append(f"youtube:po_token={po_token}")
    if visitor_data:
        extractor_args.append(f"youtube:visitor_data={visitor_data}")
    # mweb client önerilir
    extractor_args.append("youtube:player_client=mweb,android,ios,web")
    
    extractor_str = ",".join(extractor_args)
    print(f"   🔑 Extractor args: {extractor_str[:80]}...")
    
    # Denenecek yöntemler
    methods = [
        # 1. PO Token + mweb client
        {
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
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 2. PO Token + android client
        {
            "name": "potoken/android",
            "cmd": [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--user-agent", CHROME_UA,
                "--referer", "https://www.youtube.com/",
                "--geo-bypass",
                "--socket-timeout", "30",
                *cookie_arg,
                "--extractor-args", f"youtube:po_token={po_token};youtube:visitor_data={visitor_data};youtube:player_client=android",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 3. Deno + ejs (PO Token ile)
        {
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
                "--extractor-args", f"youtube:po_token={po_token};youtube:visitor_data={visitor_data};youtube:player_client=mweb",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                "-g",
                video_url
            ]
        },
        # 4. Son çare: mweb + skip web sayfası
        {
            "name": "mweb/skip",
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
        }
    ]
    
    for method in methods:
        try:
            print(f"   ▶️ {method['name']}")
            result = subprocess.run(
                method["cmd"],
                capture_output=True,
                text=True,
                timeout=120
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

# ============ M3U DOSYALARINI GÜNCELLE ============

def update_m3u_file(filepath: Path, stream_url: str) -> bool:
    """M3U dosyasını günceller."""
    if not filepath.exists():
        return False
    try:
        content = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720\n" + stream_url
        filepath.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[HATA] {filepath.name} güncellenemedi: {e}")
        return False

# ============ ANA FONKSİYON ============

def main() -> int:
    print("=" * 70)
    print(" YOUTUBE PO TOKEN KURTARICI - M3U GÜNCELLEYİCİ")
    print(f" Başlangıç: {datetime.now().strftime('%Y-%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 1. Cookie'leri kontrol et
    if not Path(COOKIE_FILE).exists():
        print("[INFO] Cookie dosyası yok, tarayıcıdan çekiliyor...")
        if not export_cookies_from_browser():
            print("[UYARI] Cookie alınamadı, sadece PO Token ile devam ediliyor.")
    
    # 2. PO Token al
    po_token, visitor_data = get_po_token_and_visitor_data()
    if not po_token:
        print("[UYARI] PO Token alınamadı, klasik yöntem deneniyor.")
    
    # 3. Config yükle
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            channels = config.get("channels", [])
    except Exception as e:
        print(f"[HATA] Config yüklenemedi: {e}")
        return 1
    
    # 4. Sadece YouTube kanallarını işle
    success_count = 0
    for idx, channel in enumerate(channels, 1):
        name = channel.get("name", f"Kanal_{idx}")
        url = channel.get("url") or channel.get("youtube_url", "")
        
        if not url or "youtube.com" not in url:
            print(f"\n⏭️ [{idx}/{len(channels)}] {name} -> YouTube değil, atlanıyor.")
            continue
        
        print(f"\n🔄 [{idx}/{len(channels)}] {name}")
        print(f"   📌 URL: {url}")
        
        # Stream URL al
        stream_url = get_youtube_stream_with_po_token(url)
        
        if stream_url:
            # M3U dosyasını güncelle
            filename = safe_filename(name)
            m3u_file = PLAYLIST_DIR / f"{filename}.m3u"
            if update_m3u_file(m3u_file, stream_url):
                print(f"   ✅ {m3u_file.name} güncellendi.")
                success_count += 1
            else:
                print(f"   ❌ {m3u_file.name} güncellenemedi.")
        else:
            print(f"   ❌ Stream URL alınamadı.")
    
    print(f"\n[OK] {success_count} YouTube kanalı güncellendi.")
    return 0

def safe_filename(name: str) -> str:
    replacements = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
        " ": "_", "'": "", '"': "", "?": "", "!": "", ",": "", ".": "",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("_")
    return name if name else "kanal"

if __name__ == "__main__":
    sys.exit(main())
