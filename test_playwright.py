import asyncio
from playwright.async_api import async_playwright

async def test_groupon():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://www.groupon.com/deals/gs-chicago-il", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)  # let JS render deal cards

        final_url = page.url
        title = await page.title()

        # Try to grab deal card text
        deals = await page.query_selector_all("[data-testid='deal-card'], .cui-udc-title, h3")
        deal_texts = []
        for d in deals[:5]:
            text = await d.inner_text()
            if text.strip():
                deal_texts.append(text.strip())

        print(f"Final URL : {final_url}")
        print(f"Page title: {title}")
        print(f"Deal snippets ({len(deals)} elements matched):")
        for t in deal_texts:
            print(" -", t[:100])

        await browser.close()

asyncio.run(test_groupon())
