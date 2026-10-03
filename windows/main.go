// Continuum VPN is a Windows tray widget. It imports a profile bundle and asks
// WireGuard for Windows to bring that tunnel up. It does not use WSL.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"unsafe"

	"github.com/getlantern/systray"
	"golang.org/x/sys/windows"
)

const (
	wmDestroy = 0x0002
	wmClose   = 0x0010
	wmCommand = 0x0111
	wmApp     = 0x8000
	wsChild   = 0x40000000
	wsVisible = 0x10000000
	wsVScroll = 0x00200000
	wsTabStop = 0x00010000
	esMulti   = 0x0004
	lbsNotify = 0x0001
	lbReset   = 0x0184
	lbAdd     = 0x0180
	lbGetSel  = 0x0188
)

var (
	user32   = windows.NewLazySystemDLL("user32.dll")
	kernel32 = windows.NewLazySystemDLL("kernel32.dll")

	pRegisterClassExW = user32.NewProc("RegisterClassExW")
	pCreateWindowExW  = user32.NewProc("CreateWindowExW")
	pDefWindowProcW   = user32.NewProc("DefWindowProcW")
	pShowWindow       = user32.NewProc("ShowWindow")
	pSetWindowTextW   = user32.NewProc("SetWindowTextW")
	pSendMessageW     = user32.NewProc("SendMessageW")
	pPostMessageW     = user32.NewProc("PostMessageW")
	pGetModuleHandleW = kernel32.NewProc("GetModuleHandleW")
	pMessageBoxW      = user32.NewProc("MessageBoxW")
)

type profile struct {
	Iface        string `json:"iface"`
	Label        string `json:"label"`
	CountryCode  string `json:"countryCode"`
	CountryFlag  string `json:"countryFlag"`
	Obfuscation  string `json:"obfuscation"`
	AdBlock      string `json:"adBlock"`
	RateLimit    string `json:"rateLimit"`
	Endpoint     string `json:"endpoint"`
	Active       bool   `json:"active"`
}

type wndClass struct {
	Size       uint32
	Style      uint32
	WndProc    uintptr
	ClsExtra   int32
	WndExtra   int32
	Instance   windows.Handle
	Icon       windows.Handle
	Cursor     windows.Handle
	Background windows.Handle
	MenuName   *uint16
	ClassName  *uint16
	IconSm     windows.Handle
}

var (
	hwnd      windows.Handle
	listBox   windows.Handle
	statusBtn windows.Handle
	pasteBox  windows.Handle
	rowsMu    sync.Mutex
	rows      []profile
	selected  string
	busy      bool
	wndproc   = windows.NewCallback(windowProc)
)

func main() {
	systray.Run(onReady, func() {})
}

func onReady() {
	systray.SetIcon(trayIcon())
	systray.SetTitle("VPN")
	systray.SetTooltip("Continuum VPN")
	openItem := systray.AddMenuItem("Open Continuum VPN", "Show the VPN window")
	systray.AddSeparator()
	quitItem := systray.AddMenuItem("Quit", "Quit Continuum VPN")
	createWindow()
	go func() {
		for {
			select {
			case <-openItem.ClickedCh:
				showWindow()
			case <-quitItem.ClickedCh:
				systray.Quit()
				return
			}
		}
	}()
	refresh()
}

func exeDir() string {
	path, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(path)
}

func pythonExe() string {
	bundled := filepath.Join(exeDir(), "python", "python.exe")
	if _, err := os.Stat(bundled); err == nil {
		return bundled
	}
	return "python"
}

func runEngine(args []string, stdin string) (string, error) {
	cmd := exec.Command(pythonExe(), append([]string{filepath.Join(exeDir(), "resources", "engine.py")}, args...)...)
	cmd.Stdin = strings.NewReader(stdin)
	out, err := cmd.CombinedOutput()
	text := strings.TrimSpace(string(out))
	if err != nil {
		if text == "" {
			text = err.Error()
		}
		return "", fmt.Errorf("%s", text)
	}
	return text, nil
}

func refresh() {
	go func() {
		text, err := runEngine([]string{"list"}, "")
		if err != nil {
			alert(err.Error())
			return
		}
		var parsed []profile
		if err := json.Unmarshal([]byte(text), &parsed); err != nil {
			alert(err.Error())
			return
		}
		rowsMu.Lock()
		rows = parsed
		rowsMu.Unlock()
		if hwnd != 0 {
			pPostMessageW.Call(uintptr(hwnd), wmApp, 0, 0)
		}
	}()
}

func createWindow() {
	className, _ := windows.UTF16PtrFromString("ContinuumVPN")
	title, _ := windows.UTF16PtrFromString("Continuum VPN")
	instance, _, _ := pGetModuleHandleW.Call(0)
	class := wndClass{
		WndProc:    wndproc,
		Instance:   windows.Handle(instance),
		ClassName:  className,
		Background: windows.Handle(6),
	}
	class.Size = uint32(unsafe.Sizeof(class))
	pRegisterClassExW.Call(uintptr(unsafe.Pointer(&class)))
	handle, _, _ := pCreateWindowExW.Call(
		0,
		uintptr(unsafe.Pointer(className)),
		uintptr(unsafe.Pointer(title)),
		0x00CF0000|wsVisible,
		80, 80, 640, 720,
		0, 0, instance, 0,
	)
	hwnd = windows.Handle(handle)
	pShowWindow.Call(handle, 1)
}

func windowProc(hwnd, msg, wparam, lparam uintptr) uintptr {
	switch msg {
	case 1: // WM_CREATE
		parent := windows.Handle(hwnd)
		statusBtn = child(parent, "button", "Disconnected", 430, 12, 180, 32, 1, 0)
		listBox = child(parent, "listbox", "", 16, 56, 590, 280, 2, lbsNotify|wsVScroll)
		child(parent, "button", "ON", 16, 348, 80, 32, 3, 0)
		child(parent, "button", "OFF", 104, 348, 80, 32, 4, 0)
		child(parent, "button", "Delete", 192, 348, 90, 32, 5, 0)
		child(parent, "button", "Import bundle…", 16, 392, 140, 32, 6, 0)
		child(parent, "static", "Paste a bundle or WireGuard config", 16, 436, 400, 20, 10, 0)
		pasteBox = child(parent, "edit", "", 16, 460, 590, 140, 7, esMulti|wsVScroll)
		child(parent, "button", "Import pasted text", 16, 612, 160, 32, 8, 0)
		child(parent, "button", "Check for updates", 186, 612, 150, 32, 9, 0)
		child(parent, "button", "Quit", 346, 612, 80, 32, 11, 0)
		return 0
	case wmClose:
		pShowWindow.Call(hwnd, 0)
		return 0
	case wmApp:
		fillList()
		return 0
	case wmCommand:
		id := int(wparam & 0xffff)
		switch id {
		case 1:
			toggle()
		case 2:
			rememberSelection()
		case 3:
			rememberSelection()
			setProfile(true)
		case 4:
			rememberSelection()
			setProfile(false)
		case 5:
			rememberSelection()
			removeSelected()
		case 6:
			importFile()
		case 8:
			importPasted()
		case 9:
			checkUpdate()
		case 11:
			systray.Quit()
		}
		return 0
	case wmDestroy:
		return 0
	}
	ret, _, _ := pDefWindowProcW.Call(hwnd, msg, wparam, lparam)
	return ret
}

func child(parent windows.Handle, className, title string, x, y, w, h int, id uintptr, extra uint32) windows.Handle {
	class, _ := windows.UTF16PtrFromString(className)
	text, _ := windows.UTF16PtrFromString(title)
	handle, _, _ := pCreateWindowExW.Call(
		0,
		uintptr(unsafe.Pointer(class)),
		uintptr(unsafe.Pointer(text)),
		uintptr(wsChild|wsVisible|wsTabStop|extra),
		uintptr(x), uintptr(y), uintptr(w), uintptr(h),
		uintptr(parent), id, 0, 0,
	)
	return windows.Handle(handle)
}

func fillList() {
	pSendMessageW.Call(uintptr(listBox), lbReset, 0, 0)
	rowsMu.Lock()
	current := append([]profile(nil), rows...)
	rowsMu.Unlock()
	active := ""
	for _, row := range current {
		line := strings.TrimSpace(row.CountryFlag + " " + blank(row.Label))
		line += "    " + blank(row.CountryCode) + "    " + obfuscation(row.Obfuscation)
		line += "    " + blank(row.AdBlock) + "    " + blank(row.RateLimit) + "    " + blank(row.Endpoint)
		text, _ := windows.UTF16PtrFromString(line)
		pSendMessageW.Call(uintptr(listBox), lbAdd, 0, uintptr(unsafe.Pointer(text)))
		if row.Active {
			active = row.Label
		}
	}
	if active != "" {
		setStatus("Connected to "+active, true)
		return
	}
	if len(current) == 0 {
		setStatus("Disconnected", false)
		return
	}
	setStatus("Disconnected", false)
}

func setStatus(text string, connected bool) {
	prefix := "Disconnected"
	if connected {
		prefix = text
	} else if text != "" {
		prefix = text
	}
	wide, _ := windows.UTF16PtrFromString(prefix)
	pSetWindowTextW.Call(uintptr(statusBtn), uintptr(unsafe.Pointer(wide)))
}

func rememberSelection() {
	sel, _, _ := pSendMessageW.Call(uintptr(listBox), lbGetSel, 0, 0)
	rowsMu.Lock()
	defer rowsMu.Unlock()
	index := int(int32(sel))
	if index >= 0 && index < len(rows) {
		selected = rows[index].Iface
	}
}

func chosen() (profile, bool) {
	rowsMu.Lock()
	defer rowsMu.Unlock()
	for _, row := range rows {
		if row.Iface == selected {
			return row, true
		}
	}
	if len(rows) > 0 {
		return rows[0], true
	}
	return profile{}, false
}

func toggle() {
	row, ok := chosen()
	if !ok || busy {
		return
	}
	rowsMu.Lock()
	var active *profile
	for i := range rows {
		if rows[i].Active {
			active = &rows[i]
			break
		}
	}
	rowsMu.Unlock()
	if active != nil {
		selected = active.Iface
		setProfile(false)
		return
	}
	selected = row.Iface
	setProfile(true)
}

func setProfile(turnOn bool) {
	if selected == "" || busy {
		return
	}
	busy = true
	iface := selected
	go func() {
		defer func() { busy = false }()
		action := "down"
		if turnOn {
			action = "up"
		}
		if _, err := runEngine([]string{action, iface}, ""); err != nil {
			alert(err.Error())
		}
		refresh()
	}()
}

func removeSelected() {
	if selected == "" {
		return
	}
	iface := selected
	go func() {
		if _, err := runEngine([]string{"delete", iface}, ""); err != nil {
			alert(err.Error())
		}
		refresh()
	}()
}

func importFile() {
	script := `Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'VPN bundle (*.json)|*.json|WireGuard (*.conf)|*.conf|All files|*.*'; if ($d.ShowDialog() -eq 'OK') { Write-Output $d.FileName }`
	out, err := exec.Command("powershell", "-NoProfile", "-STA", "-Command", script).Output()
	path := strings.TrimSpace(string(out))
	if err != nil || path == "" {
		return
	}
	go func() {
		if _, err := runEngine([]string{"import-file", path}, ""); err != nil {
			alert(err.Error())
		}
		refresh()
	}()
}

func importPasted() {
	buf := make([]uint16, 65536)
	pSendMessageW.Call(uintptr(pasteBox), 13, uintptr(len(buf)), uintptr(unsafe.Pointer(&buf[0]))) // WM_GETTEXT
	text := windows.UTF16ToString(buf)
	if strings.TrimSpace(text) == "" {
		alert("Paste a profile bundle first.")
		return
	}
	go func() {
		if _, err := runEngine([]string{"import-text", "pasted.conf"}, text); err != nil {
			alert(err.Error())
		}
		refresh()
	}()
}

func checkUpdate() {
	go func() {
		text, err := runEngine([]string{"check-update"}, "")
		if err != nil {
			alert(err.Error())
			return
		}
		var found map[string]string
		_ = json.Unmarshal([]byte(text), &found)
		if found["url"] == "" {
			alert("Continuum VPN is up to date.")
			return
		}
		alert("Continuum VPN " + found["tag"] + " is available. Download it from the node VPN panel. Windows SmartScreen may say the app is unrecognized: choose More info, then Run anyway. Saved profiles stay on this computer.\n" + found["url"])
	}()
}

func showWindow() {
	if hwnd != 0 {
		pShowWindow.Call(uintptr(hwnd), 9)
	}
}

func alert(message string) {
	title, _ := windows.UTF16PtrFromString("Continuum VPN")
	text, _ := windows.UTF16PtrFromString(message)
	pMessageBoxW.Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), 0)
}

func blank(value string) string {
	if strings.TrimSpace(value) == "" {
		return "—"
	}
	return value
}

func obfuscation(value string) string {
	switch value {
	case "", "none":
		return "None"
	case "shadowsocks":
		return "Shadowsocks"
	case "wg_obfuscator":
		return "wg-obfuscator"
	default:
		return value
	}
}

func trayIcon() []byte {
	// 16x16 green square. Windows wants an ICO, not a PNG.
	const size = 16
	header := []byte{
		0, 0, 1, 0, 1, 0,
		size, size, 0, 0, 0, 0, 32, 0,
		0x48, 0x04, 0, 0,
		22, 0, 0, 0,
	}
	dib := []byte{
		40, 0, 0, 0,
		size, 0, 0, 0,
		size * 2, 0, 0, 0,
		1, 0, 32, 0,
	}
	pixels := make([]byte, size*size*4)
	for i := 0; i < size*size; i++ {
		pixels[i*4+0] = 0x3e
		pixels[i*4+1] = 0x8e
		pixels[i*4+2] = 0x1e
		pixels[i*4+3] = 0xff
	}
	mask := make([]byte, size*size/8)
	icon := append(header, dib...)
	icon = append(icon, pixels...)
	icon = append(icon, mask...)
	return icon
}
