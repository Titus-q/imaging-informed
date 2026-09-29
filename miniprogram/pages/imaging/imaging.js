const config = require('../../config')
Page({
  openViewer() {
    if (config.ohifViewerUrl.includes('example.com')) {
      wx.showToast({ title: '请先配置受保护的 OHIF 地址', icon: 'none' })
      return
    }
    wx.navigateTo({ url: `/pages/webview/webview?url=${encodeURIComponent(config.ohifViewerUrl)}` })
  }
})
