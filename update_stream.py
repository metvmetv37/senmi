#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import subprocess
import sys
import requests
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.txt"

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/148.0.0.0 Safari/537.36")

# YouTube için özel User-Agent'lar
USER_AGENTS = {
    "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "firefox": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "edge": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "safari": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "mobile": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
}

def load_config() -> Dict:
    """Config dosyasını yükler."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "channels" not in config or not isinstance(config["channels"], list):
        raise ValueError("config.json içinde 'channels' listesi bulunamadı.")

    if not config["channels"]:
        raise ValueError("config.json içinde kanal listesi boş.")

    config.setdefault("quality", "best[height<=1080][fps<=50]/best")
    config.setdefault("output_folder", "playlist")
    config.setdefault("output_playlist", "playerlist.m3u")
    config.setdefault("retry_count", 3)
    config.setdefault("delay_between_retries", 5)
    return config

def safe_filename(name: str) -> str:
    """Güvenli dosya adı oluşturur."""
    replacements = {
        "ç": "c", "Ç": "C",
        "ğ": "g", "Ğ": "G",
        "ı": "i", "İ": "I",
        "ö": "o", "Ö": "O",
        "ş": "s", "Ş": "S",
        "ü": "u", "Ü": "U",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return f"{name or 'channel'}.m3u"

def is_direct_m3u8(url: str) -> bool:
    """URL direkt m3u8 mi kontrol eder."""
    clean = url.lower().split("?", 1)[0]
    return clean.endswith(".m3u8")

def normalize_channel_name(name: str) -> str:
    """Kanal adını karşılaştırma için normalize eder."""
    return re.sub(r"[_\-]+", " ", name.lower()).strip()

def is_eurostar_name(name: str) -> bool:
    """EuroStar kanalı mı kontrol eder."""
    lower = normalize_channel_name(name)
    return "euro star" in lower or "eurostar" in lower or "star avrupa" in lower

def is_show_turk_name(name: str) -> bool:
    """Show Türk kanalı mı kontrol eder."""
    lower = normalize_channel_name(name)
    return "show" in lower and ("türk" in lower or "turk" in lower)

def clean_cookie_file(cookie_file: str = COOKIE_FILE) -> bool:
    """
    Cookie dosyasını temizler - SADECE gerçekten sorunlu olanları siler.
    ÖNEMLİ: __Secure-YEC ve __Secure-YENID gibi kritik çerezler KORUNUR.
    """
    path = Path(cookie_file)
    if not path.exists():
        return False
    
    # SADECE gerçekten sorunlu olanlar (çok nadir)
    blocked_cookies = ["OTZ"]  # Sadece OTZ'yi temizle, diğerlerine dokunma
    
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        
        header_lines = []
        cookie_lines = []
        
        for line in lines:
            if line.startswith("#"):
                header_lines.append(line)
                continue
            if not line.strip():
                continue
            
            parts = line.split("\t")
            if len(parts) >= 7:
                cookie_name = parts[5].strip()
                if cookie_name not in blocked_cookies:
                    cookie_lines.append(line)
        
        cleaned_lines = header_lines + cookie_lines
        
        if not cookie_lines:
            path.write_text("", encoding="utf-8")
            print("   ⚠️ Tüm cookie'ler temizlendi, dosya boşaltıldı")
            return True
        
        path.write_text("\n".join(cleaned_lines), encoding="utf-8")
        print(f"   ✅ Cookie dosyası temizlendi: {len(cookie_lines)} cookie korundu")
        return True
        
    except Exception as e:
        print(f"   ⚠️ Cookie temizleme hatası: {e}")
        return False

def load_netscape_cookies(cookie_file: str = COOKIE_FILE) -> Dict[str, str]:
    """Netscape format cookies.txt dosyasını requests cookies dict formatına çevirir."""
    cookies: Dict[str, str] = {}
    path = Path(cookie_file)

    if not path.exists():
        print(f"   ℹ️ {cookie_file} bulunamadı, cookiesiz devam ediliyor")
        return cookies

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) >= 7:
                    name = parts[5].strip()
                    value = parts[6].strip()
                    if name:
                        cookies[name] = value

        if cookies:
            print(f"   🍪 {len(cookies)} cookie yüklendi")
        else:
            print("   ⚠️ cookies.txt var ama okunabilir cookie bulunamadı")

    except Exception as e:
        print(f"   ⚠️ Cookie okuma hatası: {e}")

    return cookies

def get_eurostar_token() -> Optional[str]:
    """EuroStar 1080p - HTML'den token çek."""
    headers = {
        "User-Agent": CHROME_UA,
        "Accept": "text/html,application/xhtml+xml",
    }

    page_url = "https://www.eurostartv.com.tr/canli-izle"

    try:
        response = requests.get(page_url, headers=headers, timeout=15)
        html = response.text

        pattern = r"var liveUrl = 'https://dygvideo\.dygdigital\.com/live/hls/staravrupa\?token=([a-f0-9]+)';"
        match = re.search(pattern, html)

        if not match:
            print("   ❌ EuroStar token HTML'de bulunamadı")
            return None

        token = match.group(1)
        token_url = f"https://dygvideo.dygdigital.com/live/hls/staravrupa?token={token}"

        headers2 = {
            "Origin": "https://www.eurostartv.com.tr",
            "Referer": "https://www.eurostartv.com.tr/",
            "User-Agent": CHROME_UA,
        }

        response2 = requests.get(token_url, headers=headers2, allow_redirects=False, timeout=10)

        if response2.status_code == 302:
            master_url = response2.headers.get("Location")
            if not master_url:
                print("   ❌ EuroStar Location header boş")
                return None

            match = re.match(r"(.*/)live\.m3u8\?(.*)", master_url)
            if match:
                stream_url = f"{match.group(1)}live_1080p3000000kbps/index.m3u8?{match.group(2)}"
                print("   ✅ EuroStar 1080p token alındı")
                return stream_url

            print("   ✅ EuroStar master URL alındı")
            return master_url

        print(f"   ❌ EuroStar redirect alınamadı: {response2.status_code}")
        return None

    except Exception as e:
        print(f"   ❌ EuroStar hatası: {e}")
        return None

def get_show_turk_token() -> Optional[str]:
    """Show Türk - otomatik token alıcı."""
    url = "https://www.showturk.com.tr/canli-yayin"
    pattern = r'playlist\.m3u8\?e=(\d+)&st=([^"\s&]+)'

    headers = {
        "User-Agent": CHROME_UA,
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        html = response.text
        match = re.search(pattern, html)

        if match:
            e, st = match.groups()
            stream_url = f"https://ciner-live.ercdn.net/showturk/playlist.m3u8?e={e}&st={st}&tv=1"
            print("   ✅ Show Türk token alındı")
            return stream_url

        print("   ❌ Show Türk token bulunamadı")
        return None

    except Exception as e:
        print(f"   ❌ Show Türk hatası: {e}")
        return None

def _run_ytdlp(cmd: List[str], label: str, timeout: int = 140) -> Tuple[List[str], bool]:
    """
    yt-dlp çalıştır, çıktıyı temizle.
    Returns: (lines, is_bot_error)
    """
    is_bot_error = False
    
    try:
        result = subprocess.run(cmd,
                               capture_output=True,
                               text=True,
                               timeout=timeout,
                               )
    except subprocess.TimeoutExpired:
        print(f"   ⏱️ Zaman aşımı ({label})")
        return [], False
    except Exception as e:
        print(f"   ❌ yt-dlp çalıştırılamadı ({label}): {e}")
        return [], False

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    # Bot hatasını tespit et
    if stderr:
        if "Sign in to confirm" in stderr or "bot" in stderr.lower():
            is_bot_error = True
            # Bot hatasını kısa göster
            print(f"   ⚠️ {label}: YouTube doğrulama hatası (cookie geçersiz olabilir)")
        elif "invalid Netscape format" in stderr:
            pass  # Bu hatayı yoksay
        elif len(stderr) > 0:
            # Diğer hataları kısaca göster
            short_err = stderr if len(stderr) <= 500 else stderr[:500] + " ..."
            if "ERROR" in stderr or "error" in stderr.lower():
                print(f"   ⚠️ yt-dlp stderr ({label}): {short_err}")

    if result.returncode != 0:
        return [], is_bot_error

    return [line.strip() for line in stdout.splitlines() if line.strip()], is_bot_error

def _pick_stream_from_lines(lines: List[str]) -> Optional[str]:
    """yt-dlp -g çıktısından oynatılabilir URL seç."""
    if not lines:
        return None

    # Öncelik HLS / manifest
    for line in lines:
        if line.startswith("http") and (".m3u8" in line or "manifest" in line):
            return line

    # Bazı canlı yayınlarda yt-dlp direkt googlevideo URL döndürür
    for line in lines:
        if line.startswith("http"):
            return line

    return None

def get_youtube_stream_url(youtube_url: str, quality: str, retry_count: int = 3) -> Optional[str]:
    """
    YouTube canlı yayın URL'sini al.
    Bot hatası durumunda farklı yöntemlerle yeniden dener.
    """
    cookie_path = Path(COOKIE_FILE)
    
    # Cookie dosyasını kontrol et
    cookie_args: List[str] = []
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        cookie_args = ["--cookies", COOKIE_FILE]
        print("   🍪 Cookie kullanılıyor")
    else:
        print("   ⚠️ Cookie dosyası yok veya boş, cookiesiz devam ediliyor")

    # Farklı User-Agent'lar ile dene
    user_agents_to_try = [
        ("chrome", USER_AGENTS["chrome"]),
        ("firefox", USER_AGENTS["firefox"]),
        ("edge", USER_AGENTS["edge"]),
        ("mobile", USER_AGENTS["mobile"]),
    ]

    # Client kombinasyonları
    client_combinations = [
        ("mweb,default", "mweb+default"),
        ("mweb,ios", "mweb+ios"),
        ("android,mweb", "android+mweb"),
        ("android,ios", "android+ios"),
        ("android", "android"),
        ("ios", "ios"),
        ("web", "web"),
        ("tv", "tv"),
        ("default", "default"),
    ]

    # Tüm denemeleri topla
    all_attempts: List[Tuple[str, List[str]]] = []

    for ua_label, ua_string in user_agents_to_try:
        base_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", ua_string,
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
            "--sleep-interval", "2",
            *cookie_args,
        ]

        for client_str, client_label in client_combinations:
            # Önce HLS formatını dene
            all_attempts.append((
                f"{ua_label}/{client_label}/hls",
                [
                    *base_cmd,
                    "-g",
                    "--extractor-args", f"youtube:player-client={client_str}",
                    "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                    youtube_url,
                ],
            ))

            # Sonra genel formatı dene
            all_attempts.append((
                f"{ua_label}/{client_label}/best",
                [
                    *base_cmd,
                    "-g",
                    "--extractor-args", f"youtube:player-client={client_str}",
                    "-f", quality,
                    youtube_url,
                ],
            ))

    # PO Token ile dene (eğer varsa)
    po_token = os.environ.get("YOUTUBE_PO_TOKEN", "")
    if po_token:
        for ua_label, ua_string in user_agents_to_try[:2]:  # Sadece chrome ve firefox
            all_attempts.append((
                f"{ua_label}/po-token",
                [
                    "yt-dlp",
                    "--no-playlist",
                    "--no-warnings",
                    "--user-agent", ua_string,
                    "--referer", "https://www.youtube.com/",
                    "--geo-bypass",
                    "--socket-timeout", "30",
                    *cookie_args,
                    "-g",
                    "--extractor-args", f"youtube:player-client=web,default;po_token={po_token}",
                    "-f", "best",
                    youtube_url,
                ],
            ))

    # Cookie'siz deneme (eğer cookie varsa)
    if cookie_args:
        no_cookie_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", USER_AGENTS["chrome"],
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
            "--sleep-interval", "2",
            "-g",
            "--extractor-args", "youtube:player-client=default",
            "-f", "best",
            youtube_url,
        ]
        all_attempts.append(("no-cookie/default", no_cookie_cmd))

    # Denemeleri yap
    attempted = 0
    bot_errors = 0
    
    for label, cmd in all_attempts:
        if attempted >= retry_count * 10:  # Maksimum deneme
            break
            
        print(f"   ▶️ YouTube deneme: {label}")
        lines, is_bot_error = _run_ytdlp(cmd, label)
        
        if is_bot_error:
            bot_errors += 1
            if bot_errors > 5:  # Çok fazla bot hatası varsa
                print("   ⚠️ Çok fazla bot hatası, cookie yenilenmeli")
                break
            time.sleep(1)  # Bot hatası sonrası bekle
            continue
            
        stream = _pick_stream_from_lines(lines)
        if stream:
            print(f"   ✅ YouTube stream bulundu: {label}")
            return stream
            
        attempted += 1
        time.sleep(0.5)  # Denemeler arası bekle

    # Hiçbir yöntem çalışmadıysa, son bir kez cookie'siz dene
    if cookie_args:
        print("   🔄 Son çare: Cookie'siz deneme...")
        final_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", USER_AGENTS["firefox"],
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
            "-g",
            "--extractor-args", "youtube:player-client=android",
            "-f", "best",
            youtube_url,
        ]
        lines, _ = _run_ytdlp(final_cmd, "final-no-cookie")
        stream = _pick_stream_from_lines(lines)
        if stream:
            print("   ✅ YouTube stream bulundu: final-no-cookie")
            return stream

    print("   ❌ YouTube stream hiçbir yöntemle alınamadı")
    return None

def get_stream_url(channel: Dict, quality: str, retry_count: int = 3) -> Optional[str]:
    """Kanal tipine göre stream URL'sini al."""
    channel_name = channel.get("name", "")

    if is_eurostar_name(channel_name):
        print("🔐 EuroStar için token alınıyor...")
        return get_eurostar_token()

    if is_show_turk_name(channel_name):
        print("🔐 Show Türk için token alınıyor...")
        return get_show_turk_token()

    url = channel.get("url") or channel.get("youtube_url")

    if not url:
        return None

    if is_direct_m3u8(url):
        print("🔗 Direkt m3u8 linki kullanılıyor")
        return url

    print("🎬 YouTube stream alınıyor...")
    return get_youtube_stream_url(url, quality, retry_count)

def create_extinf(channel: Dict, stream_url: str) -> str:
    """EXTINF satırı oluşturur."""
    name = channel.get("name", "Unknown")
    return f"#EXTINF:0,{name}\n{stream_url}"

def write_single_channel_file(channel: Dict, stream_url: str, output_folder: Path) -> Path:
    """Her kanal için ayrı M3U dosyası oluşturur."""
    output_folder.mkdir(parents=True, exist_ok=True)

    filename = channel.get("m3u_file") or safe_filename(channel["name"])
    path = output_folder / filename

    name = channel.get("name", "Unknown")

    # SADECE Show Türk
    if is_show_turk_name(name):
        content = (
            "#EXTM3U\n"
            "#EXTVLCOPT:http-referrer=https://www.showturk.com.tr/\n"
            "#EXTINF:-1,Show Türk\n"
            f"{stream_url}\n"
        )
    
    # SADECE Kanal Euro D
    elif name == "Kanal_Euro_D":
        content = "#EXTM3U\n"
        content += f"#EXTINF:0,{name}\n"
        content += f"{stream_url}\n"
    
    # Diğer tüm kanallar eski HLS formatında
    else:
        content = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720\n"
            f"{stream_url}\n"
        )

    path.write_text(content, encoding="utf-8")
    return path

def playlist_display_name(channel: Dict) -> str:
    """Ana playlistte görünecek kanal adını dosya adına göre üretir."""
    filename = channel.get("m3u_file") or safe_filename(channel.get("name", "channel"))
    return re.sub(r"\.m3u8?$", "", filename, flags=re.IGNORECASE)

def write_main_playlist(channels: List[Dict], output_folder: Path, output_playlist: str) -> Path:
    """Ana playlisti yazar."""
    output_folder.mkdir(parents=True, exist_ok=True)

    github_base = "https://raw.githubusercontent.com/metvmetv37/senmi/refs/heads/main/playlist"

    lines = ["#EXTM3U"]

    for channel in channels:
        filename = channel.get("m3u_file") or safe_filename(channel.get("name", "channel"))
        display_name = playlist_display_name(channel)

        lines.append(f"#EXTINF:0,{display_name}")

        # Show Türk ana listede direkt stream olarak yazılır.
        if is_show_turk_name(channel.get("name", "")) and channel.get("_stream_url"):
            lines.append(channel["_stream_url"])
        else:
            lines.append(f"{github_base}/{filename}")

    content = "\n".join(lines) + "\n"

    path = output_folder / output_playlist
    path.write_text(content, encoding="utf-8")

    aliases = {"playerlist.m3u", "playlist.m3u8"}
    aliases.discard(output_playlist)

    for alias in sorted(aliases):
        (output_folder / alias).write_text(content, encoding="utf-8")

    return path

def main() -> int:
    """Ana fonksiyon."""
    print("=" * 60)
    print("🎬 TV Kanalları M3U Güncelleyici (Token + Cookie Desteği)")
    print("=" * 60)
    print(f"🕐 Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Config okunamadı: {e}")
        return 1

    quality = config["quality"]
    output_folder = Path(config["output_folder"])
    output_playlist = config["output_playlist"]
    retry_count = config.get("retry_count", 3)

    try:
        version = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        print(f"ℹ️ yt-dlp sürümü: {version}")
    except Exception as e:
        print(f"⚠️ yt-dlp sürümü okunamadı: {e}")

    # Cookie dosyasını kontrol et
    cookie_path = Path(COOKIE_FILE)
    if cookie_path.exists():
        print(f"✅ {COOKIE_FILE} bulundu")
        
        # Cookie'leri temizle (SADECE OTZ'yi sil)
        clean_cookie_file(COOKIE_FILE)
        
        # Cookie bilgilerini göster
        cookie_lines = cookie_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        cookie_count = len([l for l in cookie_lines if l and not l.startswith("#")])
        print(f"📄 Cookie satır sayısı: {len(cookie_lines)}")
        print(f"📄 Geçerli cookie sayısı: {cookie_count}")
        
        if cookie_count > 0:
            youtube_cookies = [l for l in cookie_lines if "youtube.com" in l.lower()]
            if youtube_cookies:
                print(f"✅ YouTube cookie domain bulundu ({len(youtube_cookies)} adet)")
            else:
                print("⚠️ YouTube cookie domain bulunamadı")
        else:
            print("⚠️ Geçerli cookie yok, cookiesiz devam edilecek")
    else:
        print(f"⚠️ {COOKIE_FILE} bulunamadı, cookiesiz devam ediliyor")
        print("💡 İpucu: YouTube için cookies.txt oluşturmak için:")
        print("   1. Tarayıcıda gizli pencere açıp YouTube'a giriş yapın")
        print("   2. https://www.youtube.com/robots.txt adresini açın")
        print("   3. 'Get cookies.txt LOCALLY' eklentisiyle dışa aktarın")

    output_folder.mkdir(parents=True, exist_ok=True)

    # Eski dosyaları temizle
    for pattern in ("*.m3u", "*.m3u8"):
        for old_file in output_folder.glob(pattern):
            old_file.unlink()

    successful_channels: List[Dict] = []
    failed_channels: List[str] = []

    for index, channel in enumerate(config["channels"], start=1):
        name = channel.get("name", f"Kanal {index}")

        if not (channel.get("url") or channel.get("youtube_url")):
            print(f"\n⚠️ [{index}/{len(config['channels'])}] {name}: url/youtube_url yok, atlandı")
            failed_channels.append(name)
            continue

        print(f"\n🔄 [{index}/{len(config['channels'])}] {name} taranıyor...")
        
        # Her kanal için yeniden dene
        stream_url = None
        for attempt in range(retry_count):
            if attempt > 0:
                print(f"   🔄 Yeniden deneme {attempt+1}/{retry_count}...")
                time.sleep(config.get("delay_between_retries", 5))
            
            stream_url = get_stream_url(channel, quality, retry_count)
            if stream_url:
                break

        if not stream_url:
            print(f"❌ {name}: Stream URL alınamadı")
            failed_channels.append(name)
            continue

        channel["_stream_url"] = stream_url

        single_file = write_single_channel_file(channel, stream_url, output_folder)
        successful_channels.append(channel)
        print(f"✅ {name}: {single_file} oluşturuldu")

    if successful_channels:
        main_playlist = write_main_playlist(successful_channels, output_folder, output_playlist)
        print(f"\n✅ Toplu liste oluşturuldu: {main_playlist}")
        print(f"✅ Başarılı kanal sayısı: {len(successful_channels)}/{len(config['channels'])}")
    else:
        print("\n❌ Hiçbir kanal için link alınamadı")
        return 1

    if failed_channels:
        print("\n⚠️ Alınamayan kanallar:")
        for channel_name in failed_channels:
            print(f"   - {channel_name}")

    print(f"\n📄 Oluşan M3U dosyaları ({output_folder}/):")
    for file in sorted(output_folder.glob("*.m3u")):
        print(f"   - {file.name}")

    print(f"\n✅ İşlem tamamlandı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
