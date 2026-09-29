const config = require('../../config')

Page({
  data: {
    fullText: '',
    needsReview: true,
    interpreting: true,
    interpretError: '',
    interpretation: null,
    showOriginal: false
  },

  onLoad() {
    const result = wx.getStorageSync('latestOcrResult')
    if (!result?.full_text) {
      wx.showToast({ title: '没有可显示的报告结果', icon: 'none' })
      wx.navigateBack()
      return
    }
    this.setData({
      fullText: result.full_text,
      needsReview: result.source_status !== 'verified'
    })
    this.interpret(result)
  },

  interpret(result) {
    this.setData({ interpreting: true, interpretError: '' })
    wx.request({
      url: `${config.apiBaseUrl}/api/reports/interpret`,
      method: 'POST',
      timeout: 90000,
      data: { full_text: result.full_text, lines: result.lines || [] },
      success: ({ statusCode, data }) => {
        if (statusCode === 200 && data && data.summary) {
          this.setData({ interpretation: data, interpreting: false })
          return
        }
        this.setData({
          interpreting: false,
          interpretError: (data && data.detail) || '解读服务暂不可用'
        })
      },
      fail: (err) => {
        console.error('[interpret] fail', err)
        this.setData({ interpreting: false, interpretError: '解读服务连接失败，请检查网络' })
      }
    })
  },

  retryInterpret() {
    const result = wx.getStorageSync('latestOcrResult')
    if (result?.full_text) this.interpret(result)
  },

  toggleOriginal() {
    this.setData({ showOriginal: !this.data.showOriginal })
  }
})
