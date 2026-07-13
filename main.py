from playwright.sync_api import sync_playwright

URL = "https://www.infocasas.com.uy/venta/casas/montevideo"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        print("Título:", page.title())
        print("URL final:", page.url)

        page.screenshot(path="infocasas.png", full_page=True)

        with open("infocasas.html", "w", encoding="utf-8") as f:
            f.write(page.content())

        browser.close()


if __name__ == "__main__":
    main()
