from chroma_services import setup_db
from langchain_community.vectorstores import Chroma


def search_test(db: Chroma):
    QUERY_A = "茶葉蛋"  # 測試同義詞
    QUERY_B = "植物油的碳足跡文件"  # 測試上下文
    # --- 步驟 3: 執行語義搜索 A ---
    print(f"\n======== 搜索 A: {QUERY_A} ========")
    # 執行相似性搜索 (K=4 意指回傳最相似的前 4 個結果)
    results_a = db.similarity_search(QUERY_A, k=4)

    for i, doc in enumerate(results_a):
        # 從 metadata 中獲取 document_name
        print(f"【結果 {i+1}】 文件名: {doc.metadata.get('document_name', 'N/A')}")
        print(f"  產品範圍: {doc.page_content}...")
        print(f"  開發者: {doc.metadata.get('developer', 'N/A')}")
        print("-" * 20)

    # --- 步驟 4: 執行語義搜索 B ---
    print(f"\n======== 搜索 B: {QUERY_B} ========")
    results_b = db.similarity_search(QUERY_B, k=2)

    for i, doc in enumerate(results_b):
        print(f"【結果 {i+1}】 文件名: {doc.metadata.get('document_name', 'N/A')}")
        print(f"  產品範圍: {doc.page_content[:100]}...")
        print(f"  PCR編號: {doc.metadata.get('pcr_reg_no', 'N/A')}")
        print("-" * 20)


if __name__ == "__main__":
    db = setup_db()
    search_test(db)
