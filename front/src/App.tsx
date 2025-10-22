import React from 'react'
import Chat from './components/Chat'

export default function App(){
  return (
    <div className="app">
      <header className="header">
        <h1>ESG AI 顧問</h1>
      </header>
      <main className="main">
        <Chat />
      </main>
    </div>
  )
}
