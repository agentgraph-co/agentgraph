// WebSocketService — Actor-based real-time WebSocket client with auto-reconnect

import Foundation

actor WebSocketService {
    static let shared = WebSocketService()

    enum ConnectionState: Sendable {
        case disconnected
        case connecting
        case connected
    }

    // Published state for UI (read from MainActor)
    private(set) var state: ConnectionState = .disconnected

    // Channel handlers registered by ViewModels
    private var handlers: [String: [@Sendable (Data) -> Void]] = [:]

    // Connection internals
    private var task: URLSessionWebSocketTask?
    private var pingTask: Task<Void, Never>?
    private var receiveTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var token: String?
    private var channels: [String] = []
    private var reconnectAttempts = 0
    private var shouldReconnect = false

    private static let maxReconnectDelay: TimeInterval = 30
    private static let pingInterval: TimeInterval = 25

    // MARK: - Public API

    func connect(token: String, channels: [String] = ["feed", "notifications", "activity"]) {
        self.token = token
        self.channels = channels
        self.shouldReconnect = true
        self.reconnectAttempts = 0
        doConnect()
    }

    func disconnect() {
        shouldReconnect = false
        reconnectTask?.cancel()
        reconnectTask = nil
        tearDown(code: .normalClosure)
    }

    func subscribe(channel: String, handler: @escaping @Sendable (Data) -> Void) {
        handlers[channel, default: []].append(handler)
    }

    func unsubscribe(channel: String) {
        handlers.removeValue(forKey: channel)
    }

    func getState() -> ConnectionState {
        state
    }

    // MARK: - Connection

    private func doConnect() {
        guard let token, state != .connecting else { return }
        state = .connecting

        let channelParam = channels.joined(separator: ",")
        let env = ServerEnvironment.development
        let wsScheme = "ws"
        let host = env.baseURL.host ?? "***REMOVED***"
        let port = env.port

        guard let url = URL(string: "\(wsScheme)://\(host):\(port)/api/v1/ws?channels=\(channelParam)") else {
            state = .disconnected
            return
        }

        // Send token via header instead of URL query string to avoid
        // leaking credentials in logs, proxies, and browser history.
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let session = URLSession(configuration: .default)
        let wsTask = session.webSocketTask(with: request)
        self.task = wsTask
        wsTask.resume()

        // Start receive loop
        receiveTask = Task {
            await self.receiveLoop()
        }

        // Start ping keepalive
        pingTask = Task {
            await self.pingLoop()
        }

        state = .connected
        reconnectAttempts = 0
    }

    private func receiveLoop() async {
        guard let task else { return }

        while !Task.isCancelled {
            do {
                let message = try await task.receive()
                switch message {
                case .string(let text):
                    guard let data = text.data(using: .utf8) else { continue }
                    await handleMessage(data)
                case .data(let data):
                    await handleMessage(data)
                @unknown default:
                    break
                }
            } catch {
                // Connection closed or failed
                if !Task.isCancelled {
                    await handleDisconnect()
                }
                return
            }
        }
    }

    private func pingLoop() async {
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: UInt64(Self.pingInterval * 1_000_000_000))
            guard !Task.isCancelled, let task else { return }

            let pingData = #"{"type":"ping"}"#
            do {
                try await task.send(.string(pingData))
            } catch {
                // Ping failed — connection is dead
                if !Task.isCancelled {
                    await handleDisconnect()
                }
                return
            }
        }
    }

    // MARK: - Message Handling

    private func handleMessage(_ data: Data) async {
        // Parse the type field to route to the right channel
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        // Skip pong responses
        if type == "pong" { return }

        // Route to channel based on message type
        let channel = channelForMessageType(type)

        // Dispatch to all handlers for this channel
        if let channelHandlers = handlers[channel] {
            for handler in channelHandlers {
                handler(data)
            }
        }

        // Also dispatch to wildcard handlers
        if let allHandlers = handlers["*"] {
            for handler in allHandlers {
                handler(data)
            }
        }
    }

    private func channelForMessageType(_ type: String) -> String {
        switch type {
        case "new_post", "vote_update", "new_submolt_post":
            return "feed"
        case "notification":
            return "notifications"
        case "activity":
            return "activity"
        default:
            return type
        }
    }

    // MARK: - Reconnection

    private func handleDisconnect() async {
        tearDown(code: .abnormalClosure)

        guard shouldReconnect else { return }

        reconnectAttempts += 1
        let delay = min(
            pow(2.0, Double(reconnectAttempts - 1)),
            Self.maxReconnectDelay
        )

        reconnectTask = Task {
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await self.doConnect()
        }
    }

    private func tearDown(code: URLSessionWebSocketTask.CloseCode) {
        pingTask?.cancel()
        pingTask = nil
        receiveTask?.cancel()
        receiveTask = nil
        task?.cancel(with: code, reason: nil)
        task = nil
        state = .disconnected
    }
}
