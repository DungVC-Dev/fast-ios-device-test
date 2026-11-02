import Foundation
import Network

// Newline-delimited JSON over TCP, reached from the Mac through the CoreDevice tunnel.
// Requests are queued here and executed by the test on the main thread, where
// XCUITest expects to be called.
final class RequestServer {
    struct Request {
        let body: Data
        let reply: (String) -> Void
    }

    private let listener: NWListener
    private let queue = DispatchQueue(label: "fast.device.server")
    private let lock = NSLock()
    private var pending: [Request] = []

    init(port: NWEndpoint.Port) throws {
        listener = try NWListener(using: .tcp, on: port)
    }

    func start() {
        listener.newConnectionHandler = { [weak self] connection in
            connection.start(queue: self?.queue ?? .global())
            self?.receive(on: connection, buffer: Data())
        }
        listener.start(queue: queue)
    }

    func stop() {
        listener.cancel()
    }

    func next() -> Request? {
        lock.lock()
        defer { lock.unlock() }
        return pending.isEmpty ? nil : pending.removeFirst()
    }

    private func receive(on connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 1 << 20) { [weak self] data, _, isComplete, error in
            var buffer = buffer
            if let data { buffer.append(data) }
            if let newline = buffer.firstIndex(of: 0x0A) {
                let request = Request(body: buffer[..<newline]) { response in
                    connection.send(content: Data((response + "\n").utf8), completion: .contentProcessed { _ in
                        connection.cancel()
                    })
                }
                self?.enqueue(request)
            } else if isComplete || error != nil {
                connection.cancel()
            } else {
                self?.receive(on: connection, buffer: buffer)
            }
        }
    }

    private func enqueue(_ request: Request) {
        lock.lock()
        pending.append(request)
        lock.unlock()
    }
}
