import { defineConfig } from '@playwright/test'
import path from 'node:path'

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'chrome',
    viewport: { width: 1512, height: 1100 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: { args: [
      '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
      `--use-file-for-fake-video-capture=${path.resolve('../data/demo/camera.y4m')}`,
    ] },
  },
  webServer: [
    { command: '../.venv/bin/python ../main.py', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: true },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
  ],
})
