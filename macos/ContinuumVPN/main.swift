import Cocoa

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()

final class AppDelegate: NSObject, NSApplicationDelegate {
    let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var window: NSWindow!
    var profileColumn: NSStackView!
    var statusButton: NSButton!
    var rows: [[String: Any]] = []
    var selected = ""
    var busy = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let others = NSRunningApplication.runningApplications(withBundleIdentifier: "com.continuumdao.vpn.widget")
        if others.contains(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }) {
            NSApp.terminate(nil)
            return
        }
        if let button = statusItem.button {
            button.title = "VPN"
            button.action = #selector(presentWindow)
            button.target = self
        }
        buildWindow()
        presentWindow()
        Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            self?.reload(rebuild: true)
        }
        reload(rebuild: true)
    }

    func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 680),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Continuum VPN"
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 420, height: 360)

        let header = NSView()
        statusButton = NSButton(title: "Disconnected", target: self, action: #selector(toggleConnection))
        statusButton.isBordered = false
        statusButton.wantsLayer = true
        statusButton.layer?.cornerRadius = 16
        statusButton.contentTintColor = .white
        statusButton.font = NSFont.boldSystemFont(ofSize: 13)
        statusButton.translatesAutoresizingMaskIntoConstraints = false
        header.addSubview(statusButton)
        NSLayoutConstraint.activate([
            statusButton.trailingAnchor.constraint(equalTo: header.trailingAnchor),
            statusButton.centerYAnchor.constraint(equalTo: header.centerYAnchor),
            statusButton.heightAnchor.constraint(equalToConstant: 34),
            header.heightAnchor.constraint(equalToConstant: 48),
        ])

        let title = NSTextField(labelWithString: "Continuum VPN")
        title.font = NSFont.boldSystemFont(ofSize: 18)
        title.alignment = .center

        profileColumn = NSStackView()
        profileColumn.orientation = .vertical
        profileColumn.alignment = .leading
        profileColumn.spacing = 10
        profileColumn.translatesAutoresizingMaskIntoConstraints = false

        let document = NSView()
        document.translatesAutoresizingMaskIntoConstraints = false
        document.addSubview(profileColumn)
        NSLayoutConstraint.activate([
            profileColumn.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 8),
            profileColumn.trailingAnchor.constraint(equalTo: document.trailingAnchor, constant: -8),
            profileColumn.topAnchor.constraint(equalTo: document.topAnchor, constant: 8),
            profileColumn.bottomAnchor.constraint(equalTo: document.bottomAnchor, constant: -8),
            profileColumn.widthAnchor.constraint(equalTo: document.widthAnchor, constant: -16),
        ])

        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        scroll.documentView = document
        document.heightAnchor.constraint(greaterThanOrEqualTo: scroll.heightAnchor).isActive = false

        let actions = NSStackView()
        actions.orientation = .vertical
        actions.spacing = 6
        for item in [
            ("Import bundle…", #selector(importBundle)),
            ("Paste bundle", #selector(pasteBundle)),
            ("Check for updates", #selector(checkUpdate)),
            ("Quit", #selector(quit)),
        ] {
            let button = NSButton(title: item.0, target: self, action: item.1)
            button.bezelStyle = .rounded
            actions.addArrangedSubview(button)
            button.widthAnchor.constraint(equalTo: actions.widthAnchor).isActive = true
        }

        let root = NSStackView(views: [header, title, scroll, actions])
        root.orientation = .vertical
        root.edgeInsets = NSEdgeInsets(top: 12, left: 18, bottom: 18, right: 18)
        root.spacing = 8
        root.translatesAutoresizingMaskIntoConstraints = false
        window.contentView = root
        NSLayoutConstraint.activate([
            header.widthAnchor.constraint(equalTo: root.widthAnchor),
            scroll.widthAnchor.constraint(equalTo: root.widthAnchor),
            actions.widthAnchor.constraint(equalTo: root.widthAnchor),
        ])
        paintStatus(text: "Disconnected", connected: false, tip: "Import a VPN to connect", enabled: false)
    }

    @objc func presentWindow() {
        if let screen = window.screen ?? NSScreen.main {
            let area = screen.visibleFrame
            let size = window.frame.size
            window.setFrameOrigin(NSPoint(x: area.maxX - size.width - 12, y: area.maxY - size.height - 8))
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func resources() -> URL {
        Bundle.main.resourceURL ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    }

    func pythonPath() -> String {
        let bundled = resources().appendingPathComponent("python/bin/python3").path
        if FileManager.default.isExecutableFile(atPath: bundled) {
            return bundled
        }
        return "/usr/bin/python3"
    }

    func runEngine(_ args: [String], stdin: String = "") throws -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath())
        process.arguments = [resources().appendingPathComponent("engine.py").path] + args
        var env = ProcessInfo.processInfo.environment
        env["CONTINUUM_VPN_PLATFORM"] = "darwin"
        process.environment = env
        let input = Pipe()
        let output = Pipe()
        let error = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = error
        try process.run()
        if !stdin.isEmpty {
            input.fileHandleForWriting.write(Data(stdin.utf8))
        }
        input.fileHandleForWriting.closeFile()
        process.waitUntilExit()
        let text = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let err = String(data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        if process.terminationStatus != 0 {
            throw EngineFailure(err.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Continuum VPN failed" : err.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return text
    }

    func alert(_ message: String, style: NSAlert.Style = .warning) {
        let dialog = NSAlert()
        dialog.messageText = "Continuum VPN"
        dialog.informativeText = message
        dialog.alertStyle = style
        dialog.addButton(withTitle: "Close")
        dialog.beginSheetModal(for: window)
    }

    func reload(rebuild: Bool) {
        guard !busy else { return }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let parsed: [[String: Any]]
            do {
                let text = try self.runEngine(["list"])
                parsed = (try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [[String: Any]]) ?? []
            } catch {
                DispatchQueue.main.async { self.alert(error.localizedDescription) }
                return
            }
            DispatchQueue.main.async {
                self.rows = parsed
                if rebuild {
                    self.rebuildProfiles()
                }
                self.refreshStatus()
            }
        }
    }

    func rebuildProfiles() {
        profileColumn.arrangedSubviews.forEach { view in
            profileColumn.removeArrangedSubview(view)
            view.removeFromSuperview()
        }
        if rows.isEmpty {
            profileColumn.addArrangedSubview(NSTextField(labelWithString: "No VPNs imported yet."))
            return
        }
        for row in rows {
            profileColumn.addArrangedSubview(card(row))
        }
    }

    func card(_ row: [String: Any]) -> NSView {
        let iface = string(row["iface"])
        let box = NSBox()
        box.boxType = .custom
        box.cornerRadius = 8
        box.borderWidth = 1
        let grid = NSStackView()
        grid.orientation = .vertical
        grid.alignment = .leading
        grid.spacing = 2
        let title = NSTextField(labelWithString: "\(string(row["countryFlag"])) \(string(row["label"]))".trimmingCharacters(in: .whitespaces))
        title.font = NSFont.boldSystemFont(ofSize: 13)
        grid.addArrangedSubview(title)
        for pair in [
            ("Country", string(row["countryCode"])),
            ("Obfuscation", obfuscation(string(row["obfuscation"]))),
            ("Ad blocking", blank(string(row["adBlock"]))),
            ("Rate limit", blank(string(row["rateLimit"]))),
            ("Endpoint", blank(string(row["endpoint"]))),
        ] {
            grid.addArrangedSubview(NSTextField(labelWithString: "\(pair.0): \(pair.1)"))
        }
        let buttons = NSStackView()
        buttons.orientation = .horizontal
        buttons.spacing = 6
        let on = coloredButton("ON", color: NSColor(calibratedRed: 0.12, green: 0.56, blue: 0.24, alpha: 1))
        let off = coloredButton("OFF", color: NSColor(calibratedRed: 0.77, green: 0.13, blue: 0.12, alpha: 1))
        on.action = #selector(turnOn(_:))
        off.action = #selector(turnOff(_:))
        on.target = self
        off.target = self
        on.identifier = NSUserInterfaceItemIdentifier(iface)
        off.identifier = NSUserInterfaceItemIdentifier(iface)
        let active = (row["active"] as? Bool) == true
        on.layer?.borderWidth = active ? 2 : 0
        off.layer?.borderWidth = active ? 0 : 2
        on.layer?.borderColor = NSColor.white.cgColor
        off.layer?.borderColor = NSColor.white.cgColor
        let trash = NSButton(title: "Delete", target: self, action: #selector(askDelete(_:)))
        trash.identifier = NSUserInterfaceItemIdentifier(iface)
        trash.bezelStyle = .rounded
        buttons.addArrangedSubview(on)
        buttons.addArrangedSubview(off)
        buttons.addArrangedSubview(trash)
        grid.addArrangedSubview(buttons)
        box.contentView = grid
        box.translatesAutoresizingMaskIntoConstraints = false
        box.widthAnchor.constraint(equalToConstant: 500).isActive = true
        return box
    }

    func coloredButton(_ title: String, color: NSColor) -> NSButton {
        let button = NSButton(title: title, target: nil, action: nil)
        button.isBordered = false
        button.wantsLayer = true
        button.layer?.backgroundColor = color.cgColor
        button.layer?.cornerRadius = 6
        button.attributedTitle = NSAttributedString(
            string: title,
            attributes: [.foregroundColor: NSColor.white, .font: NSFont.boldSystemFont(ofSize: 12)]
        )
        return button
    }

    func paintStatus(text: String, connected: Bool, tip: String, enabled: Bool) {
        statusButton.attributedTitle = NSAttributedString(
            string: "  \(text)  ",
            attributes: [.foregroundColor: NSColor.white, .font: NSFont.boldSystemFont(ofSize: 13)]
        )
        statusButton.toolTip = tip
        statusButton.isEnabled = enabled
        let color = connected
            ? NSColor(calibratedRed: 0.12, green: 0.56, blue: 0.24, alpha: 1)
            : NSColor(calibratedRed: 0.77, green: 0.13, blue: 0.12, alpha: 1)
        statusButton.layer?.backgroundColor = color.cgColor
    }

    func refreshStatus() {
        if let active = rows.first(where: { ($0["active"] as? Bool) == true }) {
            let label = string(active["label"])
            paintStatus(text: "Connected to \(label)", connected: true, tip: "Disconnect \(label)", enabled: true)
            return
        }
        let target = rows.first { string($0["iface"]) == selected } ?? rows.first
        if let target {
            paintStatus(text: "Disconnected", connected: false, tip: "Connect \(string(target["label"]))", enabled: true)
            return
        }
        paintStatus(text: "Disconnected", connected: false, tip: "Import a VPN to connect", enabled: false)
    }

    @objc func toggleConnection() {
        guard !busy else { return }
        if let active = rows.first(where: { ($0["active"] as? Bool) == true }) {
            setProfile(string(active["iface"]), turnOn: false)
            return
        }
        let target = rows.first { string($0["iface"]) == selected } ?? rows.first
        if let target {
            setProfile(string(target["iface"]), turnOn: true)
        }
    }

    @objc func turnOn(_ sender: NSButton) {
        selected = sender.identifier?.rawValue ?? ""
        setProfile(selected, turnOn: true)
    }

    @objc func turnOff(_ sender: NSButton) {
        selected = sender.identifier?.rawValue ?? ""
        setProfile(selected, turnOn: false)
    }

    func setProfile(_ iface: String, turnOn: Bool) {
        guard !iface.isEmpty, !busy else { return }
        if let row = rows.first(where: { string($0["iface"]) == iface }), (row["active"] as? Bool) == turnOn {
            selected = iface
            return
        }
        busy = true
        paintStatus(text: turnOn ? "Connecting…" : "Disconnecting…", connected: false, tip: "", enabled: false)
        statusButton.layer?.backgroundColor = NSColor.gray.cgColor
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                _ = try self.runEngine([turnOn ? "up" : "down", iface])
                DispatchQueue.main.async {
                    self.busy = false
                    self.selected = iface
                    self.reload(rebuild: true)
                }
            } catch {
                DispatchQueue.main.async {
                    self.busy = false
                    self.alert(error.localizedDescription)
                    self.reload(rebuild: true)
                }
            }
        }
    }

    @objc func askDelete(_ sender: NSButton) {
        let iface = sender.identifier?.rawValue ?? ""
        let label = string(rows.first { string($0["iface"]) == iface }?["label"])
        let dialog = NSAlert()
        dialog.messageText = "Delete \(label.isEmpty ? iface : label)?"
        dialog.informativeText = "This removes the saved VPN from this computer."
        dialog.addButton(withTitle: "Delete")
        dialog.addButton(withTitle: "Cancel")
        dialog.beginSheetModal(for: window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self else { return }
            self.busy = true
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    _ = try self.runEngine(["delete", iface])
                } catch {
                    DispatchQueue.main.async { self.alert(error.localizedDescription) }
                }
                DispatchQueue.main.async {
                    self.busy = false
                    self.reload(rebuild: true)
                }
            }
        }
    }

    @objc func importBundle() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let url = panel.url, let self else { return }
            self.busy = true
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    _ = try self.runEngine(["import-file", url.path])
                } catch {
                    DispatchQueue.main.async { self.alert(error.localizedDescription) }
                }
                DispatchQueue.main.async {
                    self.busy = false
                    self.reload(rebuild: true)
                }
            }
        }
    }

    @objc func pasteBundle() {
        let editor = NSTextView(frame: NSRect(x: 0, y: 0, width: 460, height: 180))
        editor.font = NSFont.userFixedPitchFont(ofSize: 12)
        editor.string = NSPasteboard.general.string(forType: .string) ?? ""
        let scroll = NSScrollView(frame: editor.frame)
        scroll.documentView = editor
        scroll.hasVerticalScroller = true
        let dialog = NSAlert()
        dialog.messageText = "Paste bundle"
        dialog.informativeText = "Paste a profile bundle or a WireGuard config."
        dialog.accessoryView = scroll
        dialog.addButton(withTitle: "Import")
        dialog.addButton(withTitle: "Cancel")
        dialog.beginSheetModal(for: window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self else { return }
            let text = editor.string
            self.busy = true
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    _ = try self.runEngine(["import-text", "pasted.conf"], stdin: text)
                } catch {
                    DispatchQueue.main.async { self.alert(error.localizedDescription) }
                }
                DispatchQueue.main.async {
                    self.busy = false
                    self.reload(rebuild: true)
                }
            }
        }
    }

    @objc func checkUpdate() {
        busy = true
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                let text = try self.runEngine(["check-update"])
                let found = (try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: String]) ?? [:]
                DispatchQueue.main.async {
                    self.busy = false
                    guard let url = found["url"], !url.isEmpty, let tag = found["tag"] else {
                        self.alert("Continuum VPN is up to date.", style: .informational)
                        return
                    }
                    let dialog = NSAlert()
                    dialog.messageText = "Continuum VPN \(tag) is available"
                    dialog.informativeText = "Download the zip, unzip it, and replace Continuum VPN.app. macOS Gatekeeper blocks an unsigned app on the first open: Control-click the new app and choose Open, then choose Open again. Saved profiles stay on this computer."
                    dialog.addButton(withTitle: "Download")
                    dialog.addButton(withTitle: "Not now")
                    dialog.beginSheetModal(for: self.window) { response in
                        guard response == .alertFirstButtonReturn, let link = URL(string: url) else { return }
                        NSWorkspace.shared.open(link)
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    self.busy = false
                    self.alert(error.localizedDescription)
                }
            }
        }
    }

    @objc func quit() {
        NSApp.terminate(nil)
    }

    func string(_ value: Any?) -> String {
        if let text = value as? String { return text }
        return ""
    }

    func blank(_ value: String) -> String {
        value.isEmpty ? "—" : value
    }

    func obfuscation(_ value: String) -> String {
        switch value {
        case "", "none": return "None"
        case "shadowsocks": return "Shadowsocks"
        case "wg_obfuscator": return "wg-obfuscator"
        case "udp2raw": return "udp2raw"
        default: return value
        }
    }
}

struct EngineFailure: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}
