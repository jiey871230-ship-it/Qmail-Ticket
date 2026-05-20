const { fetchTickets, createTask, watchTask } = require('../../utils/cloud')

Page({
  data: {
    email: '',
    code: '',
    startDate: '',
    endDate: '',
    loading: false,
    progress: '',
    taskId: '',
    pollTimer: null,
  },

  onLoad() {
    const saved = wx.getStorageSync('imap_config')
    if (saved) {
      this.setData({
        email: saved.email || '',
        code: saved.code || '',
      })
    }
  },

  onUnload() {
    if (this.data.pollTimer) {
      clearInterval(this.data.pollTimer)
    }
  },

  onEmailInput(e) {
    this.setData({ email: e.detail.value })
  },

  onCodeInput(e) {
    this.setData({ code: e.detail.value })
  },

  onStartDateChange(e) {
    this.setData({ startDate: e.detail.value })
  },

  onEndDateChange(e) {
    this.setData({ endDate: e.detail.value })
  },

  async onStartFetch() {
    const { email, code, startDate, endDate } = this.data
    if (!email || !code) {
      wx.showToast({ title: '请输入邮箱和授权码', icon: 'none' })
      return
    }

    wx.setStorageSync('imap_config', { email, code })

    this.setData({ loading: true, progress: '正在连接...' })

    try {
      const taskId = await createTask()
      this.setData({ taskId })

      fetchTickets({ email, code, startDate, endDate, taskId })

      const timer = watchTask(taskId, (taskData) => {
        const statusMap = {
          connecting: '正在连接邮箱...',
          connected: '已连接，开始解析...',
          parsing: `正在解析票面 ${taskData.progress}`,
          generating: '正在生成文件...',
          done: '完成！',
          error: `出错: ${taskData.progress}`,
        }
        this.setData({ progress: statusMap[taskData.status] || taskData.status })

        if (taskData.status === 'done') {
          this.setData({ loading: false })
          clearInterval(this.data.pollTimer)
          wx.showToast({ title: '提取完成', icon: 'success' })
          wx.switchTab({ url: '/pages/tickets/tickets' })
        } else if (taskData.status === 'error') {
          this.setData({ loading: false })
          clearInterval(this.data.pollTimer)
          wx.showToast({ title: '提取失败', icon: 'none' })
        }
      })
      this.setData({ pollTimer: timer })
    } catch (e) {
      this.setData({ loading: false })
      wx.showToast({ title: '调用失败: ' + e.message, icon: 'none' })
    }
  },
})
