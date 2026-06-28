import asyncio, json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        page.on('response', lambda response: asyncio.create_task(handle_response(response)))
        
        async def handle_response(response):
            if response.status == 422:
                body = await response.text()
                print(f'422 ERROR on {response.url}: {body}')
            elif response.url.endswith('backtest') or response.url.endswith('analyze'):
                print(f'{response.url} returned {response.status}')
                
        await page.goto('http://127.0.0.1:8000/?v=3.2')
        await page.evaluate('document.getElementById("backtest-ticker").value = "2330.TW"; runBacktest()')
        await page.wait_for_timeout(3000)
        await browser.close()

asyncio.run(run())
