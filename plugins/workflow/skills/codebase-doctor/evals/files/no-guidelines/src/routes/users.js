const express = require('express')
const router = express.Router()

const users = [
  { id: 1, name: 'Alice', email: 'alice@example.com' },
  { id: 2, name: 'Bob', email: 'bob@example.com' },
]

// バリデーションなし
router.get('/', (req, res) => {
  res.json(users)
})

// 不統一なエラーレスポンス: 200 でエラーを返す
router.get('/:id', (req, res) => {
  const user = users.find(u => u.id === parseInt(req.params.id))
  if (!user) {
    res.status(200).send('error: user not found')  // アンチパターン: 200 + エラー文字列
    return
  }
  res.json(user)
})

// POST: バリデーションなし、エラーレスポンスも不統一
router.post('/', (req, res) => {
  const { name, email } = req.body
  if (!name) {
    res.status(500).json({ msg: 'name required' })  // 500 を入力バリデーションに使う
    return
  }
  const newUser = { id: users.length + 1, name, email }
  users.push(newUser)
  res.status(200).json(newUser)  // 201 ではなく 200
})

module.exports = router
