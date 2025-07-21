from pydantic import BaseModel, Field
from typing import Optional


# 定義 PCRRecord 模型，用於數據驗證和序列化
class PCRRecord(BaseModel):
    pcr_reg_no: str = Field(..., description="PCR 登錄編號，主鍵")
    pcr_source_type: Optional[str] = Field(None, description="PCR 來源/種類")
    document_name: Optional[str] = Field(None, description="文件名稱")
    developer: Optional[str] = Field(None, description="制定者/共同訂定者")
    version: Optional[str] = Field(None, description="版本")
    approval_date: Optional[str] = Field(None, description="核准日期")
    effective_date: Optional[str] = Field(None, description="有效期限")
    product_scope: Optional[str] = Field(None, description="適用產品範圍")
    download_link: Optional[str] = Field(None, description="下載連結")
    feedback_link: Optional[str] = Field(None, description="意見回饋連結的 ID")
    ccc_codes: Optional[str] = Field(None, description="CCC Codes (以分號分隔)")
