import asyncio
import json
import os
from playwright.async_api import async_playwright

async def main():
    url = "https://www.szse.cn/disclosure/supervision/measure/pushish/index.html"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        
        # 等待数据加载
        await page.wait_for_selector("a[encode-open]", timeout=30000)
        
        # 提取数据
        all_records = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[encode-open]'));
                return links.map(link => {
                    let parent = link.parentElement;
                    for (let i = 0; i < 6; i++) { if (parent && parent.tagName !== 'TR') parent = parent.parentElement; }
                    const cells = parent ? parent.querySelectorAll('td') : [];
                    return {
                        code: cells[0]?.innerText?.trim() || '',
                        name: cells[1]?.innerText?.trim() || '',
                        date: cells[2]?.innerText?.trim() || '',
                        type: cells[3]?.innerText?.trim() || '',
                        title: cells[4]?.innerText?.trim() || '',
                        pdf_url: 'https://reportdocs.static.szse.cn' + link.getAttribute('encode-open')
                    };
                });
            }
        """)
        
        # 保存为 JSON 文件
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(all_records, f, ensure_ascii=False, indent=2)
        await browser.close()

asyncio.run(main())