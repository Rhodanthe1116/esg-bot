import React, { useState } from 'react'
import Chat from './components/Chat'
import PCRPage from './pages/PCRPage'

export default function App(){
  const [view, setView] = useState<'chat'|'pcr'>('chat')
  return (
    <div className="app">
      <header className="header flex items-center">
        <h1 className="text-lg">ESG AI 顧問</h1>
        <div className="ml-auto flex gap-2">
          <button onClick={()=>setView('chat')} className={`px-3 py-1.5 rounded-md ${view==='chat' ? 'bg-esg-100 text-esg-800' : 'text-gray-600'}`}>聊天</button>
          <button onClick={()=>setView('pcr')} className={`px-3 py-1.5 rounded-md ${view==='pcr' ? 'bg-esg-100 text-esg-800' : 'text-gray-600'}`}>PCR 查詢</button>
        </div>
      </header>
      <main className="main">
        {view === 'chat' ? <Chat /> : <PCRPage />}
      </main>
    </div>
  )
}
