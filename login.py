"""Lunes Host 自动登录续期 - Playwright + stealth"""
import os, re, sys, time, random, requests, json

LOGIN_URL = "https://betadash.lunes.host/login?next=/"
HOME_URL = "https://betadash.lunes.host/"
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def tg_send(text, token="", chat_id=""):
    token = (token or "").strip()
    chat_id = (chat_id or "").strip()
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        print(f"⚠️ TG 发送失败：{e}")


def build_accounts():
    batch = (os.getenv("ACCOUNTS_BATCH") or "").strip()
    if not batch:
        raise RuntimeError("❌ 缺少 ACCOUNTS_BATCH")
    accounts = []
    for idx, raw in enumerate(batch.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (2, 4):
            raise RuntimeError(f"❌ 第{idx}行格式错误: {raw!r}")
        accounts.append({
            "email": parts[0], "password": parts[1],
            "tg_token": parts[2] if len(parts) == 4 else "",
            "tg_chat": parts[3] if len(parts) == 4 else "",
        })
    if not accounts:
        raise RuntimeError("❌ 无有效账号")
    return accounts


def login_one(email, password):
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=site-per-process,IsolateOrigins",
                "--window-size=1920,1080",
                "--disable-infobars",
                "--lang=en-US",
            ]
        )
        
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.114 Safari/537.36",
            locale="en-US",
            java_script_enabled=True,
        )
        
        # Stealth: remove webdriver flag
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = {runtime: {}};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : originalQuery(parameters);
        """)
        
        page = context.newPage()
        
        try:
            print(f"🚀 打开登录页: {email}")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 等 CF 通过
            for i in range(45):
                title = page.title()
                if "moment" not in (title or "").lower() and "checking" not in (title or "").lower():
                    break
                time.sleep(1)
            else:
                print("⚠️ CF 验证超时")
                page.screenshot(path=f"{SCREENSHOT_DIR}/cf-timeout-{int(time.time())}.png")
            
            time.sleep(2)
            
            # 填表单
            try:
                page.wait_for_selector("#email", state="visible", timeout=25000)
                page.wait_for_selector("#password", state="visible", timeout=25000)
            except:
                page.screenshot(path=f"{SCREENSHOT_DIR}/form-missing-{int(time.time())}.png")
                return False, None
            
            page.fill("#email", email)
            page.fill("#password", password)
            
            page.screenshot(path=f"{SCREENSHOT_DIR}/before-submit-{int(time.time())}.png")
            
            # 尝试点 Turnstile
            try:
                frames = page.frames
                for frame in frames:
                    if "challenges.cloudflare" in (frame.url or ""):
                        print("🧩 发现 Turnstile iframe，尝试点击...")
                        checkbox = frame.locator("input[type='checkbox']")
                        if checkbox.count() > 0:
                            checkbox.first.click(timeout=5000)
                            time.sleep(3)
                        break
            except Exception as e:
                print(f"⚠️ Turnstile: {e}")
            
            # 提交
            submit_btn = page.locator('button.submit-btn[type="submit"]')
            if submit_btn.count() == 0:
                submit_btn = page.locator('button[type="submit"]')
            
            submit_btn.first.click()
            
            # 等待页面跳转或加载
            time.sleep(5)
            for _ in range(15):
                url = page.url
                if "/login" not in url:
                    break
                try:
                    if page.locator("a[href='/logout']").count() > 0:
                        break
                    if page.locator("h1.hero-title").count() > 0:
                        break
                except:
                    pass
                time.sleep(1)
            
            page.screenshot(path=f"{SCREENSHOT_DIR}/after-submit-{int(time.time())}.png")
            
            # 判断登录成功
            logged_in = "/login" not in (page.url or "")
            if not logged_in:
                try:
                    if page.locator("a[href='/logout']").count() > 0:
                        logged_in = True
                except:
                    pass
            
            if not logged_in:
                print(f"❌ 登录失败: {email}")
                return False, None
            
            print(f"✅ 登录成功: {email}")
            
            # 进 server 页
            server_id = None
            try:
                server_card = page.locator("a.server-card[href^='/servers/']").first
                server_card.wait_for(state="visible", timeout=20000)
                href = server_card.get_attribute("href") or ""
                m = re.search(r"/servers/(\d+)", href)
                server_id = m.group(1) if m else None
                print(f"🧭 server_id={server_id}, 进入服务器页...")
                server_card.click()
                time.sleep(random.randint(4, 6))
                page.screenshot(path=f"{SCREENSHOT_DIR}/server-page-{int(time.time())}.png")
            except Exception as e:
                print(f"⚠️ server 页: {e}")
            
            # 回首页
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.randint(3, 5))
            
            # 退出
            try:
                logout = page.locator("a[href='/logout']")
                if logout.count() > 0:
                    logout.first.click()
                    time.sleep(2)
                    print("👋 已退出")
            except:
                pass
            
            return True, server_id
            
        except Exception as e:
            print(f"❌ 异常: {e}")
            try:
                page.screenshot(path=f"{SCREENSHOT_DIR}/error-{int(time.time())}.png")
            except:
                pass
            return False, None
        finally:
            context.close()
            browser.close()


def main():
    accounts = build_accounts()
    ok, fail = 0, 0
    results = []

    for i, acc in enumerate(accounts, 1):
        email = acc["email"]
        print(f"\n{'='*60}")
        print(f"👤 [{i}/{len(accounts)}] {email}")
        print(f"{'='*60}")

        success, server_id = login_one(email, acc["password"])
        if success:
            ok += 1
            results.append(f"✅ {email} (server={server_id or '?'})")
        else:
            fail += 1
            results.append(f"❌ {email}")

        tg_send(
            f"{'✅' if success else '❌'} Lunes 登录{'成功' if success else '失败'}\n账号: {email}\nserver: {server_id or '?'}",
            acc.get("tg_token", ""), acc.get("tg_chat", ""),
        )
        if i < len(accounts):
            time.sleep(5)

    summary = f"📌 Lunes 续期: 成功 {ok}/{len(accounts)}\n" + "\n".join(results)
    print(f"\n{summary}")
    for acc in accounts:
        if acc.get("tg_token") and acc.get("tg_chat"):
            tg_send(summary, acc["tg_token"], acc["tg_chat"])
            break

    if fail == len(accounts):
        sys.exit(1)


if __name__ == "__main__":
    main()
