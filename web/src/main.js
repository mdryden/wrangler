import { createApp } from "vue"
import { createPinia } from "pinia"
import { Quasar, Notify, Dialog } from "quasar"

// Import icon libraries
import "@quasar/extras/material-icons/material-icons.css"
import "@quasar/extras/roboto-font/roboto-font.css"

// Import Quasar pre-compiled CSS (no Sass required)
import "quasar/dist/quasar.css"

import App from "./App.vue"

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(Quasar, {
  plugins: {
    Notify,
    Dialog,
  },
})

app.mount("#app")
