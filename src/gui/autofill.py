# -*- coding: utf-8 -*-

import time
import webbrowser
import threading

try:
    import pyautogui
    import pyperclip
    PYAUTOGUI_AVAILABLE = True
    # Fail-safe: move mouse to corner to abort
    pyautogui.FAILSAFE = True
    # Pause between actions for reliability
    pyautogui.PAUSE = 0.5
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("⚠️ pyautogui not available - install with: pip install pyautogui pyperclip")

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️ Selenium not available - install with: pip install selenium webdriver-manager")


def autofill_with_selenium(url: str, username: str, password: str):
    """
    RECOMMENDED METHOD: Uses Selenium with scraping to find fields
    """
    if not SELENIUM_AVAILABLE:
        print("\n❌ Selenium is not installed")
        print("Install it with:")
        print("pip install selenium webdriver-manager")
        return False
    
    if not url:
        print("❌ Missing URL")
        return False

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    print(f"\n{'='*70}")
    print(f"🚀 AUTO-FILL WITH SELENIUM (Scraping)")
    print(f"{'='*70}")
    print(f"🌐 URL: {url}")
    print(f"👤 Username: {username}")
    print(f"🔑 Password: {'*' * len(password)}")
    
    driver = None
    try:
        # Chrome configuration
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        print(f"\n📂 Opening browser...")
        
        # Use webdriver-manager to auto-download ChromeDriver
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"   ✅ ChromeDriver installed automatically")
        except ImportError:
            # Fallback: try without webdriver-manager
            print(f"   ⚠️ webdriver-manager not installed")
            print(f"   Install with: pip install webdriver-manager")
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except:
                print(f"\n❌ Cannot initialize Chrome")
                print(f"Download ChromeDriver: https://chromedriver.chromium.org/")
                return False
        
        # Open the page
        print(f"🌐 Loading: {url}")
        driver.get(url)
        
        # Wait for page to load
        time.sleep(3)
        print(f"✅ Page loaded")
        
        # 🔍 SCRAPING: Find username/email field
        print(f"\n🔍 Searching for username field...")
        username_field = None
        
        # List of XPath selectors to find username field
        username_selectors = [
            "//input[@type='email']",
            "//input[@type='text' and (contains(@name, 'email') or contains(@name, 'user') or contains(@name, 'login'))]",
            "//input[contains(@id, 'email') or contains(@id, 'user') or contains(@id, 'login')]",
            "//input[contains(@placeholder, 'email') or contains(@placeholder, 'Email') or contains(@placeholder, 'usuario') or contains(@placeholder, 'user')]",
            "//input[@name='username' or @name='email' or @name='user' or @name='login']",
            "//input[@autocomplete='username' or @autocomplete='email']",
            "(//input[@type='text'])[1]",  # First text field as fallback
        ]
        
        for selector in username_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        username_field = element
                        print(f"   ✅ Username field found!")
                        break
                if username_field:
                    break
            except NoSuchElementException:
                continue
        
        if not username_field:
            print(f"   ❌ Cannot find username field")
            print(f"   💡 Use assisted method instead")
            return False
        
        # Fill username field
        print(f"   ⌨️  Filling: {username}")
        username_field.clear()
        username_field.send_keys(username)
        time.sleep(0.5)
        print(f"   ✅ Username filled")
        
        # 🔍 SCRAPING: Find password field
        print(f"\n🔍 Searching for password field...")
        password_field = None
        
        # List of XPath selectors to find password field
        password_selectors = [
            "//input[@type='password']",
            "//input[@name='password' or @name='passwd' or @name='pwd']",
            "//input[contains(@id, 'password') or contains(@id, 'passwd') or contains(@id, 'pwd')]",
            "//input[@autocomplete='current-password' or @autocomplete='password']",
        ]
        
        for selector in password_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        password_field = element
                        print(f"   ✅ Password field found!")
                        break
                if password_field:
                    break
            except NoSuchElementException:
                continue
        
        if not password_field:
            print(f"   ❌ Cannot find password field")
            return False
        
        # Fill password field
        print(f"   ⌨️  Filling: {'*' * len(password)}")
        password_field.clear()
        password_field.send_keys(password)
        time.sleep(0.5)
        print(f"   ✅ Password filled")
        
        # 🔍 SCRAPING: Find submit button
        print(f"\n🔍 Searching for submit button...")
        submit_button = None
        
        # List of selectors for submit button
        submit_selectors = [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'connexion')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'se connecter')]",
            "//input[contains(@value, 'Login') or contains(@value, 'Sign in')]",
            "//form//button",  # Any button in a form
        ]
        
        for selector in submit_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        submit_button = element
                        print(f"   ✅ Button found!")
                        break
                if submit_button:
                    break
            except NoSuchElementException:
                continue
        
        # Summary
        print(f"\n{'='*70}")
        print(f"📋 SUMMARY:")
        print(f"   • Username: ✅ Filled")
        print(f"   • Password: ✅ Filled")
        print(f"   • Button: {'✅ Found' if submit_button else '❌ Not found'}")
        print(f"{'='*70}")
        
        # Submit form
        time.sleep(1)
        
        if submit_button:
            print(f"\n🔨 Clicking submit button...")
            submit_button.click()
        else:
            print(f"\n⏎ Pressing ENTER...")
            password_field.send_keys(Keys.RETURN)
        
        time.sleep(2)
        print(f"✅ Form submitted!")
        
        time.sleep(10000)
        
        print(f"\n{'='*70}")
        print(f"✅ AUTO-FILL COMPLETE!")
        print(f"{'='*70}\n")
        
        return True
        
    except Exception as e:
        print(f"\n{'='*70}")
        print(f"❌ ERROR")
        print(f"{'='*70}")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"{'='*70}\n")
        return False
        
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def open_and_type_credentials(url: str, username: str, password: str, delay: float = 6.0):
    """
    ASSISTED METHOD: User clicks fields, we paste automatically
    """
    if not PYAUTOGUI_AVAILABLE:
        print("\n❌ PyAutoGUI is not installed")
        print("Install it with:")
        print("pip install pyautogui pyperclip")
        return False
    
    if not url:
        print("❌ Missing URL")
        return False

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    print(f"\n{'='*70}")
    print(f"🚀 ASSISTED AUTO-FILL")
    print(f"{'='*70}")
    print(f"🌐 URL: {url}")
    print(f"👤 Username: {username}")
    print(f"🔑 Password: {'*' * len(password)}")
    
    try:
        # Save clipboard
        original_clipboard = ""
        try:
            original_clipboard = pyperclip.paste()
        except:
            pass
        
        # Open site
        print(f"\n📂 Opening site...")
        webbrowser.open(url)
        
        print(f"\n⏳ Waiting {delay} seconds...")
        for i in range(int(delay), 0, -1):
            print(f"   {i}...", end='\r', flush=True)
            time.sleep(1)
        print(f"   ✅ Page loaded!          ")
        
        # USERNAME
        print(f"\n{'='*70}")
        print(f"📧 STEP 1: USERNAME")
        print(f"{'='*70}")
        print(f"   1. 🖱️  Click on the EMAIL/USERNAME field")
        print(f"   2. ⌨️  Then press ENTER in this console")
        
        input("\n   👉 Press ENTER when ready...")
        
        pyperclip.copy(username)
        time.sleep(0.3)
        
        print(f"\n   📋 Pasting...")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        
        print(f"   ✅ Username pasted: {username}")
        
        # PASSWORD
        print(f"\n{'='*70}")
        print(f"🔑 STEP 2: PASSWORD")
        print(f"{'='*70}")
        print(f"   1. 🖱️  Click on the PASSWORD field")
        print(f"   2. ⌨️  Then press ENTER in this console")
        
        input("\n   👉 Press ENTER when ready...")
        
        pyperclip.copy(password)
        time.sleep(0.3)
        
        print(f"\n   📋 Pasting...")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        
        print(f"   ✅ Password pasted")
        
        # Submit
        print(f"\n{'='*70}")
        print(f"🔨 STEP 3: SUBMIT")
        print(f"{'='*70}")
        
        response = input("\n   Submit automatically? (y/n): ").strip().lower()
        
        if response == 'y':
            print(f"\n   ⏎ Pressing ENTER...")
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(1)
            print(f"   ✅ Form submitted!")
        else:
            print(f"\n   ℹ️  Click 'Login' manually")
        
        # Restore clipboard
        if original_clipboard:
            try:
                pyperclip.copy(original_clipboard)
            except:
                pass
        
        print(f"\n{'='*70}")
        print(f"✅ AUTO-FILL COMPLETE!")
        print(f"{'='*70}\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def open_and_type_credentials_auto(url: str, username: str, password: str, delay: float = 7.0):
    """
    AUTOMATIC METHOD: Tries to fill automatically (may not work everywhere)
    """
    if not PYAUTOGUI_AVAILABLE:
        print("\n❌ PyAutoGUI is not installed")
        return False
    
    if not url:
        return False

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    print(f"\n{'='*70}")
    print(f"🚀 AUTOMATIC AUTO-FILL")
    print(f"{'='*70}")
    
    try:
        original_clipboard = pyperclip.paste() if pyperclip.paste() else ""
        
        print(f"📂 Opening: {url}")
        webbrowser.open(url)
        
        print(f"⏳ Waiting {delay} seconds...")
        time.sleep(delay)
        
        # Focus window
        screen_width, screen_height = pyautogui.size()
        pyautogui.click(screen_width // 2, screen_height // 2)
        time.sleep(1.5)
        
        # USERNAME
        print(f"\n📧 Entering username...")
        pyperclip.copy(username)
        time.sleep(0.5)
        
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)
        pyautogui.press('delete')
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(1.0)
        print(f"   ✅ Username: {username}")
        
        # Move to next field
        print(f"\n⏭️ Moving to password...")
        pyautogui.press('tab')
        time.sleep(1.5)
        
        # PASSWORD
        print(f"\n🔑 Entering password...")
        pyperclip.copy(password)
        time.sleep(0.5)
        
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)
        pyautogui.press('delete')
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(1.0)
        print(f"   ✅ Password entered")
        
        # Submit
        print(f"\n🔨 Submitting...")
        time.sleep(1.0)
        pyautogui.press('enter')
        
        pyperclip.copy(original_clipboard)
        
        print(f"\n✅ Complete!\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def simple_copy_paste_method(url: str, username: str, password: str):
    """
    SIMPLE METHOD: Copy to clipboard, user pastes manually
    """
    if not PYAUTOGUI_AVAILABLE:
        print("\n❌ PyAutoGUI is not installed")
        return False
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    print(f"\n{'='*70}")
    print(f"📋 COPY-PASTE METHOD")
    print(f"{'='*70}")
    
    webbrowser.open(url)
    print(f"✅ Site opened: {url}\n")
    
    time.sleep(3)
    
    # Copy username
    pyperclip.copy(username)
    print(f"📧 USERNAME COPIED: {username}")
    print(f"   👉 Paste with Ctrl+V")
    input(f"   Press ENTER when done...\n")
    
    # Copy password
    pyperclip.copy(password)
    print(f"🔑 PASSWORD COPIED (length: {len(password)})")
    print(f"   👉 Paste with Ctrl+V")
    input(f"   Press ENTER when done...\n")
    
    print(f"✅ Now click 'Login'")
    print(f"{'='*70}\n")
    
    return True


if __name__ == "__main__":
    print("🧪 TEST AUTO-FILL METHODS")
    print("="*70)
    print("\nAvailable methods:")
    print("1. Selenium (recommended) - Automatic scraping")
    print("2. Assisted - You click, we paste")
    print("3. Automatic - Fully automatic")
    print("4. Simple - Manual copy-paste")
    
    choice = input("\nChoose (1/2/3/4): ").strip()
    
    test_url = "https://www.instagram.com"
    test_user = "cicimamr@example.com"
    test_pass = "TestPassword123!"
    
    if choice == "1":
        autofill_with_selenium(test_url, test_user, test_pass)
    elif choice == "2":
        open_and_type_credentials(test_url, test_user, test_pass, delay=5.0)
    elif choice == "3":
        open_and_type_credentials_auto(test_url, test_user, test_pass, delay=7.0)
    elif choice == "4":
        simple_copy_paste_method(test_url, test_user, test_pass)
    else:
        print("❌ Invalid choice")