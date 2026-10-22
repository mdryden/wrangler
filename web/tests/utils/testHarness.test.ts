import { describe, it, expect } from "vitest"
import { defineComponent, h } from "vue"
import { mountWithQuasar, findInBody, findAllInBody } from "./testHarness"
import { useQuasar } from "quasar"

const SimpleComponent = defineComponent({
  name: "SimpleComponent",
  setup() {
    const $q = useQuasar()
    return () =>
      h("div", { class: "test-container" }, [
        h("span", { class: "message" }, "Hello Quasar"),
        h("button", {
          class: "notify-btn",
          onClick: () => $q.notify({ message: "Test notification" }),
        }),
      ])
  },
})

describe("testHarness", () => {
  it("mounts a component with Quasar plugins and attaches to body by default", () => {
    const wrapper = mountWithQuasar(SimpleComponent)

    expect(wrapper.find(".message").text()).toBe("Hello Quasar")
    expect(findInBody(".test-container")).not.toBeNull()
    expect(findInBody(".test-container")?.textContent).toContain("Hello Quasar")
  })

  it("findInBody returns null for non-existent elements", () => {
    mountWithQuasar(SimpleComponent)
    expect(findInBody(".does-not-exist")).toBeNull()
  })

  it("findAllInBody returns all matching elements in body", () => {
    mountWithQuasar(SimpleComponent)
    const elements = findAllInBody(".message")
    expect(elements.length).toBe(1)
    expect(elements[0].textContent).toBe("Hello Quasar")
  })

  it("supports attachToBody: false", () => {
    const wrapper = mountWithQuasar(SimpleComponent, { attachToBody: false })
    expect(wrapper.find(".message").text()).toBe("Hello Quasar")
    // When attachToBody is false, the wrapper container is not attached to document.body
    expect(findInBody(".test-container")).toBeNull()
  })
})
