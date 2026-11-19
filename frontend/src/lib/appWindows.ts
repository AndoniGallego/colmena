export const CLAVE_APP = 'orq.app'

export function enAppWindows(search: string, storage: Pick<Storage, 'getItem' | 'setItem'> | null): boolean {
  try {
    if (new URLSearchParams(search).get('app') === 'windows') {
      try {
        storage?.setItem(CLAVE_APP, 'windows')
      } catch {
        /* sessionStorage bloqueado */
      }
      return true
    }
    return storage?.getItem(CLAVE_APP) === 'windows'
  } catch {
    return false
  }
}
