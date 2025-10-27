import React, { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import rehypeRaw from 'rehype-raw'
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
  const [suggestionsMounted, setSuggestionsMounted] = useState(false)
  const [showSuggestionsVisible, setShowSuggestionsVisible] = useState(false)
  // loading state is handled by react-query mutation.status
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // welcome message
    setMessages([
      { id: 's1', role: 'system', content: '歡迎來到 ESG AI 顧問 — 我可以協助您釐清 ESG 相關問題。' }
    ])

    // Always generate a new session id on each page load / refresh.
    const sid = uuidv4()
    // update URL to include the new session id (replace state so no extra history entry)
    try {
      const newUrl = new URL(window.location.href)
      newUrl.searchParams.set('session', sid)
      window.history.replaceState(null, '', newUrl.toString())
    } catch (e) {
      // ignore if URL API not available
    }
    setSessionId(sid)
  }, [])

  // control suggestions mount/visibility to allow enter/exit animations
  useEffect(() => {
    if (messages.length === 1 && messages[0]?.role === 'system') {
      // mount then show
      setSuggestionsMounted(true)
      // small delay to ensure mount occurs before adding visible class
      requestAnimationFrame(() => setShowSuggestionsVisible(true))
    } else {
      // hide then unmount after animation
      setShowSuggestionsVisible(false)
      const t = setTimeout(() => setSuggestionsMounted(false), 220)
      return () => clearTimeout(t)
    }
  }, [messages])


  // UUIDv4 generator (client-side) — used to create a stable session id before first server call
  function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }

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

  // sidebar state for showing PCR details
  const [selectedPCR, setSelectedPCR] = useState<any | null>(null)
  const openPCRSidebar = async (regNo: string) => {
    if (!regNo) return
    try {
      const base = ((import.meta as any).env?.VITE_API_BASE as string) || ''
      // Use the new dedicated endpoint that looks up a single record by pcr_reg_no
      const url = new URL('/pcr_records/by_reg_no', base)
      url.searchParams.append('pcr_reg_no', regNo)
      const resp = await fetch(url.toString())
      if (resp.status === 404) {
        setSelectedPCR({ pcr_reg_no: regNo, document_name: '找不到該文件', developer: '' })
        return
      }
      if (!resp.ok) throw new Error('Failed to fetch PCR record')
      const data = await resp.json()
      // endpoint returns a single object (PCRRecord)
      setSelectedPCR(data)
    } catch (e) {
      setSelectedPCR({ pcr_reg_no: regNo, document_name: '讀取失敗', developer: '' })
    }
  }

  const closePCRSidebar = () => setSelectedPCR(null)

  // --- Helpers: process ReactMarkdown children and replace regno tokens with buttons ---
  const regnoRegex = /(\d{1,3}-\d{3})/

  function splitAndWrapText(text: string, keyBase: string) {
    // split keeps the captured groups if using a capture in the split pattern
    const parts = text.split(/(\b\d{1,3}-\d{3}\b)/)
    return parts.map((part, idx) => {
      const m = part.match(/^\d{1,3}-\d{3}$/)
      if (m) {
        const regNo = m[0]
        return (
          <button key={`${keyBase}-${idx}`} onClick={() => openPCRSidebar(regNo)} className="px-1 rounded bg-esg-100 hover:bg-esg-200 text-esg-800 text-sm">
            {part}
          </button>
        )
      }
      return <span key={`${keyBase}-${idx}`}>{part}</span>
    })
  }

  function processChild(child: any, keyBase: string): any {
    if (typeof child === 'string') return splitAndWrapText(child, keyBase)
    if (React.isValidElement(child)) {
      const props: any = child.props || {}
      const newChildren = React.Children.toArray(props.children).map((ch, i) => processChild(ch, `${keyBase}-${i}`))
      return React.cloneElement(child, { ...props, children: newChildren })
    }
    return child
  }

  function inlineWrapperFactory(tagName: string) {
    return ({ node, children, ...props }: any) => {
      const processed = React.Children.toArray(children).map((c, i) => processChild(c, `${tagName}-${i}`))
      return React.createElement(tagName, props, processed)
    }
  }

  const send = (arg?: any) => {
    const content = (typeof arg === 'string' ? arg : input) || ''
    if (!content.trim()) return
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content }
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
    <div className="mx-auto max-w-6xl p-6">
      <div className="flex gap-6">
        <div className="flex-1">
          <div className="chat-card relative bg-white rounded-2xl shadow-lg p-6 h-[84vh] flex flex-col">
        {/* New session button (sessionId not displayed) */}
        <div className="absolute top-4 right-6">
          <button
            className="px-3 py-1 rounded text-sm bg-white border border-esg-100 text-esg-600 hover:bg-esg-50"
            onClick={() => {
              const newSid = uuidv4()
              try {
                const newUrl = new URL(window.location.href)
                newUrl.searchParams.set('session', newSid)
                window.history.replaceState(null, '', newUrl.toString())
              } catch (e) {}
              setSessionId(newSid)
              setMessages([{ id: 's1', role: 'system', content: '歡迎來到 ESG AI 顧問 — 我可以協助您釐清 ESG 相關問題。' }])
            }}
          >新會話</button>
        </div>
        <div className="flex-1 overflow-auto space-y-4 px-4" style={{scrollBehavior:'smooth'}}>
          {messages.map(m => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[72%] rounded-lg px-4 py-2 ${m.role === 'user' ? 'bg-esg-500 text-white' : m.role === 'assistant' ? 'bg-esg-50 text-esg-800 border border-esg-100' : 'bg-gray-50 text-gray-700 italic'}`}>
                <div className="text-xs text-gray-500 mb-1">{m.role === 'user' ? '您' : m.role === 'assistant' ? 'esgAI' : '系統'}</div>
                {/* message content: preserve whitespace only for plain text (user/system).
                    For assistant (Markdown) we render via ReactMarkdown without pre-wrap so
                    blank lines are handled by the renderer and not preserved as large gaps. */}
                {m.role === 'assistant' ? (
                  <div className="markdown-content">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw, rehypeSanitize]}
                        components={{
                              a: ({node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                              // keep existing code handling for inline code blocks (code spans should not be processed as HTML)
                              code: ({node, inline, className, children, ...props}) => {
                                const text = String(children).trim()
                                const match = text.match(/(\d{1,3}-\d{3})/)
                                if (match) {
                                  const regNo = match[1]
                                  return (
                                    <button onClick={() => openPCRSidebar(regNo)} className="px-1 rounded bg-esg-100 hover:bg-esg-200 text-esg-800 text-sm">
                                      {text}
                                    </button>
                                  )
                                }
                                return (
                                  <code className={className ? className + ' px-1 rounded bg-gray-100' : 'px-1 rounded bg-gray-100'} {...props}>{children}</code>
                                )
                              },
                              // generic inline wrapper factory to avoid repeating logic for many tags
                              // we'll map several common inline tags to this wrapper so any text inside them
                              // will be scanned for registration numbers and replaced with buttons.
                              strong: inlineWrapperFactory('strong'),
                              b: inlineWrapperFactory('b'),
                              em: inlineWrapperFactory('em'),
                              i: inlineWrapperFactory('i'),
                              span: inlineWrapperFactory('span'),
                              u: inlineWrapperFactory('u'),
                              del: inlineWrapperFactory('del'),
                              p: inlineWrapperFactory('p'),
                              li: inlineWrapperFactory('li'),
                              h1: inlineWrapperFactory('h1'),
                              h2: inlineWrapperFactory('h2'),
                              h3: inlineWrapperFactory('h3'),
                              h4: inlineWrapperFactory('h4'),
                              h5: inlineWrapperFactory('h5'),
                              h6: inlineWrapperFactory('h6'),
                            }}
                      >
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  )}
              </div>
            </div>
          ))}
          {mutation.status === 'pending' && (
            <div className="flex justify-start">
              <div className="max-w-[140px] rounded-lg px-3 py-2 bg-esg-50 text-esg-800 border border-esg-100">
                <TypingIndicator />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

  {/* suggestion chips: animated enter/exit. mounted && visible toggles allow exit animation */}
        {suggestionsMounted && (
          <div className={`px-4 mt-3 mb-1 suggestions ${showSuggestionsVisible ? 'enter' : 'exit'}`}>
            <div className="flex gap-2 flex-wrap">
              {[
                '有茶葉蛋的 PCR 嗎？',
                '如何查詢某產品的 PCR 證書？',
                '我的公司如何開始編寫產品碳足跡報告？',
              ].map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-sm px-3 py-1 rounded-full bg-esg-50 border border-esg-100 text-esg-800 hover:bg-esg-100 suggestion-chip"
                >{s}</button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-gray-100 flex gap-3 items-center">
          <input
            className="flex-1 px-4 py-4 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-esg-200"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            onFocus={onFocus}
            placeholder="在此輸入您的問題，按 Enter 發送"
          />
          <button onClick={send} disabled={mutation.status === 'pending'} className="px-5 py-3 rounded-xl bg-esg-500 text-white disabled:opacity-60">{mutation.status === 'pending' ? '傳送中...' : '傳送'}</button>
        </div>
          </div>
        </div>

        {/* PCR detail sidebar */}
        {selectedPCR && (
          <aside className="w-80 bg-white border-l border-gray-100 p-4">
          <div className="flex justify-between items-start mb-3">
            <h3 className="text-lg font-semibold">PCR 詳細</h3>
            <button onClick={closePCRSidebar} className="text-sm text-gray-500">關閉</button>
          </div>
          <div className="space-y-2">
            <p className="text-sm text-gray-700"><span className="font-medium">文件名稱:</span> {selectedPCR.document_name || '-'}</p>
            <p className="text-sm text-gray-700"><span className="font-medium">PCR 登錄編號:</span> {selectedPCR.pcr_reg_no || '-'}</p>
            <p className="text-sm text-gray-700"><span className="font-medium">制定者:</span> {selectedPCR.developer || '-'}</p>
            <div className="mt-3 p-3 bg-gray-50 rounded-md border border-gray-200">
              <p className="text-sm font-medium text-gray-800 mb-1">適用產品範圍:</p>
              <p className="text-xs text-gray-600 whitespace-pre-wrap">{selectedPCR.product_scope || '-'}</p>
            </div>
            {selectedPCR.download_link && (
              <a href={`https://cfp-calculate.tw/cfpc/Carbon/WebPage/${selectedPCR.download_link}`} target="_blank" rel="noreferrer" className="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-esg-600 hover:bg-esg-700">下載文件</a>
            )}
          </div>
        </aside>
      )}
      </div>
    </div>
  )
}
