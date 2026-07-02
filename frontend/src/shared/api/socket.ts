import { io } from 'socket.io-client'
import type { Socket } from 'socket.io-client'

let _socket: Socket | null = null

function getStoredToken(): string {
  try {
    const raw = localStorage.getItem('vms-auth')
    if (!raw) return ''
    return (JSON.parse(raw) as { token?: string }).token ?? ''
  } catch {
    return ''
  }
}

export function getSocket(): Socket {
  if (!_socket) {
    const token = getStoredToken()
    _socket = io('', {
      path: '/socket.io',
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5_000,
      auth: { token },
    })
  }
  return _socket
}

export function resetSocket(): void {
  if (_socket) {
    _socket.disconnect()
    _socket = null
  }
}
