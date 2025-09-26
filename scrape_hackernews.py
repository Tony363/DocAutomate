#!/usr/bin/env python3
"""
Scrape top 5 headlines from Hacker News and save to Markdown
"""

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

async def scrape_hacker_news():
    """Scrape top 5 headlines from Hacker News"""
    
    headlines = []
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to Hacker News
            print("🌐 Navigating to Hacker News...")
            await page.goto("https://news.ycombinator.com", wait_until='networkidle')
            
            # Wait for content to load
            await page.wait_for_selector('.titleline', timeout=10000)
            
            # Get top 5 headlines
            print("📰 Extracting top 5 headlines...")
            headline_elements = await page.query_selector_all('.titleline > a')
            
            # Extract first 5 headlines
            for i, element in enumerate(headline_elements[:5], 1):
                title = await element.text_content()
                href = await element.get_attribute('href')
                
                # Handle relative URLs
                if href and not href.startswith('http'):
                    if href.startswith('item?'):
                        href = f"https://news.ycombinator.com/{href}"
                
                headlines.append({
                    'rank': i,
                    'title': title.strip() if title else 'No title',
                    'url': href or '#'
                })
                
                print(f"  {i}. {title[:60]}..." if len(title) > 60 else f"  {i}. {title}")
            
        finally:
            await browser.close()
    
    return headlines

def save_to_markdown(headlines):
    """Save headlines to a Markdown file"""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create Markdown content
    markdown_content = f"""# Hacker News Top 5 Headlines

**Scraped on:** {timestamp}

---

"""
    
    for item in headlines:
        markdown_content += f"{item['rank']}. [{item['title']}]({item['url']})\n\n"
    
    markdown_content += """---

*Generated automatically using Playwright web scraping*
"""
    
    # Save to file
    output_file = '/home/tony/Desktop/DocAutomate/hackernews_top5.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"\n✅ Saved to: {output_file}")
    return output_file

async def main():
    """Main execution function"""
    try:
        # Scrape headlines
        headlines = await scrape_hacker_news()
        
        if headlines:
            # Save to Markdown
            output_file = save_to_markdown(headlines)
            
            print(f"\n📄 Successfully saved {len(headlines)} headlines to Markdown!")
            print(f"📍 File location: {output_file}")
        else:
            print("❌ No headlines were extracted")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())