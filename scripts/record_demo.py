import asyncio
import os
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

ASSETS_DIR = Path(__file__).parent.parent / "docs" / "assets"
RECORDINGS_DIR = ASSETS_DIR / "recordings"

async def record_demo():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            record_video_dir=str(RECORDINGS_DIR),
            record_video_size={"width": 1440, "height": 900}
        )
        
        page = await context.new_page()
        print("1. Navigating to application...")
        await page.goto("http://localhost:3000", wait_until="networkidle")
        await asyncio.sleep(1.5)
        
        print("2. Performing 1-Click Quick Demo Login...")
        # Check if auth modal is visible
        quick_login_btn = page.locator("button:has-text('Lead Platform Engineer')").first
        if await quick_login_btn.count() > 0:
            await quick_login_btn.click()
        else:
            login_btn = page.locator("button:has-text('Sign In')").first
            if await login_btn.count() > 0:
                await login_btn.click()
        
        await asyncio.sleep(2.5)
        
        print("3. Overview & Live Telemetry KPIs...")
        await page.mouse.move(500, 300)
        await asyncio.sleep(1.0)
        await page.mouse.move(800, 350)
        await asyncio.sleep(2.0)
        
        print("4. Queue Management...")
        await page.locator("nav button:has-text('Queues')").click()
        await asyncio.sleep(2.5)
        
        # Click pause / resume on the first queue if available
        pause_btn = page.locator("button:has-text('Pause')").first
        if await pause_btn.count() > 0:
            await pause_btn.click()
            await asyncio.sleep(1.5)
            resume_btn = page.locator("button:has-text('Resume')").first
            if await resume_btn.count() > 0:
                await resume_btn.click()
                await asyncio.sleep(1.5)
                
        print("5. Batch Jobs View...")
        await page.locator("nav button:has-text('Batch Jobs')").click()
        await asyncio.sleep(2.5)
        
        print("6. Submitting a New Job...")
        submit_btn = page.locator("button:has-text('Submit New Job')").first
        if await submit_btn.count() > 0:
            await submit_btn.click()
            await asyncio.sleep(1.5)
            
            # Click submit in modal
            modal_submit = page.locator("button:has-text('Dispatch Job')").first
            if await modal_submit.count() > 0:
                await modal_submit.click()
            await asyncio.sleep(2.0)
            
        print("7. Job Stream & Terminal Drawer...")
        await page.locator("nav button:has-text('Jobs')").click()
        await asyncio.sleep(2.0)
        
        # Click on the first job row to open slide-in drawer
        first_row = page.locator("table tbody tr").first
        if await first_row.count() > 0:
            await first_row.click()
            await asyncio.sleep(2.5)
            # Close drawer
            close_btn = page.locator("button:has-text('Retry'), button:has-text('Cancel')").locator("..").locator("button").last
            if await close_btn.count() > 0:
                await close_btn.click()
            await asyncio.sleep(1.0)
            
        print("8. Dead Letter Queue & AI Diagnostics...")
        await page.locator("nav button:has-text('Dead Letter Queue')").click()
        await asyncio.sleep(2.0)
        
        view_trace_btn = page.locator("button:has-text('View Trace')").first
        if await view_trace_btn.count() > 0:
            await view_trace_btn.click()
            await asyncio.sleep(3.0)
            
        print("9. Worker Fleet Telemetry...")
        await page.locator("nav button:has-text('Worker Fleet')").click()
        await asyncio.sleep(2.5)
        
        print("10. Cron Schedules...")
        await page.locator("nav button:has-text('Cron Schedules')").click()
        await asyncio.sleep(2.5)
        
        print("11. Return to Overview Dashboard...")
        await page.locator("nav button:has-text('Overview')").click()
        await asyncio.sleep(3.0)
        
        print("12. Finalizing recording...")
        await context.close()
        await browser.close()
        
        # Move generated video
        video_files = list(RECORDINGS_DIR.glob("*.webm"))
        if video_files:
            latest_video = max(video_files, key=os.path.getctime)
            dest_video = ASSETS_DIR / "demo_walkthrough.webm"
            shutil.copy(str(latest_video), str(dest_video))
            print(f"✅ Demo video saved successfully to: {dest_video}")

if __name__ == "__main__":
    asyncio.run(record_demo())
