import json
import os
import sys
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright


def http_get_json(url: str, headers: dict | None = None) -> dict:
    merged_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlaywrightImageDemo/1.0",
        "Accept": "application/json",
    }
    if headers:
        merged_headers.update(headers)
    req = urllib.request.Request(url, headers=merged_headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_bing_image(query: str) -> str | None:
    api_key = os.getenv("BING_API_KEY", "").strip()
    if not api_key:
        return None

    endpoint = os.getenv(
        "BING_ENDPOINT", "https://api.bing.microsoft.com/v7.0/images/search"
    ).strip()
    qs = urllib.parse.urlencode(
        {
            "q": query,
            "count": 1,
            "safeSearch": "Moderate",
            "imageType": "Photo",
        }
    )
    url = f"{endpoint}?{qs}"
    data = http_get_json(url, headers={"Ocp-Apim-Subscription-Key": api_key})
    values = data.get("value") or []
    if not values:
        return None
    first = values[0]
    return first.get("contentUrl") or first.get("thumbnailUrl")


def search_wikimedia_image(query: str) -> str | None:
    # Keyless fallback: Wikimedia API.
    qs = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": 1,
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": 1200,
        }
    )
    url = f"https://en.wikipedia.org/w/api.php?{qs}"
    data = http_get_json(url)
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        thumb = (page.get("thumbnail") or {}).get("source")
        if thumb:
            return thumb
    return None


def search_wikipedia_summary_image(query: str) -> str | None:
    # Secondary keyless fallback.
    title = query.strip().replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        data = http_get_json(url)
    except Exception:
        return None
    return (data.get("thumbnail") or {}).get("source")


def find_image_url(query: str) -> tuple[str | None, str]:
    bing_url = search_bing_image(query)
    if bing_url:
        return bing_url, "Bing Image Search API"

    wiki_url = search_wikimedia_image(query)
    if wiki_url:
        return wiki_url, "Wikimedia fallback"

    wiki_summary_url = search_wikipedia_summary_image(query)
    if wiki_summary_url:
        return wiki_summary_url, "Wikipedia summary fallback"

    return None, "None"


def render_example_page(query: str, image_url: str, source: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(
            f"""
            <html>
              <head>
                <title>Example Image Result</title>
                <style>
                  body {{
                    font-family: Arial, sans-serif;
                    background: #f5f5f7;
                    margin: 0;
                    padding: 24px;
                  }}
                  .card {{
                    background: #fff;
                    max-width: 980px;
                    margin: 0 auto;
                    border-radius: 12px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.12);
                    overflow: hidden;
                  }}
                  .meta {{
                    padding: 16px 20px;
                    border-bottom: 1px solid #eee;
                  }}
                  .meta h1 {{
                    margin: 0 0 8px;
                    font-size: 24px;
                  }}
                  .meta p {{
                    margin: 2px 0;
                    color: #444;
                  }}
                  img {{
                    display: block;
                    width: 100%;
                    height: auto;
                    background: #fafafa;
                  }}
                </style>
              </head>
              <body>
                <div class="card">
                  <div class="meta">
                    <h1>Example Page</h1>
                    <p><strong>Query:</strong> {query}</p>
                    <p><strong>Source:</strong> {source}</p>
                  </div>
                  <img src="{image_url}" alt="Search result image"/>
                </div>
              </body>
            </html>
            """
        )
        print(f"Displayed image for query: {query}")
        print(f"Source used: {source}")
        input("Press Enter to close...")
        browser.close()


def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or "donald trump"
    image_url, source = find_image_url(query)
    if not image_url:
        raise RuntimeError("No image found from Bing API or Wikimedia fallback.")
    render_example_page(query, image_url, source)


if __name__ == "__main__":
    main()
