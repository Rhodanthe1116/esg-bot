import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { useMutation } from '@tanstack/react-query'
import TypingIndicator from './TypingIndicator'

type Message = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  // loading state is handled by react-query mutation.status
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // welcome message
    setMessages([
      { id: 's1', role: 'system', content: '歡迎來到 ESG AI 顧問 — 我可以協助您釐清 ESG 相關問題。' }
    ])

    // load session id from localStorage if present
    const sid = window.localStorage.getItem('esg_chat_session_id')
    if (sid) setSessionId(sid)
  }, [])

  useEffect(() => {
    // scroll the last element into view aligned to the end so it's not hidden by the fixed input
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  const apiBase = ((import.meta as any).env?.VITE_API_BASE as string) || ''

  const mutation = useMutation<any, Error, Message>({
    mutationFn: async (userMsg: Message) => {
      const url = `${apiBase}/api/chat`
      const payload: any = { messages: [...messages, userMsg] }
      if (sessionId) payload.session_id = sessionId
      const resp = await axios.post(url, payload)
      return resp.data
    }
  })

  const send = () => {
    if (!input.trim()) return
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    mutation.mutate(userMsg, {
      onSuccess: (data: any) => {
        const reply = data?.reply
        const returnedSid = data?.session_id
        if (returnedSid) {
          setSessionId(returnedSid)
          try { window.localStorage.setItem('esg_chat_session_id', returnedSid) } catch (e) {}
        }
        const assistantMsg: Message = { id: Date.now().toString() + '-a', role: 'assistant', content: reply || '抱歉，沒有回覆。' }
        setMessages(prev => [...prev, assistantMsg])
      },
      onError: (err: Error) => {
        const assistantMsg: Message = { id: Date.now().toString() + '-a', role: 'assistant', content: '無法連線至伺服器' }
        setMessages(prev => [...prev, assistantMsg])
        console.error('mutation error', err)
      }
    })
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') send()
  }

  const onFocus = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map(m => (
          <div key={m.id} className={`message ${m.role}`}>
            <div className="role">{m.role === 'user' ? '您' : m.role === 'assistant' ? 'esgAI' : '系統'}</div>
            <div className="content">{m.content}</div>
          </div>
        ))}
        {mutation.status === 'pending' && (
          <div key="__loading" className={`message assistant loading`}>
            <div className="role">esgAI</div>
            <div className="content"><TypingIndicator /></div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="input-row">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={onFocus}
          placeholder="在此輸入您的問題，按 Enter 發送"
        />
  <button onClick={send} disabled={mutation.status === 'pending'}>{mutation.status === 'pending' ? '傳送中...' : '傳送'}</button>
      </div>
      
    </div>
  )
}
