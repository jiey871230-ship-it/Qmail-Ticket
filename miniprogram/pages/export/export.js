const { sendEmail, clearAllTickets } = require('../../utils/cloud')

// sendEmail 预估耗时 27 秒
const ESTIMATED_DURATION = 27

Page({
  data: {
    toAddress: '',
    startDate: '',
    endDate: '',
    sending: false,
    clearing: false,
    progress: 0,
    progressTitle: '',
  },

  onLoad() {
    this._loadConfig()
  },

  onShow() {
    this._loadConfig()
  },

  _loadConfig() {
    const saved = wx.getStorageSync('imap_config')
    if (saved) {
      this.setData({
        toAddress: saved.lastToAddress || this.data.toAddress,
        startDate: saved.startDate || '',
        endDate: saved.endDate || '',
      })
    }
  },

  onToAddressInput(e) { this.setData({ toAddress: e.detail.value }) },

  _startProgress(title) {
    this.setData({ progress: 1, progressTitle: title })
    const startTime = Date.now()
    this._progressTimer = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000
      // 用缓动曲线：前期快后期慢，永远不到 100%
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

  async sendEmail() {
    const { toAddress, startDate, endDate } = this.data
    if (!toAddress) {
      wx.showToast({ title: '请输入收件地址', icon: 'none' })
      return
    }
    if (!startDate || !endDate) {
      wx.showToast({ title: '请先在首页设置日期范围', icon: 'none' })
      return
    }

    const saved = wx.getStorageSync('imap_config') || {}
    const { email, code } = saved
    if (!email || !code) {
      wx.showToast({ title: '请先在首页配置邮箱', icon: 'none' })
      return
    }

    saved.lastToAddress = toAddress
    wx.setStorageSync('imap_config', saved)

    this.setData({ sending: true })
    this._startProgress('正在连接邮箱并发送...')

    try {
      const { result } = await sendEmail({
        email,
        code,
        toAddress,
        startDate,
        endDate,
      })

      this._stopProgress()

      if (result && result.success) {
        const timing = result.timing || {}
        wx.showModal({
          title: '发送成功',
          content: `已发送至 ${toAddress}\n票据: ${result.ticketCount} 张\n耗时: ${timing.total || '?'} 秒`,
          showCancel: false,
        })
      } else {
        wx.showToast({ title: result.error || '发送失败', icon: 'none' })
      }
    } catch (e) {
      this._stopProgress()
      wx.showToast({ title: '发送失败: ' + e.message, icon: 'none' })
    } finally {
      this.setData({ sending: false })
    }
  },

  async clearData() {
    wx.showModal({
      title: '确认清空',
      content: '将删除所有已提取的票据数据',
      success: async (res) => {
        if (!res.confirm) return
        this.setData({ clearing: true })
        try {
          const count = await clearAllTickets()
          wx.showToast({ title: `已删除 ${count} 条记录`, icon: 'success' })
        } catch (e) {
          wx.showToast({ title: '清空失败', icon: 'none' })
        } finally {
          this.setData({ clearing: false })
        }
      },
    })
  },
})
