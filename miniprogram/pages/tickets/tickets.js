const { getAllTickets } = require('../../utils/cloud')

Page({
  data: {
    tickets: [],
    groupedTickets: [],
    totalAmount: '0.00',
    loading: true,
  },

  onShow() { this.loadTickets() },

  async loadTickets() {
    this.setData({ loading: true })
    try {
      const tickets = await getAllTickets()
      const totalAmount = tickets.reduce((sum, t) => sum + t.amount, 0).toFixed(2)
      this.setData({
        tickets,
        groupedTickets: this._groupByMonth(tickets),
        totalAmount,
        loading: false,
      })
    } catch (e) {
      console.error('加载票据失败:', e)
      this.setData({ loading: false })
    }
  },

  _groupByMonth(tickets) {
    const map = {}
    tickets.forEach(t => {
      const month = t.travelDate.substring(0, 7)
      if (!map[month]) {
        map[month] = { month: `${month.substring(0, 4)}年${month.substring(5, 7)}月`, tickets: [] }
      }
      map[month].tickets.push(t)
    })
    return Object.values(map).sort((a, b) => b.month.localeCompare(a.month))
  },

  goExport() { wx.switchTab({ url: '/pages/export/export' }) },
})
