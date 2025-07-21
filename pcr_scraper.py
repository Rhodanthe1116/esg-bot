import httpx
from bs4 import BeautifulSoup
import re
import json
import logging
import time
import asyncio  # 引入 asyncio 以便直接執行 main_scraper

# 配置日誌
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 基礎 URL
BASE_URL = "https://cfp-calculate.tw/cfpc/Carbon/WebPage/FLPCRDoneList.aspx"


async def fetch_page(client: httpx.AsyncClient, url: str, data: dict = None) -> str:
    """
    非同步獲取網頁內容，支援 GET 和 POST 請求。
    Args:
        client (httpx.AsyncClient): httpx 非同步客戶端。
        url (str): 目標 URL。
        data (dict): POST 請求的表單數據。
    Returns:
        str: 網頁的 HTML 內容。
    """
    try:
        if data:
            # 對於 POST 請求，使用 data 參數
            response = await client.post(url, data=data, timeout=30)
        else:
            # 對於 GET 請求
            response = await client.get(url, timeout=30)
        response.raise_for_status()  # 對於 4xx/5xx 狀態碼拋出異常
        logger.info(f"成功獲取頁面: {url} (狀態碼: {response.status_code})")
        return response.text
    except httpx.RequestError as e:
        logger.error(f"請求失敗: {e}")
        return ""
    except Exception as e:
        logger.error(f"獲取頁面時發生未知錯誤: {e}")
        return ""


def parse_pcr_table(html_content: str) -> list[dict]:
    """
    解析 HTML 內容，從表格中提取 PCR 數據。
    Args:
        html_content (str): 網頁的 HTML 內容。
    Returns:
        list[dict]: 包含 PCR 數據的字典列表。
    """
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", id="ContentPlaceHolder1_sgv")

    if not table:
        logger.warning("未找到 PCR 數據表格 (ID: ContentPlaceHolder1_sgv)。")
        return []

    headers = []
    # 提取表頭 (假設第一行是表頭)
    header_row = table.find("tr")
    if header_row:
        for th in header_row.find_all("th"):
            # 清理表頭文本，移除 <br> 和多餘空格
            header_text = (
                th.get_text(separator=" ", strip=True).replace("\n", " ").strip()
            )
            headers.append(header_text)

    # 預期的表頭順序和對應的鍵名，用於數據映射
    expected_headers_map = {
        "PCR來源 PCR種類": "pcr_source_type",
        "文件名稱 PCR登錄編號": "document_name_reg_no",
        "制定者/共同訂定者": "developer",
        "版本": "version",
        "核准日期 有效期限": "approval_effective_date",
        "適用產品範圍": "product_scope",
        "下載": "download_link",
        "意見回饋": "feedback_link",
    }

    # 將實際提取的表頭映射到預期的鍵名
    mapped_headers = [expected_headers_map.get(h, h) for h in headers]

    pcr_data = []
    # 遍歷每一行數據 (跳過表頭行)
    # 數據行通常有固定數量的 <td> 元素，而分頁行可能只有一個 colspan 的 <td>
    for row in table.find_all("tr")[1:]:  # 從第二行開始 (跳過表頭)
        cells = row.find_all("td")

        # 判斷是否為數據行：
        # 1. 如果沒有 cells，則跳過空行
        # 2. 如果只有一個 cell 且帶有 colspan 屬性，則判斷為分頁行，跳過
        # 3. 如果 cells 數量少於預期的表頭數量，則判斷為不完整數據行，跳過
        if not cells:
            continue
        if len(cells) == 1 and cells[0].has_attr("colspan"):
            logger.debug(f"跳過分頁行: {cells[0].get_text(strip=True)}")
            continue
        if len(cells) < len(mapped_headers):
            logger.warning(f"行數據不完整或格式異常，跳過: {row.get_text(strip=True)}")
            continue

        entry = {}
        for i, header_key in enumerate(mapped_headers):
            cell_content = cells[i]
            if header_key == "download_link":
                # 提取下載連結
                link_tag = cell_content.find("a", target="_blank")
                entry[header_key] = (
                    link_tag["href"] if link_tag and "href" in link_tag.attrs else ""
                )
            elif header_key == "feedback_link":
                # 提取意見回饋的 JavaScript 函數參數 (數字 ID)
                js_link = cell_content.find(
                    "a", href=re.compile(r"javascript:CallSubwin\(\'(\d+)\'\)")
                )
                if js_link:
                    match = re.search(r"CallSubwin\(\'(\d+)\'\)", js_link["href"])
                    entry[header_key] = match.group(1) if match else ""
                else:
                    entry[header_key] = ""
            else:
                # 提取文本內容，並清理換行符和多餘空格
                text_content = (
                    cell_content.get_text(separator=" ", strip=True)
                    .replace("\n", " ")
                    .strip()
                )
                entry[header_key] = text_content

        # 進一步解析 'document_name_reg_no' (文件名稱 PCR登錄編號)
        doc_reg_parts = entry.get("document_name_reg_no", "").split(" ")
        entry["document_name"] = doc_reg_parts[0] if doc_reg_parts else ""
        entry["pcr_reg_no"] = doc_reg_parts[-1] if len(doc_reg_parts) > 1 else ""
        del entry["document_name_reg_no"]  # 移除原始合併欄位

        # 進一步解析 'approval_effective_date' (核准日期 有效期限)
        app_eff_parts = entry.get("approval_effective_date", "").split(" ")
        entry["approval_date"] = app_eff_parts[0] if app_eff_parts else ""
        entry["effective_date"] = (
            " ".join(app_eff_parts[1:]) if len(app_eff_parts) > 1 else ""
        )
        del entry["approval_effective_date"]  # 移除原始合併欄位


        pcr_data.append(entry)

    return pcr_data


def extract_initial_form_data_and_checkboxes(html_content: str) -> dict:
    """
    從 HTML 內容中提取 ASP.NET Web Forms 的隱藏欄位和所有文件類型 checkbox 的值。
    這個函數用於首次載入頁面時，獲取所有需要提交的表單數據，包括所有 checkbox。
    Args:
        html_content (str): 網頁的 HTML 內容。
    Returns:
        dict: 包含 __VIEWSTATE, __EVENTVALIDATION 以及所有 chk_type 值的字典。
    """
    soup = BeautifulSoup(html_content, "html.parser")
    form_data = {}
    # 提取所有隱藏欄位
    for input_tag in soup.find_all("input", type="hidden"):
        if input_tag.get("name") in [
            "__VIEWSTATE",
            "__VIEWSTATEGENERATOR",
            "__EVENTVALIDATION",
            "__EVENTTARGET",
            "__EVENTARGUMENT",
        ]:
            form_data[input_tag.get("name")] = input_tag.get("value", "")

    # 提取所有 chk_type 的值，並將它們加入 form_data，模擬全部勾選
    for chk in soup.find_all(
        "input",
        {
            "type": "checkbox",
            "name": re.compile(r"ctl00\$ContentPlaceHolder1\$chk_type\$\d+"),
        },
    ):
        form_data[chk["name"]] = chk["value"]

    # 提取 radio button 的值，確保 '全部' 被選中
    rdb_status_all = soup.find(
        "input", {"name": "ctl00$ContentPlaceHolder1$rdb_status", "value": "全部"}
    )
    if rdb_status_all:
        form_data[rdb_status_all["name"]] = rdb_status_all["value"]

    # 提取其他輸入框的當前值，以確保 POST 請求的完整性 (通常為空，但仍需包含)
    txt_pcr_name = soup.find("input", id="ContentPlaceHolder1_txt_PCRName")
    if txt_pcr_name:
        form_data[txt_pcr_name["name"]] = txt_pcr_name.get("value", "")

    tbx_ccccode = soup.find("input", id="ContentPlaceHolder1_tbx_ccccode")
    if tbx_ccccode:
        form_data[tbx_ccccode["name"]] = tbx_ccccode.get("value", "")

    txt_jointly = soup.find("input", id="ContentPlaceHolder1_txt_Jointly")
    if txt_jointly:
        form_data[txt_jointly["name"]] = txt_jointly.get("value", "")

    # 確保查詢按鈕的 target 也被識別，用於第一次提交
    btn_qry = soup.find("input", id="ContentPlaceHolder1_btn_qry")
    if btn_qry and btn_qry.get("name"):
        form_data["btn_qry_name"] = btn_qry["name"]

    return form_data


def extract_hidden_form_fields(html_content: str) -> dict:
    """
    從 HTML 內容中提取 ASP.NET Web Forms 的隱藏欄位 (__VIEWSTATE, __EVENTVALIDATION 等)。
    這個函數用於後續分頁時，更新頁面狀態。
    Args:
        html_content (str): 網頁的 HTML 內容。
    Returns:
        dict: 包含隱藏欄位的字典。
    """
    soup = BeautifulSoup(html_content, "html.parser")
    form_data = {}
    for input_tag in soup.find_all("input", type="hidden"):
        if input_tag.get("name") in [
            "__VIEWSTATE",
            "__VIEWSTATEGENERATOR",
            "__EVENTVALIDATION",
            "__EVENTTARGET",
            "__EVENTARGUMENT",
        ]:
            form_data[input_tag.get("name")] = input_tag.get("value", "")
    return form_data


async def scrape_all_pcr_data() -> list[dict]:
    """
    爬取所有 PCR 頁面並收集數據。
    Returns:
        list[dict]: 包含所有 PCR 數據的列表。
    """
    all_pcr_records = []

    async with httpx.AsyncClient() as client:
        # --- 步驟 1: 獲取初始頁面並提取表單數據和所有 checkbox 值 ---
        logger.info("正在獲取初始頁面並提取表單數據...")
        initial_html = await fetch_page(client, BASE_URL)
        if not initial_html:
            return []

        # 這裡使用新的函數來提取所有初始表單數據，包括所有 checkbox 的值
        form_data_for_initial_query = extract_initial_form_data_and_checkboxes(
            initial_html
        )

        # --- 步驟 2: 模擬點擊「查詢」按鈕，載入所有數據 ---
        logger.info("模擬點擊「查詢」按鈕以載入所有數據...")
        # 查詢按鈕的 EVENTTARGET 通常是其 name 屬性
        query_button_target = form_data_for_initial_query.get(
            "btn_qry_name", "ctl00$ContentPlaceHolder1$btn_qry"
        )  # 預設值以防萬一

        # 創建用於提交查詢的 POST 數據
        query_post_data = {
            "__EVENTTARGET": query_button_target,
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": form_data_for_initial_query.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": form_data_for_initial_query.get(
                "__VIEWSTATEGENERATOR", ""
            ),
            "__EVENTVALIDATION": form_data_for_initial_query.get(
                "__EVENTVALIDATION", ""
            ),
            # 包含其他輸入框的當前值（通常為空）
            "ctl00$ContentPlaceHolder1$txt_PCRName": form_data_for_initial_query.get(
                "ctl00$ContentPlaceHolder1$txt_PCRName", ""
            ),
            "ctl00$ContentPlaceHolder1$txt_Jointly": form_data_for_initial_query.get(
                "ctl00$ContentPlaceHolder1$txt_Jointly", ""
            ),
            "ctl00$ContentPlaceHolder1$tbx_ccccode": form_data_for_initial_query.get(
                "ctl00$ContentPlaceHolder1$tbx_ccccode", ""
            ),
            "ctl00$ContentPlaceHolder1$rdb_status": form_data_for_initial_query.get(
                "ctl00$ContentPlaceHolder1$rdb_status", "全部"
            ),  # 確保 '全部' 被選中
        }
        # 添加所有文件類型 checkbox 的值，模擬全部勾選
        for key, value in form_data_for_initial_query.items():
            if key.startswith("ctl00$ContentPlaceHolder1$chk_type$"):
                query_post_data[key] = value

        # 提交查詢請求
        query_result_html = await fetch_page(client, BASE_URL, data=query_post_data)
        if not query_result_html:
            logger.error("未能成功提交查詢請求。")
            return []

        # 更新 form_data 以便後續分頁使用最新的狀態 (只提取隱藏欄位)
        form_data_for_pagination = extract_hidden_form_fields(query_result_html)

        # --- 步驟 3: 解析第一頁（查詢結果頁）的數據 ---
        page_num = 1
        current_page_records = parse_pcr_table(query_result_html)
        all_pcr_records.extend(current_page_records)
        logger.info(
            f"第 {page_num} 頁抓取到 {len(current_page_records)} 條記錄 (查詢結果頁)。"
        )

        # 查找總頁數
        soup = BeautifulSoup(query_result_html, "html.parser")
        # 修正總頁數提取邏輯：從包含 "第X頁/共Y頁" 的 span 元素中提取
        pager_info_span = soup.find("span", class_="pager")
        total_pages = 1
        if pager_info_span:
            pager_text = pager_info_span.get_text(strip=True)
            match = re.search(r"共(\d+)頁", pager_text)
            if match:
                # total_pages = int(2)
                total_pages = int(match.group(1))
                logger.info(f"總頁數: {total_pages}")
            else:
                logger.warning("未能在分頁資訊中找到總頁數，假設只有一頁。")
        else:
            logger.warning("未找到分頁資訊容器，假設只有一頁。")

        # --- 步驟 4: 遍歷後續分頁 ---
        # 這裡需要一個變數來保存上一頁的 HTML，以便從中提取下一頁的 PostBack 目標
        last_page_html = query_result_html

        for page_num in range(2, total_pages + 1):
            logger.info(f"正在獲取第 {page_num} 頁...")

            next_page_link_target = None
            # 從上一頁的 HTML 中提取分頁連結
            current_soup_for_pager = BeautifulSoup(last_page_html, "html.parser")

            # 找到包含分頁連結的 div，它是表格的下一個兄弟元素
            pager_container_div = current_soup_for_pager.find("div", class_="stripeMe")

            if pager_container_div:
                # 在這個容器內找到所有 <a> 連結 (這些是分頁連結)
                pager_links = pager_container_div.find_all("a")

                logger.debug(f"第 {page_num} 頁找到 {len(pager_links)} 個分頁連結。")
                for link in pager_links:
                    link_text = link.get_text(strip=True)
                    link_href = link.get("href", "")
                    logger.debug(f"連結文本: '{link_text}', href: '{link_href}'")

                    # 檢查連結文本是否為當前頁碼
                    if link_text == str(page_num):
                        match = re.search(r"__doPostBack\('([^']+)'", link_href)
                        if match:
                            next_page_link_target = match.group(1)
                            logger.debug(
                                f"找到第 {page_num} 頁的 PostBack 目標: {next_page_link_target}"
                            )
                            break

            if not next_page_link_target:
                logger.warning(f"未找到第 {page_num} 頁的 PostBack 目標，停止爬取。")
                break

            # 構建分頁的 POST 數據
            post_data = {
                "__EVENTTARGET": next_page_link_target,
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": form_data_for_pagination.get("__VIEWSTATE", ""),
                "__VIEWSTATEGENERATOR": form_data_for_pagination.get(
                    "__VIEWSTATEGENERATOR", ""
                ),
                "__EVENTVALIDATION": form_data_for_pagination.get(
                    "__EVENTVALIDATION", ""
                ),
                # 再次包含所有表單欄位的值，確保狀態一致性
                "ctl00$ContentPlaceHolder1$txt_PCRName": form_data_for_initial_query.get(
                    "ctl00$ContentPlaceHolder1$txt_PCRName", ""
                ),
                "ctl00$ContentPlaceHolder1$txt_Jointly": form_data_for_initial_query.get(
                    "ctl00$ContentPlaceHolder1$txt_Jointly", ""
                ),
                "ctl00$ContentPlaceHolder1$tbx_ccccode": form_data_for_initial_query.get(
                    "ctl00$ContentPlaceHolder1$tbx_ccccode", ""
                ),
                "ctl00$ContentPlaceHolder1$rdb_status": form_data_for_initial_query.get(
                    "ctl00$ContentPlaceHolder1$rdb_status", "全部"
                ),
            }
            # 再次添加所有文件類型 checkbox 的值 (從初始提取的數據中獲取)
            for key, value in form_data_for_initial_query.items():
                if key.startswith("ctl00$ContentPlaceHolder1$chk_type$"):
                    post_data[key] = value

            # 執行 POST 請求
            next_page_html = await fetch_page(client, BASE_URL, data=post_data)
            if not next_page_html:
                logger.error(f"無法獲取第 {page_num} 頁的內容，停止爬取。")
                break

            # 更新 form_data_for_pagination 以便下一輪請求使用最新的 __VIEWSTATE 等
            form_data_for_pagination = extract_hidden_form_fields(next_page_html)
            # 更新 last_page_html 以便下一輪提取分頁連結
            last_page_html = next_page_html

            # 解析當前頁數據
            current_page_records = parse_pcr_table(next_page_html)
            if not current_page_records:
                logger.info(
                    f"第 {page_num} 頁沒有找到記錄，可能已達最後一頁或解析錯誤。"
                )
                break
            all_pcr_records.extend(current_page_records)
            logger.info(f"第 {page_num} 頁抓取到 {len(current_page_records)} 條記錄。")

            # 為了避免過於頻繁的請求，可以加入延遲
            time.sleep(1)  # 延遲 1 秒

    return all_pcr_records


async def main_scraper():
    logger.info("開始爬取環境部 PCR 清單...")
    pcr_data = await scrape_all_pcr_data()

    if pcr_data:
        logger.info(f"總共抓取到 {len(pcr_data)} 條 PCR 記錄。")
        with open("pcr_list_scraped.json", "w", encoding="utf-8") as f:
            json.dump(pcr_data, f, ensure_ascii=False, indent=4)
        logger.info("數據已儲存到 pcr_list_scraped.json")
        return pcr_data
    else:
        logger.warning("未能抓取到任何 PCR 數據。")
        return []


if __name__ == "__main__":
    # 使用 asyncio.run() 執行非同步主函數
    asyncio.run(main_scraper())
