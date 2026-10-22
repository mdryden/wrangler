import { mount, type ComponentMountingOptions, type VueWrapper } from "@vue/test-utils"
import { Quasar, Notify, Dialog, ClosePopup } from "quasar"
import { createPinia, setActivePinia, type Pinia } from "pinia"
import type { ComponentPublicInstance } from "vue"

export interface MountWithQuasarOptions<T> extends ComponentMountingOptions<T> {
  pinia?: Pinia
  attachToBody?: boolean
}

/**
 * Mounts a Vue component with Quasar plugins and Pinia configured.
 */
export function mountWithQuasar<T>(component: T, options: MountWithQuasarOptions<T> = {}): VueWrapper<ComponentPublicInstance & T> {
  const { pinia, attachToBody = true, global = {}, ...mountOptions } = options

  // Set active Pinia (default to a fresh root if not provided)
  const activePinia = pinia || createPinia()
  setActivePinia(activePinia)

  const plugins = [
    activePinia,
    [Quasar, { plugins: { Notify, Dialog }, directives: { ClosePopup } }] as [any, any],
    ...(global.plugins || []),
  ]

  const container = attachToBody ? document.body : undefined

  return mount(component as any, {
    attachTo: container,
    global: {
      ...global,
      plugins,
    },
    ...mountOptions,
  }) as VueWrapper<ComponentPublicInstance & T>
}

/**
 * Helper to query elements teleported to document.body (e.g., active QDialog contents).
 */
export function findInBody<T extends Element = HTMLElement>(selector: string): T | null {
  return document.body.querySelector<T>(selector)
}

/**
 * Helper to query all elements teleported to document.body.
 */
export function findAllInBody<T extends Element = HTMLElement>(selector: string): T[] {
  return Array.from(document.body.querySelectorAll<T>(selector))
}
