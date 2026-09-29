const config = require('../../config')

Page({
  data: {
    selectedFile: '',
    fileName: '',
    uploading: false,
    privacyAccepted: false
  },
  onShow() {
    this.setData({ privacyAccepted: getApp().globalData.hasAcceptedPrivacy })
  },
  chooseReport() {
    if (!this.data.privacyAccepted) {
      wx.showToast({ title: '请先阅读并同意隐私说明', icon: 'none' })
      return
    }
    wx.showActionSheet({
      itemList: ['拍摄 / 从相册选择图片', '从微信文件选择 PDF'],
      success: ({ tapIndex }) => tapIndex === 0 ? this.chooseImage() : this.choosePdf()
    })
  },
  chooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: ({ tempFiles }) => this.setReport(tempFiles[0].tempFilePath, tempFiles[0].name || '检查报告图片')
    })
  },
  choosePdf() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf'],
      success: ({ tempFiles }) => {
        const file = tempFiles[0]
        if (!/\.pdf$/i.test(file.name)) {
          wx.showToast({ title: '请选择 PDF 报告', icon: 'none' })
          return
        }
        this.setReport(file.path, file.name)
      }
    })
  },
  setReport(path, name) {
    if (path && name) this.setData({ selectedFile: path, fileName: name })
  },
  uploadReport() {
    if (!this.data.privacyAccepted) return
    this.setData({ uploading: true })
    wx.showToast({ title: '正在识别，请稍候…', icon: 'loading', duration: 0 })
    wx.uploadFile({
      url: `${config.apiBaseUrl}/api/reports/ocr`,
      filePath: this.data.selectedFile,
      name: 'file',
      timeout: 120000,
      success: ({ statusCode, data }) => {
        wx.hideToast()
        let result
        try { result = JSON.parse(data) } catch (_) { result = null }
        if (statusCode < 200 || statusCode >= 300 || !result) {
          wx.showToast({ title: result?.detail || '读取失败，请稍后重试', icon: 'none' })
          return
        }
        wx.setStorageSync('latestOcrResult', result)
        wx.navigateTo({ url: '/pages/result/result' })
      },
      fail: (err) => {
        wx.hideToast()
        console.error('[uploadFile] fail', err)
        const reason = (err && err.errMsg) || '未知错误'
        wx.showToast({ title: `上传失败：${reason}`, icon: 'none', duration: 4000 })
      },
      complete: () => this.setData({ uploading: false })
    })
  },
  togglePrivacy({ detail }) {
    const accepted = detail.value.length > 0
    getApp().globalData.hasAcceptedPrivacy = accepted
    wx.setStorageSync('privacyAccepted', accepted)
    this.setData({ privacyAccepted: accepted })
  },
  openPrivacy() { wx.navigateTo({ url: '/pages/privacy/privacy' }) },
  openImaging() { wx.navigateTo({ url: '/pages/imaging/imaging' }) }
})
