/** Se avisa al servidor si el chat está abierto, a la vista y hay unread o la sesión quedó en done. */
export function shouldMarkSeen(opts: {
  unread: boolean | undefined
  status?: string
  sessionOpen: boolean
  visible: boolean
}): boolean {
  const { unread, status, sessionOpen, visible } = opts
  return sessionOpen && visible && (!!unread || status === 'done')
}
