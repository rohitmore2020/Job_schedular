const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const GIFEncoder = require('gif-encoder-2');
const { PNG } = require('pngjs');

const CHROME_PATH = fs.existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
  ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  : '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser';

const ASSETS_DIR = path.join(__dirname, '../docs/assets');

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function recordWalkthrough() {
  console.log('🚀 Launching Google Chrome for Demo Walkthrough Recording...');
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    defaultViewport: {
      width: 1280,
      height: 800,
      deviceScaleFactor: 1,
    },
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1280,800'],
  });

  const page = await browser.newPage();
  const frames = [];

  async function captureFrame(delayMs = 250) {
    const buffer = await page.screenshot({ type: 'png' });
    frames.push({ buffer, delay: delayMs });
  }

  async function holdFrames(count = 5, delayEach = 300) {
    for (let i = 0; i < count; i++) {
      await captureFrame(delayEach);
      await sleep(100);
    }
  }

  console.log('1. Navigating to Scheduler Dashboard...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle0' });
  await holdFrames(4, 250);

  console.log('2. Performing 1-Click Quick Demo Login...');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const btn = buttons.find(b => b.textContent.includes('Lead Platform Engineer') || b.textContent.includes('Sign In') || b.textContent.includes('Demo'));
    if (btn) btn.click();
  });
  await sleep(1500);
  await holdFrames(6, 300);

  console.log('3. Overview Dashboard & Telemetry Charts...');
  await page.mouse.move(400, 260);
  await holdFrames(3, 250);
  await page.mouse.move(750, 300);
  await holdFrames(4, 300);

  console.log('4. Navigating to Queue Manager...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const qBtn = btns.find((b) => b.textContent.includes('Queues'));
    if (qBtn) qBtn.click();
  });
  await sleep(800);
  await holdFrames(6, 300);

  console.log('5. Navigating to Batch Orchestrator...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const bBtn = btns.find((b) => b.textContent.includes('Batch Jobs'));
    if (bBtn) bBtn.click();
  });
  await sleep(800);
  await holdFrames(6, 300);

  console.log('6. Submitting a New Job / Modal Interaction...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const submitBtn = btns.find((b) => b.textContent.includes('Submit New Job'));
    if (submitBtn) submitBtn.click();
  });
  await sleep(600);
  await holdFrames(5, 300);

  // Close or submit modal
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const dispatchBtn = btns.find((b) => b.textContent.includes('Dispatch Job') || b.textContent.includes('Submit'));
    if (dispatchBtn) dispatchBtn.click();
  });
  await sleep(800);
  await holdFrames(4, 250);

  console.log('7. Navigating to Job Stream & Opening Execution Terminal Drawer...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const jBtn = btns.find((b) => b.textContent.includes('Jobs'));
    if (jBtn) jBtn.click();
  });
  await sleep(800);
  await holdFrames(4, 250);

  // Click first job row to open slide-in drawer
  await page.evaluate(() => {
    const firstRow = document.querySelector('table tbody tr');
    if (firstRow) firstRow.click();
  });
  await sleep(800);
  await holdFrames(7, 350);

  // Close drawer
  await page.evaluate(() => {
    const closeBtn = document.querySelector('.animate-slide-in button');
    if (closeBtn) closeBtn.click();
  });
  await sleep(400);

  console.log('8. Dead Letter Queue & AI Root-Cause Diagnostics...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const dlqBtn = btns.find((b) => b.textContent.includes('Dead Letter Queue'));
    if (dlqBtn) dlqBtn.click();
  });
  await sleep(800);
  await holdFrames(4, 300);

  // Click View Trace on DLQ incident to reveal AI diagnostic
  await page.evaluate(() => {
    const traceBtn = Array.from(document.querySelectorAll('button')).find((b) =>
      b.textContent.includes('View Trace')
    );
    if (traceBtn) traceBtn.click();
  });
  await sleep(600);
  await holdFrames(8, 350);

  // Click Replay Job button
  await page.evaluate(() => {
    const replayBtn = Array.from(document.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Replay Job')
    );
    if (replayBtn) replayBtn.click();
  });
  await sleep(800);
  await holdFrames(5, 300);

  console.log('9. Worker Fleet Telemetry & Node Heartbeats...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const wBtn = btns.find((b) => b.textContent.includes('Worker Fleet'));
    if (wBtn) wBtn.click();
  });
  await sleep(800);
  await holdFrames(6, 300);

  console.log('10. Cron Schedules...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const sBtn = btns.find((b) => b.textContent.includes('Cron Schedules'));
    if (sBtn) sBtn.click();
  });
  await sleep(800);
  await holdFrames(6, 300);

  console.log('11. Returning to Overview Dashboard...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('nav button, aside button'));
    const oBtn = btns.find((b) => b.textContent.includes('Overview'));
    if (oBtn) oBtn.click();
  });
  await sleep(800);
  await holdFrames(6, 400);

  await browser.close();

  console.log(`🎬 Captured ${frames.length} frames. Encoding into animated GIF...`);
  const encoder = new GIFEncoder(1280, 800, 'neuquant', true);
  const gifPath = path.join(ASSETS_DIR, 'demo_walkthrough.gif');
  const writeStream = fs.createWriteStream(gifPath);
  encoder.createReadStream().pipe(writeStream);

  encoder.start();
  encoder.setRepeat(0); // 0 = loop indefinitely
  encoder.setQuality(10); // high visual quality

  for (let i = 0; i < frames.length; i++) {
    const f = frames[i];
    encoder.setDelay(f.delay);
    const png = PNG.sync.read(f.buffer);
    encoder.addFrame(png.data);
    if ((i + 1) % 15 === 0 || i === frames.length - 1) {
      console.log(`  Encoding frame ${i + 1}/${frames.length}...`);
    }
  }

  encoder.finish();

  await new Promise((resolve) => writeStream.on('finish', resolve));
  console.log(`🎉 Demo animation saved to: ${gifPath} (${(fs.statSync(gifPath).size / 1024 / 1024).toFixed(2)} MB)`);
}

recordWalkthrough().catch((err) => {
  console.error('Recording error:', err);
  process.exit(1);
});
