const { fetchTickets } = require('../../utils/cloud')

function formatDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// fetchTickets 预估耗时 20 秒
const ESTIMATED_DURATION = 20

Page({
  data: {
    email: '',
    code: '',
    startDate: '',
    endDate: '',
    loading: false,
    progress: 0,
  },

  onLoad() {
    const saved = wx.getStorageSync('imap_config')
    const now = new Date()
    const oneMonthAgo = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
    this.setData({
      email: (saved && saved.email) || '',
      code: (saved && saved.code) || '',
      startDate: (saved && saved.startDate) || formatDate(oneMonthAgo),
      endDate: (saved && saved.endDate) || formatDate(now),
    })
  },

  onEmailInput(e) { this.setData({ email: e.detail.value }) },
  onCodeInput(e) { this.setData({ code: e.detail.value }) },
  onStartDateChange(e) { this.setData({ startDate: e.detail.value }) },
  onEndDateChange(e) { this.setData({ endDate: e.detail.value }) },

  _startProgress() {
    this.setData({ progress: 1 })
    const startTime = Date.now()
    this._progressTimer = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000
      const ratio = elapsed / ESTIMATED_DURATION
      const percent = Math.min(95, Math.floor(100 * (1 - Math.pow(1 - Math.min(ratio, 0.95), 2.5))))
      this.setData({ progress: percent })
    }, 300)
  },

  _stopProgress() {
    if (this._progressTimer) {
      clearInterval(this._progressTimer)
      this._progressTimer = null
    }
    this.setData({ progress: 100 })
    setTimeout(() => this.setData({ progress: 0 }), 600)
  },

  async onStartFetch() {
    const { email, code, startDate, endDate } = this.data
    if (!email || !code) {
      wx.showToast({ title: '请输入邮箱和授权码', icon: 'none' })
      return
    }
    if (!startDate || !endDate) {
      wx.showToast({ title: '请选择起止日期', icon: 'none' })
      return
    }

    wx.setStorageSync('imap_config', { email, code, startDate, endDate })
    this.setData({ loading: true })
    this._startProgress()

    try {
      const result = await fetchTickets({ email, code, startDate, endDate })
      this._stopProgress()
      this.setData({ loading: false })

      if (result.tickets.length === 0) {
        wx.showToast({ title: '未找到票据', icon: 'none' })
      } else {
        wx.showToast({ title: `找到 ${result.summary.count} 张票据`, icon: 'success' })
        wx.switchTab({ url: '/pages/tickets/tickets' })
      }
    } catch (e) {
      this._stopProgress()
      this.setData({ loading: false })
      wx.showToast({ title: '提取失败: ' + e.message, icon: 'none' })
    }
  },
})
