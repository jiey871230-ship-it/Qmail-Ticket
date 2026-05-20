const db = wx.cloud.database()

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
    return { tickets: [], summary: { count: 0, totalAmount: 0 } }
  }

  // 清空旧数据后保存
  await clearAllTickets()

  const tickets = result.tickets.map(t => ({
    ...t,
    createTime: db.serverDate(),
  }))

  for (const t of tickets) {
    try {
      await db.collection('tickets').add({ data: t })
    } catch (e) {
      console.error('保存票据失败:', e)
    }
  }

  return { tickets, summary: result.summary }
}

/**
 * 发送邮件（云函数重新解析并发送）
 */
async function sendEmail({ email, code, toAddress, startDate, endDate }) {
  console.log('Calling sendEmail cloud function...')
  const res = await wx.cloud.callFunction({
    name: 'sendEmail',
    data: { email, code, toAddress, startDate, endDate },
  })
  console.log('sendEmail result:', JSON.stringify(res.result))
  return res
}

async function getAllTickets() {
  const { data } = await db.collection('tickets')
    .orderBy('travelDate', 'asc')
    .get()
  return data
}

async function clearAllTickets() {
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
