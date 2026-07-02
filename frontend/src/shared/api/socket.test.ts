import { vi, describe, it, expect, beforeEach } from 'vitest'

const mockSocket = {
  disconnect: vi.fn(),
  on: vi.fn(),
  emit: vi.fn(),
  connected: false,
}

vi.mock('socket.io-client', () => ({
  io: vi.fn(() => mockSocket),
}))

import { io } from 'socket.io-client'
import { getSocket, resetSocket } from './socket'

describe('socket client', () => {
  beforeEach(() => {
    resetSocket()
    vi.mocked(io).mockClear()
    mockSocket.disconnect.mockClear()
    localStorage.clear()
  })

  it('creates socket with correct reconnect settings', () => {
    getSocket()
    expect(io).toHaveBeenCalledWith(
      '',
      expect.objectContaining({
        reconnection: true,
        reconnectionDelay: 500,
        reconnectionDelayMax: 5_000,
      }),
    )
  })

  it('attaches JWT token from localStorage in auth', () => {
    localStorage.setItem('vms_token', 'test-jwt-abc')
    getSocket()
    expect(io).toHaveBeenCalledWith(
      '',
      expect.objectContaining({ auth: { token: 'test-jwt-abc' } }),
    )
  })

  it('uses empty string when no token in localStorage', () => {
    getSocket()
    expect(io).toHaveBeenCalledWith(
      '',
      expect.objectContaining({ auth: { token: '' } }),
    )
  })

  it('returns the same instance on subsequent calls', () => {
    const s1 = getSocket()
    const s2 = getSocket()
    expect(s1).toBe(s2)
    expect(io).toHaveBeenCalledTimes(1)
  })

  it('creates a new instance after resetSocket', () => {
    getSocket()
    resetSocket()
    expect(mockSocket.disconnect).toHaveBeenCalledTimes(1)
    getSocket()
    expect(io).toHaveBeenCalledTimes(2)
  })

  it('resetSocket is a no-op when no socket exists', () => {
    expect(() => resetSocket()).not.toThrow()
  })
})
