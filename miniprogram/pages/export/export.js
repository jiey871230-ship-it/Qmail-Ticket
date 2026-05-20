const cloud = require('../../utils/cloud')

Page({
  data: {
    fileIds: { jpgs: [], csv: '', pdf: '' },
    jpgPreviews: [],
    ticketCount: 0,
    toAddress: '',
    downloading: false,
    downloadProgress: '',
    savingJpgs: false,
    jpgProgress: '',
    sending: false,
  },

  onLoad() {
    const saved = wx.getStorageSync('imap_config')
    if (saved && saved.lastToAddress) {
      this.setData({ toAddress: saved.lastToAddress })
    }
    this.loadFileIds()
  },

  async loadFileIds() {
    try {
      const db = cloud.db
      const { data: tasks } = await db.collection('tasks')
        .where({ status: 'done' })
        .orderBy('createTime', 'desc')
        .limit(1)
        .get()

      if (!tasks.length) return

      const task = tasks[0]
      const fileIds = task.fileIds || { jpgs: [], csv: '', pdf: '' }

      const jpgPreviews = []
      for (const fid of fileIds.jpgs.slice(0, 10)) {
        try {
          const res = await wx.cloud.getTempFileURL({ fileList: [fid] })
          if (res.fileList[0].tempFileURL) {
            jpgPreviews.push(res.fileList[0].tempFileURL)
          }
        } catch (e) {}
      }

      this.setData({
        fileIds,
        jpgPreviews,
        ticketCount: task.ticketCount || 0,
      })
    } catch (e) {
      console.error('加载文件信息失败:', e)
    }
  },

  onToAddressInput(e) {
    this.setData({ toAddress: e.detail.value })
  },

  async downloadAll() {
    this.setData({ downloading: true, downloadProgress: '正在保存图片...' })
    try {
      await this.saveAllJpgs()
      this.setData({ downloadProgress: '正在打开 CSV...' })
      await this.downloadCsv()
      this.setData({ downloadProgress: '正在打开 PDF...' })
      await this.downloadPdf()
      wx.showToast({ title: '全部下载完成', icon: 'success' })
    } catch (e) {
      wx.showToast({ title: '部分下载失败', icon: 'none' })
    } finally {
      this.setData({ downloading: false, downloadProgress: '' })
    }
  },

  async saveAllJpgs() {
    if (!this.data.fileIds.jpgs.length) return
    this.setData({ savingJpgs: true })
    const total = this.data.fileIds.jpgs.length
    try {
      for (let i = 0; i < total; i++) {
        this.setData({ jpgProgress: `${i + 1}/${total}` })
        const tempPath = await cloud.downloadFile(this.data.fileIds.jpgs[i])
        await cloud.saveImageToAlbum(tempPath)
      }
      if (!this.data.downloading) {
        wx.showToast({ title: '已保存到相册', icon: 'success' })
      }
    } catch (e) {
      if (e.errMsg && e.errMsg.includes('auth deny')) {
        wx.showModal({
          title: '需要授权',
          content: '请在设置中允许保存到相册',
          confirmText: '去设置',
          success(res) {
            if (res.confirm) wx.openSetting()
          },
        })
      }
    } finally {
      this.setData({ savingJpgs: false, jpgProgress: '' })
    }
  },

  previewJpg(e) {
    const index = e.currentTarget.dataset.index
    wx.previewImage({
      urls: this.data.jpgPreviews,
      current: this.data.jpgPreviews[index],
    })
  },

  async downloadCsv() {
    if (!this.data.fileIds.csv) return
    try {
      const tempPath = await cloud.downloadFile(this.data.fileIds.csv)
      await cloud.openDocument(tempPath, 'csv')
    } catch (e) {
      wx.showToast({ title: 'CSV 下载失败', icon: 'none' })
    }
  },

  async downloadPdf() {
    if (!this.data.fileIds.pdf) return
    try {
      const tempPath = await cloud.downloadFile(this.data.fileIds.pdf)
      await cloud.openDocument(tempPath, 'pdf')
    } catch (e) {
      wx.showToast({ title: 'PDF 下载失败', icon: 'none' })
    }
  },

  async sendEmail() {
    const { toAddress, fileIds } = this.data
    if (!toAddress) {
      wx.showToast({ title: '请输入收件地址', icon: 'none' })
      return
    }

    const saved = wx.getStorageSync('imap_config') || {}
    saved.lastToAddress = toAddress
    wx.setStorageSync('imap_config', saved)

    this.setData({ sending: true })
    try {
      const { email, code } = wx.getStorageSync('imap_config')
      const res = await cloud.sendEmail({ email, code, toAddress, fileIds })
      if (res.result && res.result.success) {
        wx.showToast({ title: `已发送至 ${toAddress}`, icon: 'success' })
      } else {
        wx.showToast({ title: '发送失败', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: '发送失败: ' + e.message, icon: 'none' })
    } finally {
      this.setData({ sending: false })
    }
  },
})
