import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api/client'

export interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Fetches data from the API on mount and whenever `path` changes.
 * Call `refetch()` to manually re-run the request.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useApi<Stats>('/discovery/stats')
 */
export function useApi<T>(path: string | null): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(path !== null)
  const [error, setError] = useState<string | null>(null)
  // Track the latest path so stale responses from old paths are dropped
  const latestPath = useRef<string | null>(path)

  const run = useCallback(async (p: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<T>(p)
      if (latestPath.current === p) {
        setData(result)
      }
    } catch (e) {
      if (latestPath.current === p) {
        setError(e instanceof Error ? e.message : 'Request failed')
      }
    } finally {
      if (latestPath.current === p) {
        setLoading(false)
      }
    }
  }, [])

  const refetch = useCallback(() => {
    if (latestPath.current) run(latestPath.current)
  }, [run])

  useEffect(() => {
    latestPath.current = path
    if (path) {
      run(path)
    } else {
      setData(null)
      setLoading(false)
    }
  }, [path, run])

  return { data, loading, error, refetch }
}
