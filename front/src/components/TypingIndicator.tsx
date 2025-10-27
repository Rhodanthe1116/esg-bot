import React from 'react'

export default function TypingIndicator(){
  return (
    <div className="flex items-center" aria-live="polite" aria-atomic="true">
      <svg className="esg-spinner" width="20" height="20" viewBox="0 0 50 50" role="img" aria-label="載入中">
        <circle className="path" cx="25" cy="25" r="20" fill="none" />
      </svg>
    </div>
  )
}
