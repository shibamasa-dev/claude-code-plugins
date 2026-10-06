const express = require('express')
const winston = require('winston')
const usersRouter = require('./routes/users')

const logger = winston.createLogger({
  level: 'info',
  format: winston.format.json(),
  transports: [new winston.transports.Console()],
})

const app = express()
app.use(express.json())

const PORT = process.env.PORT || 3000

app.use('/api/users', usersRouter)

app.get('/health', (req, res) => {
  logger.info('Health check requested')
  res.json({ status: 'ok' })
})

// エラー握りつぶし: 空の catch ブロック
try {
  const config = JSON.parse(process.env.APP_CONFIG || '{}')
} catch (e) {
  // 意図的に空
}

const server = app.listen(PORT, () => {
  logger.info(`Server running on port ${PORT}`)
})

// Graceful shutdown
process.on('SIGTERM', () => {
  logger.info('SIGTERM received, shutting down gracefully')
  server.close(() => {
    logger.info('Server closed')
    process.exit(0)
  })
})

process.on('SIGINT', () => {
  logger.info('SIGINT received')
  server.close()
  process.exit(0)
})
