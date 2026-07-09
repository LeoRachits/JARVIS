/**
 * Processo principal do Jarvis HUD.
 * Cria uma janela transparente, sem borda, sempre-no-topo e click-through
 * posicionada no canto inferior direito da tela principal.
 */
const { app, BrowserWindow, screen } = require('electron');
const path = require('path');

let win;

function createWindow() {
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    const WIN_W  = 460;
    const WIN_H  = 400;
    const MARGIN = 20;

    win = new BrowserWindow({
        width:           WIN_W,
        height:          WIN_H,
        x:               width  - WIN_W - MARGIN,
        y:               height - WIN_H - MARGIN,
        transparent:     true,
        backgroundColor: '#00000000',
        frame:           false,
        alwaysOnTop:     true,
        skipTaskbar:     true,
        resizable:       false,
        hasShadow:       false,
        focusable:       false,
        webPreferences: {
            nodeIntegration:  true,
            contextIsolation: false,
        },
    });

    // Click-through: cliques passam para a janela por baixo; o HUD não rouba foco.
    win.setIgnoreMouseEvents(true, { forward: true });

    // Garante que fica acima de outros always-on-top (ex.: barra de tarefas flutuante).
    win.setAlwaysOnTop(true, 'screen-saver');

    // Passa a porta do WS como query string para o renderer.
    const port = process.env.HUD_PORT || '8765';
    win.loadFile(path.join(__dirname, 'index.html'), { query: { port } });
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
