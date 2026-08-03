#!/usr/bin/env python3

import json
import re
import subprocess
import sys
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.txt"

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/148.0.0.0 Safari/537.36")

def load_config() -> Dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "channels" not in config or not isinstance(config["channels"], list):
        raise ValueError("config.json içinde 'channels' listesi bulunamadı.")

    if not config["channels"]:
        raise ValueError("config.json içinde kanal listesi boş.")

    config.setdefault("quality", "best[height<=1080][fps<=50]/best")
    config.setdefault("output_folder", "playlist")
    config.setdefault("output_playlist", "playerlist.m3u")
    return config

def safe_filename(name: str) -> str:
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
    clean = url.lower().split("?", 1)[0]
    return clean.endswith(".m3u8")

def normalize_channel_name(name: str) -> str:
    """Kanal adını karşılaştırma için normalize eder.

    Config bazen boşluklu ad, bazen alt çizgili ad kullanıyor
    (Euro Star TV / Euro_Star_TV gibi). Bu yüzden token kanalı
    algılamada alt çizgi ve tireleri boşluk kabul ediyoruz.
    """
    return re.sub(r"[_\-]+", " ", name.lower()).strip()

def is_eurostar_name(name: str) -> bool:
    lower = normalize_channel_name(name)
    return "euro star" in lower or "eurostar" in lower or "star avrupa" in lower

def is_show_turk_name(name: str) -> bool:
    lower = normalize_channel_name(name)
    return "show" in lower and ("türk" in lower or "turk" in lower)

def clean_cookie_file(cookie_file: str = COOKIE_FILE) -> bool:
    """Geçersiz cookie'leri temizle ve yeni dosya oluştur."""
    path = Path(cookie_file)
    if not path.exists():
        return False
    
    # Sorunlu cookie'ler
    blocked_cookies = ["CONSISTENCY", "ST-sbra4i", "OTZ", "__Secure-YEC", "__Secure-YENID"]
    
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        
        # Başlıkları ve geçerli cookie'leri tut
        cleaned_lines = []
        header_lines = []
        cookie_lines = []
        
        for line in lines:
            # Başlık satırlarını koru
            if line.startswith("#"):
                header_lines.append(line)
                continue
            
            # Boş satırları atla
            if not line.strip():
                continue
            
            # Cookie'yi kontrol et
            parts = line.split("\t")
            if len(parts) >= 7:
                cookie_name = parts[5].strip()
                # Sorunlu cookie'leri filtrele
                if cookie_name not in blocked_cookies:
                    cookie_lines.append(line)
        
        # Header + cookie'leri birleştir
        cleaned_lines = header_lines + cookie_lines
        
        # Eğer hiç cookie kalmadıysa dosyayı boş bırak
        if not cookie_lines:
            path.write_text("", encoding="utf-8")
            print("   ⚠️ Tüm cookie'ler temizlendi, dosya boşaltıldı")
            return True
        
        # Yeni dosyayı yaz
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

def _run_ytdlp(cmd: List[str], label: str, timeout: int = 140) -> List[str]:
    """yt-dlp çalıştır, çıktıyı temizle ve hata varsa kısa göster."""
    try:
        result = subprocess.run(cmd,
                               capture_output=True,
                               text=True,
                               timeout=timeout,
                               )
    except Exception as e:
        print(f"   ❌ yt-dlp çalıştırılamadı ({label}): {e}")
        return []

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    # Cookie hatasını sessize al
    if stderr and "invalid Netscape format cookies file" not in stderr:
        # GitHub logunu okunabilir tutmak için çok uzunsa kısalt
        short_err = stderr if len(stderr) <= 900 else stderr[:900] + " ..."
        if len(short_err) > 10:  # Sadece anlamlı hataları göster
            print(f"   ⚠️ yt-dlp stderr ({label}): {short_err}")

    if result.returncode != 0:
        # Cookie hatasını ignore et
        if "invalid Netscape format cookies file" in stderr:
            return []
        print(f"   ❌ yt-dlp çıkış kodu ({label}): {result.returncode}")
        return []

    return [line.strip() for line in stdout.splitlines() if line.strip()]

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

def get_youtube_stream_url(youtube_url: str, quality: str) -> Optional[str]:
    """YouTube canlı yayın URL'sini al.

    Cookie hatası durumunda cookie'siz dener.
    """
    # Cookie dosyasını kontrol et ve temizle
    cookie_args: List[str] = []
    cookie_path = Path(COOKIE_FILE)
    
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        # Cookie'leri temizle
        clean_cookie_file(COOKIE_FILE)
        
        # Tekrar kontrol et
        if cookie_path.stat().st_size > 0:
            cookie_args = ["--cookies", COOKIE_FILE]
            print("   🍪 Cookie kullanılıyor")
        else:
            print("   ⚠️ Cookie dosyası boş, cookiesiz devam ediliyor")
    else:
        print("   ⚠️ Cookie dosyası yok veya boş, cookiesiz devam ediliyor")

    common = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--user-agent", CHROME_UA,
        "--referer", "https://www.youtube.com/",
        "--geo-bypass",
        "--socket-timeout", "30",
        *cookie_args,
    ]

    attempts: List[tuple[str, List[str]]] = []

    # 1) Deno + remote ejs + default client (cookie'li veya cookie'siz)
    attempts.append((
        "deno/ejs/default",
        [
            *common,
            "-g",
            "--js-runtimes", "deno",
            "--remote-components", "ejs:github",
            "--extractor-args", "youtube:player_client=default",
            "-f", quality,
            youtube_url,
        ],
    ))

    # 2) Aynı yöntem ama HLS öncelikli format seçimi
    attempts.append((
        "deno/ejs/default/hls",
        [
            *common,
            "-g",
            "--js-runtimes", "deno",
            "--remote-components", "ejs:github",
            "--extractor-args", "youtube:player_client=default",
            "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
            youtube_url,
        ],
    ))

    # 3) Farklı client denemeleri
    for client in ["android", "ios", "web", "tv", "mweb"]:
        attempts.append((
            f"deno/ejs/{client}",
            [
                *common,
                "-g",
                "--js-runtimes", "deno",
                "--remote-components", "ejs:github",
                "--extractor-args", f"youtube:player_client={client}",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                youtube_url,
            ],
        ))

    # 4) Deno olmadan klasik yt-dlp
    for client in ["default", "android", "ios", "web", "tv"]:
        attempts.append((
            f"classic/{client}",
            [
                *common,
                "-g",
                "--extractor-args", f"youtube:player_client={client}",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                youtube_url,
            ],
        ))

    # 5) Son çare: tamamen cookie'siz dene (eğer cookie kullanılıyorsa)
    if cookie_args:
        no_cookie_common = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--user-agent", CHROME_UA,
            "--referer", "https://www.youtube.com/",
            "--geo-bypass",
            "--socket-timeout", "30",
        ]
        attempts.append((
            "no-cookie/default",
            [
                *no_cookie_common,
                "-g",
                "--extractor-args", "youtube:player_client=default",
                "-f", "best[protocol=m3u8_native]/best[protocol=m3u8]/best",
                youtube_url,
            ],
        ))

    for label, cmd in attempts:
        print(f"   ▶️ YouTube deneme: {label}")
        lines = _run_ytdlp(cmd, label)
        stream = _pick_stream_from_lines(lines)
        if stream:
            print(f"   ✅ YouTube stream bulundu: {label}")
            return stream

    print("   ❌ YouTube stream hiçbir yöntemle alınamadı")
    return None

def get_stream_url(channel: Dict, quality: str) -> Optional[str]:
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
    return get_youtube_stream_url(url, quality)

def create_extinf(channel: Dict, stream_url: str) -> str:
    name = channel.get("name", "Unknown")
    return f"#EXTINF:0,{name}\n{stream_url}"

def write_single_channel_file(channel: Dict, stream_url: str, output_folder: Path) -> Path:
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
    """Ana playlisti yazar.

    Show Türk raw .m3u üzerinden açılmadığı için ana listede direkt stream URL kullanılır.
    Diğer kanallar kanal .m3u dosyalarına Raw GitHub linkiyle yazılır.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    github_base = "https://raw.githubusercontent.com/Tahir2020/TR_Avrupa/refs/heads/main/playlist"

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

    try:
        version = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        print(f"ℹ️ yt-dlp sürümü: {version}")
    except Exception as e:
        print(f"⚠️ yt-dlp sürümü okunamadı: {e}")

    # Cookie dosyasını kontrol et ve temizle
    cookie_path = Path(COOKIE_FILE)
    if cookie_path.exists():
        print(f"✅ {COOKIE_FILE} bulundu")
        
        # Cookie'leri temizle
        clean_cookie_file(COOKIE_FILE)
        
        # Cookie bilgilerini göster
        cookie_lines = cookie_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        cookie_count = len([l for l in cookie_lines if l and not l.startswith("#")])
        print(f"📄 Cookie satır sayısı: {len(cookie_lines)}")
        print(f"📄 Geçerli cookie sayısı: {cookie_count}")
        
        if cookie_count > 0:
            if any("youtube.com" in line for line in cookie_lines):
                print("✅ YouTube cookie domain bulundu")
            else:
                print("⚠️ YouTube cookie domain bulunamadı")
        else:
            print("⚠️ Geçerli cookie yok, cookiesiz devam edilecek")
    else:
        print(f"⚠️ {COOKIE_FILE} bulunamadı, cookiesiz devam ediliyor")

    output_folder.mkdir(parents=True, exist_ok=True)

    for pattern in ("*.m3u", "*.m3u8"):
        for old_file in output_folder.glob(pattern):
            old_file.unlink()

    playlist_entries: List[str] = []
    successful_channels: List[Dict] = []
    failed_channels: List[str] = []

    for index, channel in enumerate(config["channels"], start=1):
        name = channel.get("name", f"Kanal {index}")

        if not (channel.get("url") or channel.get("youtube_url")):
            print(f"\n⚠️ [{index}/{len(config['channels'])}] {name}: url/youtube_url yok, atlandı")
            failed_channels.append(name)
            continue

        print(f"\n🔄 [{index}/{len(config['channels'])}] {name} taranıyor...")
        stream_url = get_stream_url(channel, quality)

        if not stream_url:
            print(f"❌ {name}: Stream URL alınamadı")
            failed_channels.append(name)
            continue

        channel["_stream_url"] = stream_url

        single_file = write_single_channel_file(channel, stream_url, output_folder)
        playlist_entries.append(create_extinf(channel, stream_url))
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
