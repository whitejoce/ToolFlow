import axios from 'axios'

export const apiBaseURL = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export const http = axios.create({
  baseURL: apiBaseURL,
  timeout: 15000,
})
