"""Lunes Host 自动登录 - nodriver"""
import os, sys, time, asyncio, requests, shutil

LOGIN_URL = "https://betadash.lunes.host/login"

def tg_send(text, token="", chat_id=""):
    token, chat_id = (token or "").strip(), (chat_id or "").strip()
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as e:
        print(f"TG send failed: {e}")

def build_accounts():
    batch = (os.getenv("ACCOUNTS_BATCH") or "").strip()
    if not batch:
        raise RuntimeError("Missing ACCOUNTS_BATCH")
    accounts = []
    for raw in batch.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            accounts.append({
                "email": parts[0], "password": parts[1],
                "tg_token": parts[2] if len(parts) > 2 else "",
                "tg_chat": parts[3] if len(parts) > 3 else "",
            })
    return accounts

def find_chrome():
    for p in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]:
        if os.path.exists(p):
            return p
    for p in ["/snap/chromium/current/usr/lib/chromium-browser/chrome", "/snap/bin/chromium"]:
        if os.path.exists(p):
            return p
    found = shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("google-chrome")
    return found

async def login_one(email, password):
    import nodriver as uc
    
    chrome_path = find_chrome()
    print(f"Chrome path: {chrome_path}")
    
    config = uc.Config()
    config.no_sandbox = True
    config.headless = True
    if chrome_path:
        config.browser_executable_path = chrome_path
    
    browser = await uc.start(config)
    
    try:
        page = await browser.get(LOGIN_URL)
        await asyncio.sleep(5)
        
        email_input = await page.select("#email", timeout=20000)
        await email_input.clear_input()
        await email_input.send_keys(email)
        
        pass_input = await page.select("#password", timeout=10000)
        await pass_input.clear_input()
        await pass_input.send_keys(password)
        
        print("Waiting for Turnstile...")
        for i in range(30):
            await asyncio.sleep(2)
            try:
                val = await page.evaluate('document.querySelector("[name=cf-turnstile-response]")?.value || ""')
                if val:
                    print(f"Turnstile solved! ({i*2}s)")
                    break
            except:
                pass
        else:
            print("Turnstile timeout, trying submit anyway...")
        
        btn = await page.select('button[type="submit"]', timeout=5000)
        await btn.click()
        await asyncio.sleep(5)
        
        url = page.url
        if "/login" not in url:
            print(f"Login success: {url}")
            for sid in ["51160", "60685"]:
                try:
                    await browser.get(f"https://betadash.lunes.host/servers/{sid}")
                    await asyncio.sleep(3)
                    print(f"  Visited server {sid}")
                except Exception as e:
                    print(f"  Server {sid}: {e}")
            return True
        else:
            print(f"Login failed, still on: {url}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        browser.stop()

async def main():
    accounts = build_accounts()
    ok, fail = 0, 0
    results = []
    
    for i, acc in enumerate(accounts, 1):
        email = acc["email"]
        print(f"\n{'='*50}")
        print(f"[{i}/{len(accounts)}] {email}")
        print(f"{'='*50}")
        
        success = await login_one(email, acc["password"])
        if success:
            ok += 1
            results.append(f"OK {email}")
        else:
            fail += 1
            results.append(f"FAIL {email}")
        
        tg_send(
            f"{'✅' if success else '❌'} Lunes {'登录成功' if success else '登录失败'}\n{email}",
            acc.get("tg_token", ""), acc.get("tg_chat", "")
        )
        if i < len(accounts):
            await asyncio.sleep(5)
    
    summary = f"Lunes 续期: {ok}/{len(accounts)} 成功\n" + "\n".join(results)
    print(f"\n{summary}")
    for acc in accounts:
        if acc.get("tg_token") and acc.get("tg_chat"):
            tg_send(summary, acc["tg_token"], acc["tg_chat"])
            break
    
    if fail == len(accounts):
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
