import asyncio
import json
import os
from playwright.async_api import async_playwright

DATA_FILE = "data.json"

def load_existing_data():
    """加载已有数据，返回记录列表和已存在记录的key集合"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            
            # 构建已存在记录的key集合
            existing_keys = set()
            for r in records:
                # 使用 (code, date, title) 作为唯一键
                # 对于缺失code的记录，使用 (date, title) 作为降级键
                if r.get("code"):
                    key = (r["code"], r["date"], r["title"])
                else:
                    key = ("__no_code__", r["date"], r["title"])
                existing_keys.add(key)
            
            # 最新处分日期（用于快速判断）
            latest_date = records[0]["date"] if records else None
            
            return records, existing_keys, latest_date
        except (json.JSONDecodeError, KeyError) as e:
            print(f"加载已有数据失败: {e}")
            return [], set(), None
    return [], set(), None

def save_data(records):
    """保存数据到文件"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

async def main():
    url = "https://www.szse.cn/disclosure/supervision/measure/pushish/index.html"
    
    # 加载已有数据
    existing_records, existing_keys, latest_date = load_existing_data()
    print(f"已有 {len(existing_records)} 条记录，最新处分日期: {latest_date}")
    
    new_records = []  # 本次新抓取的记录
    stop_crawling = False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        
        page_num = 1
        
        while not stop_crawling and page_num <= 142:
            print(f"正在抓取第 {page_num} 页...")
            
            await page.wait_for_selector("a[encode-open]", timeout=30000)
            
            # 提取当前页数据
            page_records = await page.evaluate("""
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
            
            # 过滤出新增记录
            new_on_page = []
            for record in page_records:
                # 构建当前记录的唯一键
                if record.get("code"):
                    key = (record["code"], record["date"], record["title"])
                else:
                    key = ("__no_code__", record["date"], record["title"])
                
                # 如果已存在，停止抓取（因为页面按日期倒序，遇到已存在说明后面的也都有了）
                if key in existing_keys:
                    print(f"  遇到已存在的记录: {record['date']} - {record['title'][:30]}...")
                    stop_crawling = True
                    break
                
                # 可选：即使已存在记录，如果日期比最新日期还新，说明可能是同一天的新记录
                # 这里用更严格的判断：只有完全匹配才停止
                new_on_page.append(record)
            
            if new_on_page:
                new_records.extend(new_on_page)
                print(f"  本页新增 {len(new_on_page)} 条记录")
            else:
                if not stop_crawling:
                    print(f"  本页无新增记录")
            
            # 如果已停止或已无新数据，结束循环
            if stop_crawling:
                print("已遇到已存在记录，停止抓取")
                break
            
            # 翻到下一页
            next_page_num = page_num + 1
            if next_page_num > 142:
                print("已到达最后一页")
                break
            
            try:
                # 滚动到页面底部
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                
                # 点击下一页的页码
                clicked = await page.evaluate(f"""
                    () => {{
                        const links = Array.from(document.querySelectorAll('a.item'));
                        const targetLink = links.find(link => link.innerText.trim() === '{next_page_num}');
                        if (targetLink) {{
                            targetLink.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            targetLink.click();
                            return true;
                        }}
                        return false;
                    }}
                """)
                
                if clicked:
                    await page.wait_for_timeout(3000)
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_selector("a[encode-open]", timeout=30000)
                    page_num += 1
                else:
                    print("无法翻页，停止抓取")
                    break
                    
            except Exception as e:
                print(f"翻页失败: {e}")
                break
        
        await browser.close()
    
    # 合并数据：新记录在前（网站倒序），已有数据在后
    all_records = new_records + existing_records
    
    # 可选：去重（防止边界情况）
    final_keys = set()
    deduped_records = []
    for r in all_records:
        if r.get("code"):
            key = (r["code"], r["date"], r["title"])
        else:
            key = ("__no_code__", r["date"], r["title"])
        if key not in final_keys:
            final_keys.add(key)
            deduped_records.append(r)
    
    save_data(deduped_records)
    
    print(f"\n本次新增 {len(new_records)} 条记录")
    print(f"当前共 {len(deduped_records)} 条记录，已保存至 {DATA_FILE}")

asyncio.run(main())
