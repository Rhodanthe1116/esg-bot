import httpx
from bs4 import BeautifulSoup
import re
import json
import logging
import time

# 配置日誌
# 為了更詳細的除錯，將 level 設置為 logging.DEBUG
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://cfp-calculate.tw/cfpc/Carbon/WebPage/FLPCRDoneList.aspx"
# 注意：根據提供的HTML，下載連結本身是相對URL，需要拼接BASE_URL
DOWNLOAD_BASE_URL = "https://cfp-calculate.tw/cfpc/Carbon/WebPage/" 

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
            logger.debug(f"發送 POST 請求到: {url}，數據: {json.dumps(data, ensure_ascii=False)[:200]}...") # 打印部分數據
            response = await client.post(url, data=data, timeout=30)
        else:
            logger.debug(f"發送 GET 請求到: {url}")
            response = await client.get(url, timeout=30)
        response.raise_for_status() # 對於 4xx/5xx 狀態碼拋出異常
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
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', id='ContentPlaceHolder1_sgv')
    
    if not table:
        logger.warning("未找到 PCR 數據表格 (ID: ContentPlaceHolder1_sgv)。")
        return []

    headers = []
    # 提取表頭 (假設第一行是表頭)
    header_row = table.find('tr')
    if header_row:
        for th in header_row.find_all('th'):
            # 清理表頭文本，移除 <br> 和多餘空格
            header_text = th.get_text(separator=' ', strip=True).replace('\n', ' ').strip()
            headers.append(header_text)
    
    # 預期的表頭順序和對應的鍵名
    expected_headers_map = {
        "PCR來源 PCR種類": "pcr_source_type",
        "文件名稱 PCR登錄編號": "document_name_reg_no",
        "制定者/共同訂定者": "developer",
        "版本": "version",
        "核准日期 有效期限": "approval_effective_date",
        "適用產品範圍": "product_scope",
        "下載": "download_link",
        "意見回饋": "feedback_link"
    }

    mapped_headers = [expected_headers_map.get(h, h) for h in headers]
    logger.debug(f"解析到的表頭: {mapped_headers}")

    pcr_data = []
    # 遍歷每一行數據 (跳過表頭行)
    for row_idx, row in enumerate(table.find_all('tr')[1:]): # 從第二行開始 (跳過表頭)
        cells = row.find_all('td')
        
        # 判斷是否為數據行：數據行通常有與表頭數量匹配的 td 元素，且第一個 td 不會是分頁器
        if not cells: # 空行
            logger.debug(f"第 {row_idx+1} 行是空行，跳過。")
            continue
        # 檢查是否為分頁器行 (通常只有一個 td 且其內容包含分頁資訊)
        if len(cells) == 1 and cells[0].find('span', class_='pager'):
            logger.debug(f"第 {row_idx+1} 行是分頁行，跳過: {cells[0].get_text(strip=True)}")
            continue
        if len(cells) < len(mapped_headers): # 數據不完整，可能是其他非數據行
            logger.warning(f"第 {row_idx+1} 行數據不完整或格式異常，跳過: {row.get_text(strip=True)}")
            continue

        entry = {}
        # 儲存原始的 product_scope 文本，因為 CCC Code 提取和 product_scope 清理會基於它
        raw_product_scope_text = "" 

        for i, header_key in enumerate(mapped_headers):
            cell_content = cells[i]
            if header_key == "download_link":
                # 提取下載連結，原始HTML中href是相對URL，需要拼接
                link_tag = cell_content.find('a', target='_blank')
                relative_path = link_tag['href'] if link_tag and 'href' in link_tag.attrs else ''
                if relative_path and not relative_path.startswith('http'):
                    entry[header_key] = f"{DOWNLOAD_BASE_URL}{relative_path}"
                else:
                    entry[header_key] = relative_path
                logger.debug(f"提取下載連結: {entry[header_key]}")
            elif header_key == "feedback_link":
                # 提取意見回饋的 JavaScript 函數參數
                js_link = cell_content.find('a', href=re.compile(r'javascript:CallSubwin\(\'(\d+)\'\)'))
                if js_link:
                    match = re.search(r'CallSubwin\(\'(\d+)\'\)', js_link['href'])
                    entry[header_key] = match.group(1) if match else ''
                else:
                    entry[header_key] = ''
                logger.debug(f"提取意見回饋連結ID: {entry[header_key]}")
            elif header_key == "product_scope":
                # 先保存原始的 product_scope 文本
                raw_product_scope_text = cell_content.get_text(separator=' ', strip=True).replace('\n', ' ').strip()
                entry[header_key] = raw_product_scope_text # 暫時保存原始文本
            else:
                # 提取文本內容，並清理換行符和多餘空格
                text_content = cell_content.get_text(separator=' ', strip=True).replace('\n', ' ').strip()
                entry[header_key] = text_content
        
        # 進一步解析 'document_name_reg_no' 和 'approval_effective_date'
        doc_reg_parts = entry.get('document_name_reg_no', '').split(' ')
        entry['document_name'] = doc_reg_parts[0] if doc_reg_parts else ''
        entry['pcr_reg_no'] = doc_reg_parts[-1] if len(doc_reg_parts) > 1 else ''
        del entry['document_name_reg_no'] # 移除原始合併欄位
        logger.debug(f"解析文件名稱: {entry['document_name']}, PCR登錄編號: {entry['pcr_reg_no']}")

        app_eff_parts = entry.get('approval_effective_date', '').split(' ')
        entry['approval_date'] = app_eff_parts[0] if app_eff_parts else ''
        entry['effective_date'] = ' '.join(app_eff_parts[1:]) if len(app_eff_parts) > 1 else ''
        del entry['approval_effective_date'] # 移除原始合併欄位
        logger.debug(f"解析核准日期: {entry['approval_date']}, 有效期限: {entry['effective_date']}")

        # 從原始 product_scope 文本中提取 CCC Codes (修正邏輯，更全面掃描)
        logger.debug(f"原始 product_scope (用於CCC Code提取): {raw_product_scope_text[:200]}...") 
        
        # 嘗試找到 CCC Code 歸類描述的開始
        # 匹配 "CCC Code)歸類如下:" 或 "CCCcode)歸類如下號列：" 等變體
        # 這裡使用非貪婪匹配 `.*?` 以避免匹配過多內容
        ccc_section_start_match = re.search(r'(?:CCC ?Code|C\.C\.C ?Code|CCCCode)[)）]?\s*(?:歸類(?:之號列：|如下號列：|如下:)\s*)?(.*)', raw_product_scope_text, re.DOTALL)
        
        extracted_ccc_text_block = ""
        if ccc_section_start_match:
            # 從匹配到的位置開始，提取後續的文本作為 CCC Code 區塊
            extracted_ccc_text_block = ccc_section_start_match.group(1).strip()
            logger.debug(f"提取到的CCC Code文本區塊: {extracted_ccc_text_block[:200]}...") 
            
            # 提取所有可能的 CCC Codes 格式
            # 涵蓋：DDDD.DD.DD.DD-D, DDDDDDDDDDD, DDDD.DD.DD, DDDD.DD, DDDD (可能帶有前導數字和點，例如 "1.84241000117")
            # 修正後的 regex，更精確地捕獲，並允許後綴的中文或空格，但只在捕獲組中捕獲代碼本身
            ccc_codes_patterns_list = re.findall(
                r'(?:\b\d+\.\s*)?(\d{4}\.\d{2}\.\d{2}\.\d{2}-\d)\b(?:[^\d\.\-]*?)|' # Pattern 1: DDDD.DD.DD.DD-D (11碼)
                r'(?:\b\d+\.\s*)?(\d{11})\b(?:[^\d\.\-]*?)|' # Pattern 2: 11-digit number (如 84145100002)
                r'(?:\b\d+\.\s*)?(\d{4}\.\d{2}\.\d{2})\b(?:[^\d\.\-]*?)|' # Pattern 3: DDDD.DD.DD (8碼)
                r'(?:\b\d+\.\s*)?(\d{4}\.\d{2})\b(?:[^\d\.\-]*?)|' # Pattern 4: DDDD.DD (6碼)
                r'(?:\b\d+\.\s*)?(\d{4})\b(?:[^\d\.\-]*?)' # Pattern 5: DDDD (4碼)
                , extracted_ccc_text_block
            )
            
            # ccc_codes_patterns_list 會是 tuple 的列表，需要扁平化並過濾空值
            found_ccc_codes = [code for tpl in ccc_codes_patterns_list for code in tpl if code]
            
            # 額外處理可能存在的 CCC Code 後綴中文描述，例如 "8714.96.10-踏板及其零件。"
            # 這裡需要對每個找到的代碼進行清理，去除其後的非代碼字符
            cleaned_and_filtered_codes = []
            for code in found_ccc_codes:
                # 移除代碼後面的非數字、非點、非連字符的字符，直到遇到空格或中文
                cleaned_code = re.sub(r'[^\d\.\-].*$', '', code).strip() # 移除結尾的非數字/點/連字符
                if cleaned_code:
                    cleaned_and_filtered_codes.append(cleaned_code)

            # 去重並排序
            entry['ccc_codes'] = ";".join(sorted(list(set(filter(None, cleaned_and_filtered_codes)))))
            logger.debug(f"提取並清理後的CCC Codes: {entry['ccc_codes']}")
            
            # 從 product_scope 中移除 CCC Code 相關的描述，只保留純粹的產品範圍描述
            # 這裡將原始 product_scope 文本中，從 CCC Code 歸類描述開始的部分移除
            entry['product_scope'] = raw_product_scope_text[:ccc_section_start_match.start()].strip()
            logger.debug(f"清理CCC Code後的product_scope: {entry['product_scope'][:200]}...")
        else:
            entry['ccc_codes'] = ''
            entry['product_scope'] = raw_product_scope_text # 如果沒有找到 CCC Code 區塊，則保留原始 product_scope
            logger.debug("未找到CCC Code歸類段落。")


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
    soup = BeautifulSoup(html_content, 'html.parser')
    form_data = {}
    for input_tag in soup.find_all('input', type='hidden'):
        if input_tag.get('name') in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION', '__EVENTTARGET', '__EVENTARGUMENT']:
            form_data[input_tag.get('name')] = input_tag.get('value', '')
    
    # 提取所有 chk_type 的值，並將它們加入 form_data，模擬全部勾選
    for chk in soup.find_all('input', {'type': 'checkbox', 'name': re.compile(r'ctl00\$ContentPlaceHolder1\$chk_type\$\d+')}):
        form_data[chk['name']] = chk['value']
    
    # 提取 radio button 的值，確保 '全部' 被選中
    rdb_status_all = soup.find('input', {'name': 'ctl00$ContentPlaceHolder1$rdb_status', 'value': '全部'})
    if rdb_status_all:
        form_data[rdb_status_all['name']] = rdb_status_all['value']

    # 提取其他輸入框的當前值，以確保 POST 請求的完整性
    txt_pcr_name = soup.find('input', id='ContentPlaceHolder1_txt_PCRName')
    if txt_pcr_name:
        form_data[txt_pcr_name['name']] = txt_pcr_name.get('value', '')

    tbx_ccccode = soup.find('input', id='ContentPlaceHolder1_tbx_ccccode')
    if tbx_ccccode:
        form_data[tbx_ccccode['name']] = tbx_ccccode.get('value', '')

    txt_jointly = soup.find('input', id='ContentPlaceHolder1_txt_Jointly')
    if txt_jointly:
        form_data[txt_jointly['name']] = txt_jointly.get('value', '')

    # 確保查詢按鈕的 target 也被識別，用於第一次提交
    btn_qry = soup.find('input', id='ContentPlaceHolder1_btn_qry')
    if btn_qry and btn_qry.get('name'):
        form_data['btn_qry_name'] = btn_qry['name']

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
    soup = BeautifulSoup(html_content, 'html.parser')
    form_data = {}
    for input_tag in soup.find_all('input', type='hidden'):
        if input_tag.get('name') in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION', '__EVENTTARGET', '__EVENTARGUMENT']:
            form_data[input_tag.get('name')] = input_tag.get('value', '')
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
        form_data_for_initial_query = extract_initial_form_data_and_checkboxes(initial_html)
        
        # --- 步驟 2: 模擬點擊「查詢」按鈕，載入所有數據 ---
        logger.info("模擬點擊「查詢」按鈕以載入所有數據...")
        # 查詢按鈕的 EVENTTARGET 通常是其 name 屬性
        query_button_target = form_data_for_initial_query.get('btn_qry_name', 'ctl00$ContentPlaceHolder1$btn_qry') # 預設值以防萬一
        
        # 創建用於提交查詢的 POST 數據
        query_post_data = {
            '__EVENTTARGET': query_button_target,
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': form_data_for_initial_query.get('__VIEWSTATE', ''),
            '__VIEWSTATEGENERATOR': form_data_for_initial_query.get('__VIEWSTATEGENERATOR', ''),
            '__EVENTVALIDATION': form_data_for_initial_query.get('__EVENTVALIDATION', ''),
            # 包含其他輸入框的當前值（通常為空）
            'ctl00$ContentPlaceHolder1$txt_PCRName': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$txt_PCRName', ''),
            'ctl00$ContentPlaceHolder1$txt_Jointly': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$txt_Jointly', ''),
            'ctl00$ContentPlaceHolder1$tbx_ccccode': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$tbx_ccccode', ''),
            'ctl00$ContentPlaceHolder1$rdb_status': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$rdb_status', '全部'), # 確保 '全部' 被選中
        }
        # 添加所有文件類型 checkbox 的值，模擬全部勾選
        for key, value in form_data_for_initial_query.items():
            if key.startswith('ctl00$ContentPlaceHolder1$chk_type$'):
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
        logger.info(f"第 {page_num} 頁抓取到 {len(current_page_records)} 條記錄 (查詢結果頁)。")

        # 查找總頁數
        soup = BeautifulSoup(query_result_html, 'html.parser')
        # 修正總頁數提取邏輯：從包含 "第X頁/共Y頁" 的 span 元素中提取
        pager_info_span = soup.find('span', class_='pager')
        total_pages = 1
        if pager_info_span:
            pager_text = pager_info_span.get_text(strip=True)
            match = re.search(r'共(\d+)頁', pager_text)
            if match:
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
            current_soup_for_pager = BeautifulSoup(last_page_html, 'html.parser')
            
            # 找到表格
            table = current_soup_for_pager.find('table', id='ContentPlaceHolder1_sgv')
            
            if table:
                # 找到表格的最後一個 <tbody> 元素
                tbody = table.find('tbody')
                if tbody:
                    # 找到 tbody 內的所有 tr 元素
                    all_trs = tbody.find_all('tr')
                    if all_trs:
                        # 最後一個 tr 應該是分頁器所在的行
                        last_table_row = all_trs[-1]
                        # 在這個 tr 內找到唯一的 td 元素 (它有 colspan)
                        pager_td = last_table_row.find('td')
                        
                        if pager_td:
                            # 在這個 td 內部找到所有 <a> 連結
                            pager_links = pager_td.find_all('a')
                            
                            logger.debug(f"第 {page_num} 頁找到 {len(pager_links)} 個分頁連結。")
                            for link in pager_links:
                                link_text = link.get_text(strip=True)
                                link_href = link.get('href', '')
                                logger.debug(f"連結文本: '{link_text}', href: '{link_href}'")

                                # 檢查連結文本是否為當前頁碼
                                if link_text == str(page_num):
                                    match = re.search(r"__doPostBack\('([^']+)'", link_href)
                                    if match:
                                        next_page_link_target = match.group(1)
                                        logger.debug(f"找到第 {page_num} 頁的 PostBack 目標: {next_page_link_target}")
                                        break
            
            if not next_page_link_target:
                logger.warning(f"未找到第 {page_num} 頁的 PostBack 目標，停止爬取。")
                break

            # 構建分頁的 POST 數據
            post_data = {
                '__EVENTTARGET': next_page_link_target,
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': form_data_for_pagination.get('__VIEWSTATE', ''),
                '__VIEWSTATEGENERATOR': form_data_for_pagination.get('__VIEWSTATEGENERATOR', ''),
                '__EVENTVALIDATION': form_data_for_pagination.get('__EVENTVALIDATION', ''),
                # 再次包含所有表單欄位的值，確保狀態一致性
                'ctl00$ContentPlaceHolder1$txt_PCRName': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$txt_PCRName', ''),
                'ctl00$ContentPlaceHolder1$txt_Jointly': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$txt_Jointly', ''),
                'ctl00$ContentPlaceHolder1$tbx_ccccode': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$tbx_ccccode', ''),
                'ctl00$ContentPlaceHolder1$rdb_status': form_data_for_initial_query.get('ctl00$ContentPlaceHolder1$rdb_status', '全部'),
            }
            # 再次添加所有文件類型 checkbox 的值 (從初始提取的數據中獲取)
            for key, value in form_data_for_initial_query.items():
                if key.startswith('ctl00$ContentPlaceHolder1$chk_type$'):
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
                logger.info(f"第 {page_num} 頁沒有找到記錄，可能已達最後一頁或解析錯誤。")
                break
            all_pcr_records.extend(current_page_records)
            logger.info(f"第 {page_num} 頁抓取到 {len(current_page_records)} 條記錄。")

            # 為了避免過於頻繁的請求，可以加入延遲
            time.sleep(1) # 延遲 1 秒

    return all_pcr_records

async def main_scraper():
    logger.info("開始爬取環境部 PCR 清單...")
    pcr_data = await scrape_all_pcr_data()
    
    if pcr_data:
        logger.info(f"總共抓取到 {len(pcr_data)} 條 PCR 記錄。")
        with open('pcr_list_scraped.json', 'w', encoding='utf-8') as f:
            json.dump(pcr_data, f, ensure_ascii=False, indent=4)
        logger.info("數據已儲存到 pcr_list_scraped.json")
        return pcr_data
    else:
        logger.warning("未能抓取到任何 PCR 數據。")
        return []

if __name__ == "__main__":
    import asyncio
    asyncio.run(main_scraper())
