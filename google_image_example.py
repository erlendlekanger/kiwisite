from base64 import b64encode
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


def dismiss_google_consent(page) -> None:
    """Best-effort dismissal of common Google consent dialogs."""
    selectors = [
        'button:has-text("Reject all")',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Agree")',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=1500)
            return
        except Exception:
            continue


def get_first_real_image_bytes(page) -> bytes:
    """
    Return screenshot bytes for the first substantial visible image.
    Excludes tiny icons/logos by checking element dimensions.
    """
    images = page.locator("img")
    count = images.count()
    for i in range(count):
        candidate = images.nth(i)
        try:
            box = candidate.bounding_box()
            if not box:
                continue
            if box["width"] < 120 or box["height"] < 120:
                continue
            return candidate.screenshot(type="png")
        except Exception:
            continue
    raise RuntimeError("Could not find a suitable image to screenshot.")


def wait_for_images_after_manual_challenge(page) -> None:
    """
    Wait for image results; if blocked by challenge, let user solve it manually.
    """
    try:
        page.wait_for_selector("img", timeout=10000)
        return
    except PlaywrightTimeoutError:
        print("Google may be showing a challenge/CAPTCHA.")
        print("Please solve it in the browser window, then press Enter here.")
        input("Press Enter after challenge is solved -> ")
        page.wait_for_selector("img", timeout=30000)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        query = "donald trump"
        page.goto(
            f"https://www.google.com/search?tbm=isch&q={query.replace(' ', '+')}",
            timeout=30000,
        )

        dismiss_google_consent(page)
        wait_for_images_after_manual_challenge(page)

        image_bytes = get_first_real_image_bytes(page)
        image_b64 = b64encode(image_bytes).decode("ascii")

        demo_page = context.new_page()
        demo_page.set_content(
            f"""
            <html>
              <head>
                <title>Example Image Display</title>
                <style>
                  body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    background: #f7f7f7;
                    display: grid;
                    place-items: center;
                    min-height: 100vh;
                  }}
                  .card {{
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
                    padding: 20px;
                    max-width: 760px;
                    width: calc(100% - 40px);
                  }}
                  h1 {{
                    margin: 0 0 12px 0;
                    font-size: 24px;
                  }}
                  p {{
                    margin: 0 0 16px 0;
                    color: #444;
                  }}
                  img {{
                    width: 100%;
                    height: auto;
                    border-radius: 8px;
                    border: 1px solid #ddd;
                  }}
                </style>
              </head>
              <body>
                <div class="card">
                  <h1>Example Page</h1>
                  <p>First Google Images result screenshot for: {query}</p>
                  <img alt="Captured first image" src="data:image/png;base64,{image_b64}" />
                </div>
              </body>
            </html>
            """
        )

        print("Done. Check the new tab titled 'Example Image Display'.")
        input("Press Enter to close...")
        browser.close()


if __name__ == "__main__":
    main()
