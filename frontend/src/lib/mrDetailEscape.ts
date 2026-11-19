export function mrDetailEscapeAllowed(mrsVisible: boolean, mrsPinOpen: boolean, key: string, defaultPrevented: boolean): boolean {
  return key === 'Escape' && !defaultPrevented && mrsVisible && !mrsPinOpen
}
