/// <reference types="vite/client" />

import axios from 'axios'
import type { FailRateTrendPoint, InspectionLog, InspectionStats } from '@/types/inspection'

const API_BASE_URL = import.meta.env.DEV
  ? '/api'
  : (import.meta.env.VITE_INSPECTION_API_BASE_URL ?? '/api')

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const message = error.response?.data?.message ?? error.message

    if (status === 404) {
      console.warn(`[API] 리소스 없음: ${message}`)
    } else if (status >= 500) {
      console.error(`[API] 서버 오류 ${status}: ${message}`)
    } else {
      console.error(`[API] 요청 오류: ${message}`)
    }

    return Promise.reject(error)
  }
)

export interface EdgeDevice {
  deviceId: string
  connected: boolean
  connectedAt: string
  lastSeenAt: string
  lastStatus?: Record<string, unknown>
  lastMessage?: Record<string, unknown>
}

export interface EdgeCommandMessage {
  type: string
  requestId: string
  deviceId: string
  timestamp: string
  payload?: Record<string, unknown>
}

export const fetchAllInspections = async (): Promise<InspectionLog[]> => {
  const { data } = await apiClient.get<InspectionLog[]>('/inspections')
  return data
}

export const fetchInspectionById = async (id: number): Promise<InspectionLog> => {
  const { data } = await apiClient.get<InspectionLog>(`/inspections/${id}`)
  return data
}

export const fetchRecentInspections = async (limit = 10): Promise<InspectionLog[]> => {
  const { data } = await apiClient.get<InspectionLog[]>('/inspections/recent', {
    params: { limit },
  })
  return data
}

export const fetchStats = async (): Promise<InspectionStats> => {
  const { data } = await apiClient.get<InspectionStats>('/inspections/stats')
  return data
}

export const fetchFailRateTrend = async (
  groupBy: 'week' | 'month',
  periods: number
): Promise<FailRateTrendPoint[]> => {
  const { data } = await apiClient.get<FailRateTrendPoint[]>(
    '/inspections/stats/fail-rate-trend',
    {
      params: { groupBy, periods },
    }
  )
  return data
}

export const fetchInspectionsByPeriod = async (
  from: string,
  to: string
): Promise<InspectionLog[]> => {
  const { data } = await apiClient.get<InspectionLog[]>('/inspections/period', {
    params: { from, to },
  })
  return data
}

export const deleteAllInspections = async (): Promise<void> => {
  await apiClient.delete('/inspections')
}

export const fetchEdgeDevices = async (): Promise<EdgeDevice[]> => {
  const { data } = await apiClient.get<EdgeDevice[]>('/edge/devices')
  return data
}

export const triggerEdgeInspection = async (deviceId: string): Promise<EdgeCommandMessage> => {
  const { data } = await apiClient.post<EdgeCommandMessage>(
    `/edge/${encodeURIComponent(deviceId)}/inspect/trigger`
  )
  return data
}

