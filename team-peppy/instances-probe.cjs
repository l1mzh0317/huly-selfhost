const { chmodSync, lstatSync, unlinkSync } = require('node:fs')
const { createServer } = require('node:http')
const { createConnection, isIP } = require('node:net')

const path = '/run/pepper-instance-probe/connectivity.sock'
const maxChecks = 8
let active = 0

function isTailnetAddress(address) {
  if (isIP(address) === 4) {
    const [first, second] = address.split('.').map(Number)
    return first === 100 && second >= 64 && second < 128
  }
  return isIP(address) === 6 && /^fd7a:115c:a1e0:/i.test(address)
}

const server = createServer({ requestTimeout: 4000, headersTimeout: 2000, maxHeaderSize: 2048 }, (req, res) => {
  const params = new URLSearchParams(req.url?.slice('/probe?'.length))
  const address = params.get('address') ?? ''
  const port = Number(params.get('port'))
  if (req.method !== 'GET' || !req.url?.startsWith('/probe?') || !isTailnetAddress(address) || !Number.isInteger(port) || port < 1 || port > 65535) {
    res.writeHead(400).end()
    return
  }
  if (active >= maxChecks) {
    res.writeHead(429).end()
    return
  }
  active++
  const check = createConnection({ host: address, port, timeout: 3000 })
  const finish = reachable => {
    check.destroy()
    if (!res.destroyed && !res.writableEnded) {
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ reachable }))
    }
  }
  check.once('connect', () => finish(true))
  check.once('error', () => finish(false))
  check.once('timeout', () => finish(false))
  check.once('close', () => { active-- })
  res.once('close', () => { check.destroy() })
})

server.maxConnections = 16
server.setTimeout(5000, socket => { socket.destroy() })

try {
  if (!lstatSync(path).isSocket()) throw new Error('Unexpected file in the connectivity socket directory')
  unlinkSync(path)
} catch (error) {
  if (error.code !== 'ENOENT') throw error
}
// Only the Huly app and this probe can mount the dedicated socket volume. The app mounts it read-only.
server.listen(path, () => { chmodSync(path, 0o666) })
