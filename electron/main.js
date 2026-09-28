/**
 * main.js — Electron main process
 *
 * Launches the Python FastAPI backend as a child process,
 * then opens the BrowserWindow pointing to the frontend HTML.
 */

const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let mainWindow;
let backendProcess;

const BACKEND_PORT = 8765;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;

// ── Backend management ─────────────────────────────────────────────────

async function isBackendAlreadyRunning() {
  try {
    const http = require("http");
    return await new Promise((resolve) => {
      const req = http.get(`${BACKEND_URL}/api/info`, (res) => {
        resolve(res.statusCode === 200);
      });
      req.on("error", () => resolve(false));
      req.setTimeout(1000, () => { req.destroy(); resolve(false); });
    });
  } catch { return false; }
}

async function startBackend() {
  // Skip if backend is already running (e.g. in dev mode)
  if (await isBackendAlreadyRunning()) {
    console.log("[Backend] Already running on port " + BACKEND_PORT);
    return;
  }

  const projectRoot = path.resolve(__dirname, "..");

  // Try venv python first, fall back to system python
  const venvPython = path.join(projectRoot, "venv", "Scripts", "python.exe");
  const pythonCmd = require("fs").existsSync(venvPython)
    ? venvPython
    : "python";

  backendProcess = spawn(
    pythonCmd,
    ["-m", "uvicorn", "backend.server:app", "--port", String(BACKEND_PORT), "--host", "127.0.0.1"],
    {
      cwd: projectRoot,
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    }
  );

  backendProcess.stdout.on("data", (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on("data", (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.on("error", (err) => {
    console.error("[Backend] Failed to start:", err.message);
  });

  backendProcess.on("close", (code) => {
    console.log(`[Backend] Process exited with code ${code}`);
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill("SIGTERM");
    backendProcess = null;
  }
}

// Wait for backend to be ready
async function waitForBackend(maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const http = require("http");
      await new Promise((resolve, reject) => {
        const req = http.get(`${BACKEND_URL}/api/info`, (res) => {
          if (res.statusCode === 200) resolve();
          else reject();
        });
        req.on("error", reject);
        req.setTimeout(1000, () => {
          req.destroy();
          reject();
        });
      });
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  return false;
}

// ── Window creation ────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#0a0e1a",
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── IPC handlers ───────────────────────────────────────────────────────

ipcMain.handle("get-backend-url", () => BACKEND_URL);

ipcMain.handle("window-minimize", () => mainWindow?.minimize());
ipcMain.handle("window-maximize", () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.handle("window-close", () => mainWindow?.close());
ipcMain.handle("window-is-maximized", () => mainWindow?.isMaximized());

ipcMain.handle("select-files", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile", "multiSelections"],
    filters: [{ name: "PDF Files", extensions: ["pdf"] }],
  });
  return result.filePaths;
});

// ── App lifecycle ──────────────────────────────────────────────────────

app.whenReady().then(async () => {
  await startBackend();
  
  createWindow();

  // Show loading state while backend starts
  const ready = await waitForBackend();
  if (ready) {
    mainWindow?.webContents.send("backend-ready");
  } else {
    mainWindow?.webContents.send("backend-error");
  }
});

app.on("window-all-closed", () => {
  stopBackend();
  app.quit();
});

app.on("before-quit", () => {
  stopBackend();
});
