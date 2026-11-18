// Market Skew.app: a native window around the local dashboard. It starts the server on launch and stops it on quit.
import AppKit
import WebKit

private let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String ?? "Market Skew"
// Follows the page's ivory or its dark ground, whichever the Mac is set to.
private let paper = NSColor(name: nil) { appearance in
    appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        ? NSColor(srgbRed: 0x12 / 255, green: 0x14 / 255, blue: 0x12 / 255, alpha: 1)
        : NSColor(srgbRed: 0xF7 / 255, green: 0xF5 / 255, blue: 0xEF / 255, alpha: 1)
}

/// macOS treats a click on an unfocused window as "focus only". This lets that first click also press the button.
final class DashboardView: WKWebView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    private var window: NSWindow!
    private var webView: DashboardView!
    private var server: Process?
    private var allowedPort: Int?
    private var output = ""
    private var quitting = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        startServer()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        server?.terminate()
    }

    private func buildWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent() // nothing from the session is kept on disk
        webView = DashboardView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.underPageBackgroundColor = paper
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = appName
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.backgroundColor = paper
        window.minSize = NSSize(width: 480, height: 560)
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("\(appName)MainWindow")
        window.makeKeyAndOrderFront(nil)
    }

    private func buildMenu() {
        let main = NSMenu()
        let app = NSMenu()
        app.addItem(withTitle: "About \(appName)", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Hide \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        app.addItem(withTitle: "Quit \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        add(app, titled: appName, to: main)
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        add(edit, titled: "Edit", to: main)
        let view = NSMenu(title: "View")
        view.addItem(withTitle: "Reload", action: #selector(reload), keyEquivalent: "r").target = self
        add(view, titled: "View", to: main)
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        add(windowMenu, titled: "Window", to: main)
        NSApp.windowsMenu = windowMenu
        NSApp.mainMenu = main
    }

    private func add(_ menu: NSMenu, titled title: String, to main: NSMenu) {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.submenu = menu
        main.addItem(item)
    }

    @objc private func reload() { webView.reload() }

    private func startServer() {
        let info = Bundle.main.infoDictionary ?? [:]
        guard let python = info["SkewPython"] as? String, let configured = info["SkewProject"] as? String,
              let launcher = info["SkewLauncher"] as? String, let resources = Bundle.main.resourcePath else {
            return showProblem("The app was not installed properly. Run ./install.sh again from the project folder.")
        }
        _ = resources
        let project = configured
        let files = FileManager.default
        guard files.fileExists(atPath: "\(project)/\(launcher)"), files.isExecutableFile(atPath: python) else {
            return showProblem("The project folder moved or was deleted (it was at \(project)). Run ./install.sh again from the project folder.")
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-I", "-B", "\(project)/\(launcher)", "ui", "--port", "0", "--exit-with-parent"]
        process.currentDirectoryURL = URL(fileURLWithPath: project)
        process.environment = ["HOME": NSHomeDirectory(), "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin:\(NSHomeDirectory())/.local/bin", "PYTHONDONTWRITEBYTECODE": "1"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            guard let text = String(data: handle.availableData, encoding: .utf8), !text.isEmpty else { return }
            DispatchQueue.main.async { self?.received(text) }
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.serverStopped() }
        }
        do {
            try process.run()
            server = process
        } catch {
            showProblem("\(appName) could not start its dashboard.")
        }
    }

    private func received(_ text: String) {
        output += text
        guard allowedPort == nil, let match = output.range(of: #"http://127\.0\.0\.1:[0-9]+/"#, options: .regularExpression),
              let url = URL(string: String(output[match])), let port = url.port else { return }
        allowedPort = port
        webView.load(URLRequest(url: url))
    }

    private func serverStopped() {
        guard !quitting else { return }
        let reason = output.split(separator: "\n").last(where: { $0.hasPrefix("Error:") }).map(String.init)
        showProblem(reason ?? "The dashboard stopped. Quit \(appName) and open it again.")
    }

    private func showProblem(_ message: String) {
        allowedPort = nil
        let safe = message.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        webView.loadHTMLString("""
        <!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;display:grid;place-items:center;background:#f7f5ef;color:#1c1f1d;font:15px 'Helvetica Neue',sans-serif">
        <div style="width:min(420px,90vw)"><h1 style="font-size:32px;margin:0 0 12px">\(appName) could not start</h1><p>\(safe)</p></div>
        """, baseURL: nil)
    }

    // The window only ever shows the local dashboard. Any other destination is refused.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = action.request.url
        let isDashboard = url?.scheme == "http" && url?.host == "127.0.0.1" && url?.port == allowedPort && allowedPort != nil
        let isProblemPage = allowedPort == nil && url?.scheme == "about"
        decisionHandler(isDashboard || isProblemPage ? .allow : .cancel)
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
