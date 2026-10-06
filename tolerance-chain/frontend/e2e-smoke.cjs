/* 端到端冒烟：真实 Chromium 渲染 Angular 页面，点击分析并核对结果。 */
const puppeteer = require('puppeteer');
const os = require('os');
const fs = require('fs');

const browserRoot = `${os.homedir()}/.cache/ms-playwright/chromium_headless_shell-1243`;
const candidates = fs.readdirSync(browserRoot)
  .map((d) => `${browserRoot}/${d}/chrome-headless-shell`)
  .filter((p) => fs.existsSync(p));

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: candidates[0],
    env: {
      ...process.env,
      LD_LIBRARY_PATH: [
        '/workspace/tools/chromelibs/usr/lib/aarch64-linux-gnu',
        '/workspace/tools/chromelibs/lib/aarch64-linux-gnu',
        process.env.LD_LIBRARY_PATH || '',
      ].filter(Boolean).join(':'),
    },
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('CONSOLE: ' + m.text());
  });

  await page.goto('http://localhost:4200/', { waitUntil: 'networkidle0' });
  await page.waitForSelector('.chain-item');
  const chainCount = await page.$$eval('.chain-item', (els) => els.length);
  console.log('渲染出尺寸链卡片数:', chainCount);

  // 选中轴孔配合案例（第一张卡片默认选中），点运行
  await page.waitForSelector('button');
  await page.click('button');
  await page.waitForFunction(
    () => document.body.innerText.includes('0.0250'),
    { timeout: 20000 });

  const body = await page.evaluate(() => document.body.innerText);
  const checks = [
    ['极值下限 0.025', body.includes('0.0250')],
    ['极值上限 0.089', body.includes('0.0890')],
    ['封闭环中心 0.057', body.includes('0.0570')],
    ['朴素绝对值警告', body.includes('绝对值直接相加')],
    ['RSS 前提说明', body.includes('均方根')],
    ['MC 固定种子', body.includes('20261006')],
    ['主导尺寸 bore（孔）', body.includes('孔 Φ50H8')],
    ['验收免责声明', body.includes('不替代制造验收')],
    ['干涉判定“否”', /可能干涉[\s\S]*否/.test(body)],
  ];
  let ok = true;
  for (const [name, pass] of checks) {
    console.log((pass ? 'PASS' : 'FAIL') + ' - ' + name);
    if (!pass) ok = false;
  }

  // 切换到 unknown_dist 案例
  const cards = await page.$$('.chain-item');
  await cards[3].click();
  await page.click('button');
  await page.waitForFunction(
    () => document.body.innerText.includes('系统不会把未知分布默认成正态'),
    { timeout: 20000 });
  const body2 = await page.evaluate(() => document.body.innerText);
  const ok2 = body2.includes('不会自动套用正态') ||
    body2.includes('系统不会把未知分布默认成正态');
  console.log((ok2 ? 'PASS' : 'FAIL') + ' - 未知分布被统计方法拒绝');
  if (!ok2) ok = false;

  // 切到零公差基准
  const cards2 = await page.$$('.chain-item');
  await cards2[2].click();
  await page.click('button');
  await page.waitForFunction(
    () => document.body.innerText.includes('零公差常数'),
    { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 300));
  const body3 = await page.evaluate(() => document.body.innerText);
  const ok3 = body3.includes('基准隔块') && body3.includes('0.1500') &&
    body3.includes('零公差') && body3.includes('零公差常数');
  console.log((ok3 ? 'PASS' : 'FAIL') +
    ' - 零公差基准：极值上界 0.15、基准环标记零公差常数');
  if (!ok3) ok = false;

  if (errors.length) {
    console.log('--- 浏览器错误 ---');
    errors.forEach((e) => console.log(e));
    ok = false;
  }
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
