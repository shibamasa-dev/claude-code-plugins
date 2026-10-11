const express = require('express')
const router = express.Router()

const users = [
  { id: 1, name: 'Alice', email: 'alice@example.com' },
  { id: 2, name: 'Bob', email: 'bob@example.com' },
]

// no validation
router.get('/', (req, res) => {
  res.json(users)
})

// inconsistent error response: returns an error with 200
router.get('/:id', (req, res) => {
  const user = users.find(u => u.id === parseInt(req.params.id))
  if (!user) {
    res.status(200).send('error: user not found')  // anti-pattern: 200 + error string
    return
  }
  res.json(user)
})

// POST: no validation, inconsistent error response too
router.post('/', (req, res) => {
  const { name, email } = req.body
  if (!name) {
    res.status(500).json({ msg: 'name required' })  // 500 used for input validation
    return
  }
  const newUser = { id: users.length + 1, name, email }
  users.push(newUser)
  res.status(200).json(newUser)  // 200 instead of 201
})

module.exports = router
