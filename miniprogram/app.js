App({
  globalData: {
    hasAcceptedPrivacy: false
  },
  onLaunch() {
    this.globalData.hasAcceptedPrivacy = wx.getStorageSync('privacyAccepted') === true
  }
})
