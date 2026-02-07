import time
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def clean_url(url):
    # Очищаем URL от старых параметров
    if "?" in url:
        url = url.split("?")[0]
    
    # Гарантируем наличие /reviews/
    if "ozon.ru/product/" in url and "/reviews" not in url:
        if url.endswith("/"):
            url += "reviews/"
        else:
            url += "/reviews/"
            
    return url.rstrip("/")

def collect_reviews_from_url(driver, target_url, limit, existing_set, label=""):
    print(f"\n🔎 [{label}] Переход: {target_url}")
    
    driver.get(target_url)
    time.sleep(3) # Ждем прогрузки
    
    collected_count = 0
    page_num = 1
    
    while collected_count < limit:
        print(f"   📄 [{label}] Страница {page_num}...")
        
        # 1. Кликаем "Читать полностью"
        # Ищем по тексту, так как классы кнопок тоже меняются
        try:
            buttons = driver.find_elements(By.XPATH, "//span[contains(text(), 'Читать полностью')]")
            for btn in buttons:
                driver.execute_script("arguments[0].click();", btn)
        except: pass

        # 2. Собираем отзывы (ВЕЧНЫЙ МЕТОД)
        try:
            # Мы ищем ВСЕ элементы, у которых есть атрибут data-review-uuid.
            # Это контейнер всего отзыва.
            review_cards = driver.find_elements(By.XPATH, "//div[@data-review-uuid]")
            
            count_before = len(existing_set)
            
            for card in review_cards:
                # Мы берем весь текст карточки. 
                # Там будет: Имя, Дата, "Достоинства:", текст, "Недостатки:", текст.
                # Для Gemini это даже лучше — он поймет структуру.
                full_text = card.text.strip()
                
                # Фильтруем пустые или слишком короткие (например, удаленные отзывы)
                # 30 символов — чтобы отсечь мусор, но оставить "Все ок" + имя
                if len(full_text) > 30: 
                    # Очищаем от лишних переносов строк для компактности
                    clean_text = " ".join(full_text.splitlines())
                    existing_set.add(clean_text)
            
            new_in_step = len(existing_set) - count_before
            collected_count += new_in_step
            
            print(f"   ✅ +{new_in_step} новых. (Всего: {len(existing_set)})")

            # Если ничего не нашли (даже дублей) и это не первая страница - стоп
            if len(review_cards) == 0 and page_num > 1:
                print(f"   🏁 [{label}] Отзывы кончились (элементы не найдены).")
                break
            
            if collected_count >= limit:
                print(f"   🏁 [{label}] Лимит выполнен.")
                break

        except Exception as e:
            print(f"   ⚠️ Ошибка сбора: {e}")

        # 3. Листаем дальше
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Ищем ссылку внутри элемента с текстом "Дальше"
            next_link = driver.find_element(By.XPATH, "//a[descendant::*[contains(text(), 'Дальше')]]")
            next_url = next_link.get_attribute("href")
            
            if next_url and "ozon.ru" in next_url:
                # ВАЖНО: Сохраняем фильтр "reviewsVariantMode=2" (Этот вариант товара)
                if "reviewsVariantMode" not in next_url:
                    separator = "&" if "?" in next_url else "?"
                    next_url += f"{separator}reviewsVariantMode=2"
                
                driver.get(next_url)
                page_num += 1
                time.sleep(3)
            else:
                print(f"   🏁 [{label}] Кнопка 'Дальше' не активна или ссылка пустая.")
                break
        except:
            print(f"   🏁 [{label}] Страницы кончились.")
            break

async def parse_ozon_reviews(url, max_reviews=100, max_negative=50):
    base_url = clean_url(url)
    print(f"🚀 ЗАПУСК: {max_reviews} свежих + {max_negative} негативных")
    print("🛡️ Используем метод поиска по data-review-uuid (без классов)")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    all_reviews = set()

    # reviewsVariantMode=2 — фильтр "Этот вариант товара"
    
    try:
        # ЭТАП 1: Свежие
        url_fresh = base_url + "?sort=published_at_desc&reviewsVariantMode=2"
        collect_reviews_from_url(driver, url_fresh, max_reviews, all_reviews, label="Свежие")

        # ЭТАП 2: Негатив
        if max_negative > 0:
            url_bad = base_url + "?sort=score_asc&reviewsVariantMode=2"
            collect_reviews_from_url(driver, url_bad, max_negative, all_reviews, label="Негатив")

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        driver.quit()

    result_list = list(all_reviews)
    print(f"📊 ИТОГ: Передаем {len(result_list)} отзывов.")
    return result_list