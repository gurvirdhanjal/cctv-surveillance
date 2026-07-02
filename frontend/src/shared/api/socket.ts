import { io } from 'socket.io-client'
import type { Socket } from 'socket.io-client'

let _socket: Socket | null = null

export function getSocket(): Socket {
  if (!_socket) {
    const token = localStorage.getItem('vms_token') ?? ''
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
