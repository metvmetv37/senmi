#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U PLAYLIST YENİDEN OLUŞTURUCU - TAM KOD
Tüm .m3u dosyalarını tarar, playerlist.m3u'yu tamamen yeniden oluşturur.
Eksik kanalları, boş satırları temizler, geçersiz URL'leri filtreler.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set

# ============ KONFIGÜRASYON ============
PLAYLIST_DIR = Path("playlist")
OUTPUT_FILE = PLAYLIST_DIR / "playerlist.m3u"
BACKUP_FILE = PLAYLIST_DIR / "playerlist.m3u.bak"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/metvmetv37/senmi/refs/heads/main/playlist"

# Özel kanallar - doğrudan stream URL kullanılacak (dosya referansı değil)
DIRECT_STREAM_CHANNELS = {"Show_Turk", "Show_Max"}  # Show_Max da token gerektiriyorsa ekle

# Show_Turk token yenileme URL'si
SHOWTURK_PAGE = "https://www.showturk.com.tr/canli-yayin"
SHOWTURK_PATTERN = r'playlist\.m3u8\?e=(\d+)&st=([^"\s&]+)'

# ============ YARDIMCI FONKSİYONLAR ============

def safe_filename(name: str) -> str:
    """Kanal adını güvenli dosya adına çevirir."""
    replacements = {
        "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G",
        "ı": "i", "İ": "I", "ö": "o", "Ö": "O",
        "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
        " ": "_", "'": "", '"': "", "?": "", "!": "",
        ",": "", ".": "", ";": "", ":": "", "(": "", ")": "",
        "[": "", "]": "", "{": "", "}": ""
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("_")
    return name if name else "kanal"

def get_showturk_token() -> Optional[str]:
    """Show Türk için güncel token alır."""
    try:
        import requests
    except ImportError:
        print("[HATA] requests modülü yüklü değil. 'pip install requests'")
        return None
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        resp = requests.get(SHOWTURK_PAGE, headers=headers, timeout=15)
        html = resp.text
        match = re.search(SHOWTURK_PATTERN, html)
        if match:
            e, st = match.groups()
            return f"https://ciner-live.ercdn.net/showturk/playlist.m3u8?e={e}&st={st}&tv=1"
        print("[UYARI] Show Türk token bulunamadı, eski URL kullanılacak.")
        return None
    except Exception as e:
        print(f"[HATA] Show Türk token alınamadı: {e}")
        return None

def get_channel_name_from_file(filepath: Path) -> str:
    """Dosya adından kanal adını çıkarır (uzantısız)."""
    return filepath.stem

def is_valid_m3u_file(filepath: Path) -> bool:
    """Geçerli bir .m3u dosyası mı kontrol eder (playerlist ve playlist hariç)."""
    if filepath.name in ["playerlist.m3u", "playlist.m3u8"]:
        return False
    if not filepath.suffix.lower() in [".m3u", ".m3u8"]:
        return False
    if filepath.stat().st_size < 10:  # Çok küçük dosyaları atla
        return False
    return True

def read_m3u_content(filepath: Path) -> Optional[str]:
    """M3U dosyasını okur, ilk geçerli stream URL'sini döndürür."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                if line.startswith("http://") or line.startswith("https://"):
                    return line
        return None
    except Exception as e:
        print(f"[HATA] {filepath.name} okunamadı: {e}")
        return None

def generate_main_playlist(channel_files: List[Path], direct_streams: Dict[str, str]) -> str:
    """
    Ana playlist içeriğini oluşturur.
    - channel_files: playlist klasöründeki tüm .m3u dosyaları
    - direct_streams: doğrudan URL kullanılacak kanallar {kanal_adı: stream_url}
    """
    lines = ["#EXTM3U"]
    processed_names: Set[str] = set()
    
    # Önce doğrudan stream kanallarını ekle
    for name, url in direct_streams.items():
        if url and name not in processed_names:
            lines.append(f"#EXTINF:0,{name}")
            lines.append(url)
            processed_names.add(name)
            print(f"[EKLE] {name} -> doğrudan stream")
    
    # Sonra tüm .m3u dosyalarını tara
    for filepath in sorted(channel_files):
        if not is_valid_m3u_file(filepath):
            continue
        
        name = get_channel_name_from_file(filepath)
        
        # Zaten eklendiyse atla
        if name in processed_names:
            continue
        
        # Dosya içeriğini kontrol et
        stream_url = read_m3u_content(filepath)
        if not stream_url:
            print(f"[UYARI] {filepath.name} içinde geçerli URL yok, atlanıyor.")
            continue
        
        # Dosya adı ve kanal adını normalize et
        display_name = name.replace("_", " ").strip()
        
        # GitHub raw URL'si oluştur
        raw_url = f"{GITHUB_RAW_BASE}/{filepath.name}"
        
        lines.append(f"#EXTINF:0,{display_name}")
        lines.append(raw_url)
        processed_names.add(name)
        print(f"[EKLE] {display_name} -> {filepath.name}")
    
    return "\n".join(lines) + "\n"

def backup_existing(output_file: Path) -> bool:
    """Mevcut playlist'i yedekler."""
    if output_file.exists():
        try:
            backup_path = output_file.with_suffix(".m3u.bak")
            backup_path.write_text(output_file.read_text(encoding="utf-8"))
            print(f"[YEDEK] {output_file.name} -> {backup_path.name}")
            return True
        except Exception as e:
            print(f"[HATA] Yedekleme başarısız: {e}")
    return False

def fix_show_turk_entry(content: str) -> str:
    """Show_Turk entry'sini günceller (token yeniler)."""
    token_url = get_showturk_token()
    if not token_url:
        return content
    
    lines = content.splitlines()
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        # Show_Turk satırını bul
        if "#EXTINF" in line and "Show_Turk" in line:
            # Bir sonraki satır URL ise değiştir
            if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                new_lines.append(token_url)
                i += 1  # Eski URL'yi atla
                print("[GÜNCELLE] Show_Turk token yenilendi.")
        i += 1
    
    return "\n".join(new_lines)

def fix_show_max_entry(content: str) -> str:
    """Show_Max entry'sini düzeltir - direkt stream URL kullan."""
    # Show_Max genelde YouTube stream'i olduğu için URL'sini bulmaya çalış
    # Eğer playerlist'te Show_Max varsa ve .m3u dosyası mevcutsa içindeki URL'yi kullan
    show_max_file = PLAYLIST_DIR / "Show_Max.m3u"
    if show_max_file.exists():
        stream_url = read_m3u_content(show_max_file)
        if stream_url:
            lines = content.splitlines()
            new_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                new_lines.append(line)
                if "#EXTINF" in line and "Show_Max" in line:
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        new_lines.append(stream_url)
                        i += 1
                        print("[GÜNCELLE] Show_Max URL güncellendi.")
                i += 1
            return "\n".join(new_lines)
    return content

def main() -> int:
    print("=" * 70)
    print(" M3U PLAYLIST YENİDEN OLUŞTURUCU v2.0")
    print(f" Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 1. Playlist klasörünü kontrol et
    if not PLAYLIST_DIR.exists():
        print(f"[HATA] {PLAYLIST_DIR} klasörü bulunamadı!")
        return 1
    
    # 2. Tüm M3U dosyalarını tara
    m3u_files = list(PLAYLIST_DIR.glob("*.m3u")) + list(PLAYLIST_DIR.glob("*.m3u8"))
    m3u_files = [f for f in m3u_files if is_valid_m3u_file(f)]
    
    print(f"\n[INFO] {len(m3u_files)} adet M3U dosyası bulundu.")
    for f in sorted(m3u_files):
        print(f"   - {f.name}")
    
    # 3. Doğrudan stream kanallarını belirle
    direct_streams: Dict[str, str] = {}
    
    # Show_Turk: token yenile
    showturk_url = get_showturk_token()
    if showturk_url:
        direct_streams["Show_Turk"] = showturk_url
    else:
        # Yedek: Show_Turk.m3u dosyasından oku
        showturk_file = PLAYLIST_DIR / "Show_Turk.m3u"
        if showturk_file.exists():
            url = read_m3u_content(showturk_file)
            if url:
                direct_streams["Show_Turk"] = url
    
    # Show_Max: .m3u dosyasından oku
    showmax_file = PLAYLIST_DIR / "Show_Max.m3u"
    if showmax_file.exists():
        url = read_m3u_content(showmax_file)
        if url:
            direct_streams["Show_Max"] = url
    
    # 4. Yedek al
    if OUTPUT_FILE.exists():
        backup_existing(OUTPUT_FILE)
    
    # 5. Ana playlist'i oluştur
    content = generate_main_playlist(m3u_files, direct_streams)
    
    # 6. Özel düzeltmeler
    content = fix_show_turk_entry(content)
    content = fix_show_max_entry(content)
    
    # 7. Dosyayı yaz
    try:
        OUTPUT_FILE.write_text(content, encoding="utf-8")
        print(f"\n[OK] {OUTPUT_FILE} başarıyla oluşturuldu.")
        print(f"   - Boyut: {OUTPUT_FILE.stat().st_size} bayt")
        print(f"   - Satır sayısı: {len(content.splitlines())}")
    except Exception as e:
        print(f"[HATA] Dosya yazılamadı: {e}")
        return 1
    
    # 8. İstatistik
    lines = content.splitlines()
    extinf_count = sum(1 for line in lines if line.startswith("#EXTINF"))
    url_count = sum(1 for line in lines if line.startswith("http"))
    
    print(f"\n[İSTATİSTİK]")
    print(f"   - Toplam kanal: {extinf_count}")
    print(f"   - Geçerli URL: {url_count}")
    print(f"   - Eksik/boş: {extinf_count - url_count}")
    
    # 9. Eksik kanalları kontrol et
    all_files = set(f.stem for f in m3u_files)
    all_files.discard("playerlist")
    all_files.discard("playlist")
    
    listed_names = set()
    for line in lines:
        if line.startswith("#EXTINF"):
            # #EXTINF:0,Kanal_Adı
            match = re.search(r"#EXTINF:[^,]+,(.+?)(?:\s*$)", line)
            if match:
                name = match.group(1).strip().replace(" ", "_")
                listed_names.add(name)
    
    missing = all_files - listed_names
    if missing:
        print(f"\n[UYARI] Aşağıdaki kanallar listede yok:")
        for name in sorted(missing):
            print(f"   - {name}")
    
    print(f"\n[OK] İşlem tamamlandı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
