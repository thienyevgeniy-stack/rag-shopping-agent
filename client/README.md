# Android Client

Native Android scaffold built with Kotlin and Jetpack Compose.

## Notes

- Physical-device backend URL defaults to `http://127.0.0.1:8000` and uses `adb reverse tcp:8000 tcp:8000`.
- If testing on an emulator, change `baseUrl` in `ChatSseClient` to `http://10.0.2.2:8000`.
- The client listens to SSE events: `token`, `product_card`, and `done`.
