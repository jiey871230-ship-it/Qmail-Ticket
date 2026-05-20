const db = wx.cloud.database()

function fetchTickets({ email, code, startDate, endDate, taskId }) {
  return wx.cloud.callFunction({
    name: 'fetchTickets',
    data: { email, code, startDate, endDate, taskId },
  })
}

function sendEmail({ email, code, toAddress, fileIds }) {
  return wx.cloud.callFunction({
    name: 'sendEmail',
    data: { email, code, toAddress, fileIds },
  })
}

async function createTask() {
  const res = await db.collection('tasks').add({
    data: {
      status: 'connecting',
      progress: '0/0',
      ticketCount: 0,
      totalAmount: 0,
      fileIds: {},
      createTime: db.serverDate(),
    },
  })
  return res._id
}

function watchTask(taskId, callback) {
  const timer = setInterval(async () => {
    try {
      const { data } = await db.collection('tasks').doc(taskId).get()
      callback(data)
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(timer)
      }
    } catch (e) {
      console.error('轮询失败:', e)
    }
  }, 2000)
  return timer
}

async function getTickets(taskId) {
  const { data } = await db.collection('tickets')
    .where({ _taskId: taskId })
    .orderBy('travelDate', 'desc')
    .get()
  return data
}

async function getTask(taskId) {
  const { data } = await db.collection('tasks').doc(taskId).get()
  return data
}

async function downloadFile(fileID) {
  const res = await wx.cloud.downloadFile({ fileID })
  return res.tempFilePath
}

async function saveImageToAlbum(tempFilePath) {
  return new Promise((resolve, reject) => {
    wx.saveImageToPhotosAlbum({
      filePath: tempFilePath,
      success: resolve,
      fail: reject,
    })
  })
}

async function openDocument(tempFilePath, fileType) {
  return new Promise((resolve, reject) => {
    wx.openDocument({
      filePath: tempFilePath,
      fileType,
      success: resolve,
      fail: reject,
    })
  })
}

module.exports = {
  fetchTickets,
  sendEmail,
  createTask,
  watchTask,
  getTickets,
  getTask,
  downloadFile,
  saveImageToAlbum,
  openDocument,
  db,
}
