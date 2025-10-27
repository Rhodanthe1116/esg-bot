import React, { useEffect, useState } from 'react'

const DOWNLOAD_BASE_URL = 'https://cfp-calculate.tw/cfpc/Carbon/WebPage/'

export default function PCRPage(){
  const [records, setRecords] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState<number>(50)
  const [page, setPage] = useState<number>(1)

  const skip = (page - 1) * limit

  const fetchPcrRecords = async () => {
    setLoading(true)
    setError(null)
    setRecords([])
    try{
      // Prefer explicit API base from env (VITE_API_BASE). When running the dev server
      // the frontend origin is different from the backend, so window.location.origin
      // would point to the frontend and return HTML. Use VITE_API_BASE to target backend.
      const base = ((import.meta as any).env?.VITE_API_BASE as string) || (window as any).API_BASE_URL || window.location.origin
      const url = new URL('/pcr_records/', base)
      url.searchParams.append('skip', String(skip))
      url.searchParams.append('limit', String(limit))
      if (search) url.searchParams.append('search', search)

      const resp = await fetch(url.toString())
      if (!resp.ok) {
        // try parse JSON error body; if response is HTML (frontend index) return a clearer message
        let errBody: any = null
        try {
          errBody = await resp.json()
        } catch (e) {
          const text = await resp.text().catch(()=>null)
          throw new Error(text ? `Non-JSON response from ${url.toString()}: ${text.slice(0,200)}` : `HTTP ${resp.status}`)
        }
        throw new Error(errBody.detail || `HTTP ${resp.status}`)
      }
      const data = await resp.json()
      setRecords(data)
      if (data.length === 0 && page > 1){
        setPage(p => p-1)
      }
    }catch(e:any){
      setError(e.message || '載入失敗')
    }finally{setLoading(false)}
  }

  useEffect(()=>{ fetchPcrRecords() }, [page])

  return (
    <div className="container mx-auto bg-white p-6 rounded-xl shadow-lg w-full max-w-6xl">
      <h1 className="text-3xl font-bold text-gray-800 mb-6 text-center">環境部PCR記錄查詢</h1>

      <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:space-x-4 space-y-4 sm:space-y-0">
        <div className="flex-grow">
          <label className="block text-sm font-medium text-gray-700 mb-1">搜尋關鍵字 (文件名稱/制定者/產品範圍)</label>
          <input className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm" value={search} onChange={e=>setSearch(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">每頁顯示數量</label>
          <input type="number" className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm" value={limit} onChange={e=>setLimit(Number(e.target.value)||50)} />
        </div>
  <button className="px-4 py-2 bg-esg-600 text-white font-semibold rounded-md" onClick={()=>{setPage(1); fetchPcrRecords()}}>查詢</button>
      </div>

  {loading && <div className="text-center text-esg-600 font-medium mb-4">載入中...</div>}
      {error && <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-md relative mb-4">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {records.length===0 && !loading ? <p className="text-center text-gray-600 col-span-full">沒有找到任何記錄。</p> : records.map((record:any, idx:number)=>{
          const getDisplay = (v:any)=> v===null||v===undefined||v===''?'-':v
          const fullDownload = record.download_link ? `${DOWNLOAD_BASE_URL}${record.download_link}` : ''
          return (
            <div key={idx} className="bg-white p-4 rounded-xl shadow-md flex flex-col justify-between hover:shadow-lg">
              <div>
                <h3 className="text-lg font-semibold text-esg-700 mb-2"><span className="text-gray-600">文件名稱:</span> {getDisplay(record.document_name)}</h3>
                <p className="text-sm text-gray-700 mb-1"><span className="font-medium">PCR 登錄編號:</span> {getDisplay(record.pcr_reg_no)}</p>
                <p className="text-sm text-gray-700 mb-1"><span className="font-medium">制定者:</span> {getDisplay(record.developer)}</p>
                <p className="text-sm text-gray-700 mb-1"><span className="font-medium">版本:</span> {getDisplay(record.version)}</p>
                <p className="text-sm text-gray-700 mb-1"><span className="font-medium">核准日期:</span> {getDisplay(record.approval_date)}</p>
                <p className="text-sm text-gray-700 mb-1"><span className="font-medium">有效期限:</span> {getDisplay(record.effective_date)}</p>
                <div className="mt-3 mb-2 p-3 bg-gray-50 rounded-md border border-gray-200">
                  <p className="text-sm font-medium text-gray-800 mb-1">適用產品範圍:</p>
                  <p className="text-xs text-gray-600 whitespace-pre-wrap">{getDisplay(record.product_scope)}</p>
                </div>
                <div className="mt-2 mb-2 p-3 bg-gray-50 rounded-md border border-gray-200">
                  <p className="text-sm font-medium text-gray-800 mb-1">CCC Codes:</p>
                  <p className="text-xs text-gray-600 whitespace-pre-wrap">{getDisplay(record.ccc_codes)}</p>
                </div>
              </div>
              <div className="mt-4 text-right">
                {fullDownload && <a href={fullDownload} target="_blank" rel="noreferrer" className="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-esg-600 hover:bg-esg-700">下載文件</a>}
              </div>
            </div>
          )
        })}
      </div>

      <div className="flex justify-between items-center mt-4">
  <button className="px-4 py-2 bg-gray-300 text-gray-800 font-semibold rounded-md" onClick={()=>{ if(page>1) setPage(p=>p-1)}} disabled={page===1}>上一頁</button>
        <span className="text-gray-700 font-medium">頁數: {page}</span>
  <button className="px-4 py-2 bg-esg-600 text-white font-semibold rounded-md" onClick={()=>setPage(p=>p+1)}>下一頁</button>
      </div>
    </div>
  )
}
