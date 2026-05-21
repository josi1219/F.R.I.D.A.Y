"""Quick diagnostic: test what DuckDuckGo HTML actually returns."""
import requests, re, urllib.parse

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

for test_url in [
    "https://html.duckduckgo.com/html/?q=recent+AI+machine+learning",
    "https://lite.duckduckgo.com/lite/?q=recent+AI+machine+learning",
]:
    print(f"\n{'='*60}\nURL: {test_url}")
    try:
        resp = requests.get(test_url, headers=headers, timeout=15)
        print(f"Status: {resp.status_code}  Length: {len(resp.text)}")

        # Try uddg extraction
        uddg = re.findall(r"[?&]uddg=(https?[^&<>\s\"]+)", resp.text)
        print(f"uddg matches: {len(uddg)}")
        if uddg:
            decoded = [urllib.parse.unquote(u) for u in uddg[:3]]
            print(f"  First 3 decoded: {decoded}")

        # Try direct href
        direct = re.findall(r'href="(https?://[^"]+)"', resp.text)
        direct_clean = [u for u in direct if "&" not in u]
        print(f"Direct href matches: {len(direct_clean)}")
        if direct_clean:
            print(f"  First 3: {direct_clean[:3]}")

        # Show raw snippet around first result link
        idx = resp.text.find("uddg=")
        if idx >= 0:
            print(f"uddg snippet: {repr(resp.text[max(0,idx-30):idx+120])}")
        else:
            # Show a mid-page snippet so we can see the link structure
            print(f"No uddg found. Mid-page snippet:\n{repr(resp.text[1500:2300])}")

    except Exception as e:
        print(f"ERROR: {e}")
