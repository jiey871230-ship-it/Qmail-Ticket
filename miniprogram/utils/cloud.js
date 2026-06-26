const db = wx.cloud.database()

// 内存缓存
let _ticketCache = null

/**
 * 提取票据（只返回元数据）
 */
async function fetchTickets({ email, code, startDate, endDate }) {
  const { result } = await wx.cloud.callFunction({
    name: 'fetchTickets',
    data: { email, code, startDate, endDate },
  })

  if (result.error) {
    throw new Error(result.error)
  }

  if (!result.tickets || result.tickets.length === 0) {
    _ticketCache = []
    return { tickets: [], summary: { count: 0, totalAmount: 0 } }
  }

  _ticketCache = result.tickets

  return { tickets: result.tickets, summary: result.summary }
}

/**
 * 发送邮件（云函数重新解析并发送）
 */
async function sendEmail({ email, code, toAddress, startDate, endDate }) {
  const res = await wx.cloud.callFunction({
    name: 'sendEmail',
    data: { email, code, toAddress, startDate, endDate },
  })
  return res
}

async function getAllTickets() {
  if (_ticketCache) {
    return [..._ticketCache].sort((a, b) => a.travelDate.localeCompare(b.travelDate))
  }
  // 无缓存时从数据库读（历史数据兜底）
  const { data } = await db.collection('tickets')
    .orderBy('travelDate', 'asc')
    .limit(100)
    .get()
  return data
}

async function clearAllTickets() {
  _ticketCache = null
  let total = 0
  while (true) {
    const { data } = await db.collection('tickets').limit(100).get()
    if (data.length === 0) break
    for (const t of data) {
      await db.collection('tickets').doc(t._id).remove()
    }
    total += data.length
  }
  return total
}

module.exports = {
  fetchTickets,
  sendEmail,
  getAllTickets,
  clearAllTickets,
  db,
}
