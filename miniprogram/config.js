/**
 * 小程序端配置。
 *
 * 生产环境必须使用已在微信公众平台登记、且完成 ICP 备案的 HTTPS 域名，
 * 并在「开发管理 > 开发设置」中配置为 request / uploadFile 合法域名。
 * 永远不要将 localhost、局域网 IP 或裸 HTTP 地址用于发布版本。
 */
module.exports = {
  // 后端 API 地址，改为你的服务域名，例如 'https://api.example.com'
  apiBaseUrl: 'https://api.example.com',
  // 隐私政策页面地址（webview 页内打开）
  privacyPolicyUrl: 'https://example.com/privacy',
  // OHIF 影像查看器地址（自建或官方 demo）
  ohifViewerUrl: 'https://viewer.ohif.org/local'
}
