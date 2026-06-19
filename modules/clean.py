import os
import shutil
import asyncio

async def cleanup_downloads(download_path="./downloads"):
    """
    यह फंक्शन downloads फोल्डर की सारी फाइलें और फोल्डर डिलीट कर देगा
    """
    try:
        if os.path.exists(download_path):
            # सारी फाइलें और सबफोल्डर हटाओ
            shutil.rmtree(download_path)
            print(f"✅ Cleanup: {download_path} पूरी तरह खाली कर दिया")
        # नया खाली फोल्डर बनाओ
        os.makedirs(download_path, exist_ok=True)
    except Exception as e:
        print(f"❌ Cleanup Error: {e}")

async def cleanup_temp_files(extensions=[".jpg", ".jpeg", ".png", ".webm", ".mkv", ".mp4", ".ts", ".m4a"]):
    """
    Temp फाइलें (जो main directory में रह गई हैं) हटाओ
    """
    try:
        for file in os.listdir("."):
            if any(file.endswith(ext) for ext in extensions):
                # सिर्फ वही फाइलें हटाओ जो downloads फोल्डर में नहीं हैं
                if not file.startswith("downloads") and not file.startswith("modules"):
                    os.remove(file)
                    print(f"🗑️ Deleted temp file: {file}")
    except Exception as e:
        print(f"❌ Temp Cleanup Error: {e}")
