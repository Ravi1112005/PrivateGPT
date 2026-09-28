/**
 * preload.js — Secure bridge between Electron main process and renderer
 *
 * Exposes a minimal API to the renderer via contextBridge.
 * No Node.js access in the renderer — all system calls go through here.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),
  
  // Window controls
  minimize: () => ipcRenderer.invoke("window-minimize"),
  maximize: () => ipcRenderer.invoke("window-maximize"),
  close: () => ipcRenderer.invoke("window-close"),
  isMaximized: () => ipcRenderer.invoke("window-is-maximized"),
  
  // File dialog
  selectFiles: () => ipcRenderer.invoke("select-files"),
  
  // Backend status events
  onBackendReady: (callback) => ipcRenderer.on("backend-ready", callback),
  onBackendError: (callback) => ipcRenderer.on("backend-error", callback),
});
