from ..utils import *

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)


sk_card_recommend_pool = ProcessPoolExecutor(max_workers=1)


def _sk_card_recommend_work(user_id: int, live_type: str, music_key: str, music_diff: str, chara_name: str, topk: int):
    logger.info(f"开始自动组卡: ({user_id}, {live_type}, {music_key}, {music_diff}, {chara_name}, {topk})")
    assert live_type in ["multi", "single", "auto", "challenge"]
    assert music_diff in ["easy", "normal", "hard", "expert", "master", "append"]

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://3-3.dev/sekai/deck-recommend")
        # 等待页面加载完成
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[text()='用户ID']")))

        # 填入用户ID
        driver.find_element(By.XPATH, f"//*[text()='用户ID']/..//input").send_keys(user_id)

        # 选择LIVE类型
        if live_type == 'challenge':
            driver.find_element(By.XPATH, f"//*[text()='挑战']").click()
            # 选择角色
            assert chara_name
            driver.find_element(By.XPATH, f"//*[text()='角色']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{chara_name}']").click()
            except: raise Exception(f"无法选中角色: {chara_name}")
        else: 
            if live_type == 'single':
                driver.find_element(By.XPATH, f"//*[text()='单人Live']").click()
            elif live_type == 'auto':
                driver.find_element(By.XPATH, f"//*[text()='自动Live']").click()

        # 选择歌曲
        if music_key:
            driver.find_element(By.XPATH, f"//*[text()='歌曲']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{music_key}']").click()
            except: raise Exception(f"无法选中歌曲: {music_key}")
        
        # 选择难度
        if music_diff:
            driver.find_element(By.XPATH, f"//*[text()='难度']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{music_diff}']").click()
            except: raise Exception(f"无法选中难度: {music_diff}")

        # 开始组卡
        driver.find_element(By.XPATH, "//*[text()='自动组卡！']").click()
        logger.info("组卡选项已提交，等待计算完毕")
        # 等待页面加载完成
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//*[text()='排名']")))

        driver.execute_script("document.documentElement.style.overflow = 'hidden';")
        body = driver.find_element(By.TAG_NAME, "body")
        width = driver.execute_script("return arguments[0].getBoundingClientRect().width;", body)
        height = driver.execute_script("return arguments[0].getBoundingClientRect().height;", body)
        driver.set_window_size(width, height)

        results = []
        tbody = driver.find_element(By.XPATH, "//*[text()='排名']/../../../tbody")
        # 遍历前topk的卡组
        for i, tr in enumerate(tbody.find_elements(By.TAG_NAME, "tr")):
            if i >= topk: break
            item = {}
            tds = tr.find_elements(By.TAG_NAME, "td")
            item['score'] = int(tds[1].text)
            if live_type == 'challenge':
                item['power'] = int(tds[3].text)
            else:
                item['bonus'] = float(tds[3].text)
                item['power'] = int(tds[4].text)
            item['cards'] = []
            for div in tds[2].find_element(By.TAG_NAME, "div").find_elements(By.TAG_NAME, "div"):
                title = div.find_element(By.TAG_NAME, "svg").find_element(By.TAG_NAME, "title").get_attribute("innerHTML")
                card_id = int(title[2:].split('<', 1)[0])
                item['cards'].append(card_id)
            results.append(item)

        logger.info(f"自动组卡完成")
        return results

    except Exception as e:
        logger.print_exc("自动组卡失败")
        raise ReplyException(f"自动组卡失败: {type(e).__name__}")

    finally:
        driver.quit()


# sk自动组卡
async def sk_card_recommend(user_id: int, live_type: str, music_key: str, music_diff: str, chara_name: str=None, topk=5):
    return await asyncio.wait_for(
        run_in_pool(_sk_card_recommend_work, user_id, live_type, music_key, music_diff, chara_name, topk, pool=sk_card_recommend_pool),
        timeout=60,
    )


