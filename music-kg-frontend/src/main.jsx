import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App'
import { AppProvider } from './context/AppContext'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: '#1a1a1a',
              color: '#fff',
              border: '1px solid #282828',
              fontFamily: 'Syne, sans-serif',
            },
            success: { iconTheme: { primary: '#1db954', secondary: '#fff' } },
            error:   { iconTheme: { primary: '#e84393', secondary: '#fff' } },
          }}
        />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>
)
