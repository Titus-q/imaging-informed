Page({
  data: { url: '' },
  onLoad({ url }) {
    if (!url || !/^https:\/\//.test(decodeURIComponent(url))) {
      wx.showToast({ title: '查看器地址无效', icon: 'none' })
      wx.navigateBack()
      return
    }
    this.setData({ url: decodeURIComponent(url) })
  }
})
